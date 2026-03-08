import os
import torch
import gc
import soundfile as sf
import numpy as np
import importlib.util
import subprocess
import sys

class SuppressWindows:
    """Context manager to suppress console windows on Windows"""
    def __enter__(self):
        if os.name == 'nt':
            self._original_popen = subprocess.Popen
            
            def new_popen(*args, **kwargs):
                # Ensure creationflags includes CREATE_NO_WINDOW
                if 'creationflags' not in kwargs:
                    kwargs['creationflags'] = 0x08000000 # CREATE_NO_WINDOW
                else:
                    kwargs['creationflags'] |= 0x08000000
                
                # Ensure startupinfo hides window
                if 'startupinfo' not in kwargs:
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    si.wShowWindow = 0
                    kwargs['startupinfo'] = si
                    
                return self._original_popen(*args, **kwargs)
                
            subprocess.Popen = new_popen
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if os.name == 'nt':
            subprocess.Popen = self._original_popen

class Qwen3TTS:
    def __init__(self, model_dir, device="cuda"):
        self.model_dir = model_dir
        self.device = device
        self.model_wrapper = None # Instance of Qwen3TTSModel
        
        # Add local sox to PATH if exists (keeping this from previous version)
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # indextts -> root
        sox_path = os.path.join(root_dir, "sox-14.4.2-win32")
        if os.path.exists(sox_path):
            os.environ["PATH"] = sox_path + os.pathsep + os.environ["PATH"]

    def _ensure_package(self, module_name, package_name=None):
        if package_name is None:
            package_name = module_name
        if importlib.util.find_spec(module_name) is None:
            print(f"Installing missing package: {package_name}")
            try:
                cmd = [sys.executable, "-m", "pip", "install", package_name]
                if os.name == 'nt':
                    try:
                        cf = subprocess.CREATE_NO_WINDOW
                        si = subprocess.STARTUPINFO()
                        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        si.wShowWindow = 0
                        subprocess.check_call(cmd, creationflags=cf, startupinfo=si)
                    except Exception:
                        subprocess.check_call(cmd)
                else:
                    subprocess.check_call(cmd)
                print(f"Successfully installed {package_name}")
            except subprocess.CalledProcessError as e:
                print(f"Failed to install {package_name}: {e}")

    def _patch_transformers(self):
        try:
            import transformers.utils.args_doc as args_doc
            def safe_auto_class_docstring(obj=None, *args, **kwargs):
                if obj is not None and isinstance(obj, type):
                    return obj
                def decorator(cls):
                    return cls
                return decorator
            args_doc.auto_class_docstring = safe_auto_class_docstring
        except Exception:
            pass

        try:
            import transformers
            try:
                import transformers.masking_utils
                return
            except Exception:
                pass
            import types
            masking_utils = types.ModuleType("transformers.masking_utils")
            found_prepare = False
            try:
                from transformers.modeling_attn_mask_utils import _prepare_4d_causal_attention_mask
                masking_utils._prepare_4d_causal_attention_mask = _prepare_4d_causal_attention_mask
                found_prepare = True
            except Exception:
                pass
            try:
                from transformers.modeling_attn_mask_utils import _create_4d_causal_attention_mask
                masking_utils.create_causal_mask = _create_4d_causal_attention_mask
            except Exception:
                def create_causal_mask(*args, **kwargs):
                    return None
                masking_utils.create_causal_mask = create_causal_mask
            try:
                from transformers.modeling_attn_mask_utils import _create_4d_causal_attention_mask
                def create_sliding_window_causal_mask(*args, **kwargs):
                    return _create_4d_causal_attention_mask(*args, **kwargs)
                masking_utils.create_sliding_window_causal_mask = create_sliding_window_causal_mask
            except Exception:
                def create_sliding_window_causal_mask(*args, **kwargs):
                    return None
                masking_utils.create_sliding_window_causal_mask = create_sliding_window_causal_mask
            if not found_prepare:
                def _prepare_4d_causal_attention_mask(*args, **kwargs):
                    return None
                masking_utils._prepare_4d_causal_attention_mask = _prepare_4d_causal_attention_mask
            sys.modules["transformers.masking_utils"] = masking_utils
            transformers.masking_utils = masking_utils
        except Exception:
            pass

    def load_model(self):
        if self.model_wrapper is not None:
            return

        print(f"Loading Qwen3-TTS from {self.model_dir}...")
        
        # Ensure qwen_tts is available
        self._ensure_package("qwen_tts", "qwen-tts")

        self._patch_transformers()
        
        try:
            with SuppressWindows():
                from qwen_tts.inference.qwen3_tts_model import Qwen3TTSModel
        except ImportError:
            print("Error: Could not import Qwen3TTSModel from qwen_tts. Please ensure qwen-tts is installed correctly.")
            return

        # Prepare loading arguments
        # Using bfloat16 and flash_attention_2 for performance if on CUDA, similar to webui copy.py
        dtype = torch.float32
        attn_impl = "eager"
        
        if self.device != "cpu" and torch.cuda.is_available():
            dtype = torch.bfloat16
            attn_impl = "flash_attention_2"

        try:
            print(f"Attempting to load model with dtype={dtype} and attn_implementation={attn_impl}...")
            self.model_wrapper = Qwen3TTSModel.from_pretrained(
                self.model_dir,
                device_map=self.device,
                dtype=dtype,
                attn_implementation=attn_impl,
            )
            print("Model loaded successfully with optimized settings.")
        except Exception as e:
            print(f"Failed to load with optimized settings: {e}")
            print("Retrying with default settings (float32, eager)...")
            try:
                self.model_wrapper = Qwen3TTSModel.from_pretrained(
                    self.model_dir,
                    device_map=self.device,
                    dtype=torch.float32,
                    attn_implementation="eager"
                )
                print("Model loaded successfully with default settings.")
            except Exception as e2:
                print(f"CRITICAL: Failed to load Qwen3-TTS model: {e2}")
                import traceback
                traceback.print_exc()
                raise e2

    def unload_model(self):
        if self.model_wrapper is not None:
            # Clean up internal model components
            if hasattr(self.model_wrapper, 'model'):
                del self.model_wrapper.model
            if hasattr(self.model_wrapper, 'processor'):
                del self.model_wrapper.processor
            del self.model_wrapper
            self.model_wrapper = None
        
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
        gc.collect()
        print("Qwen3-TTS model unloaded.")

    def generate(self, text, voice_description, output_path, language="auto"):
        self.load_model()
        
        if self.model_wrapper is None:
            print("Generation failed: Model not loaded.")
            return None

        # Debug memory usage
        if torch.cuda.is_available():
            vram_allocated = torch.cuda.memory_allocated() / 1024**3
            vram_reserved = torch.cuda.memory_reserved() / 1024**3
            print(f"[Qwen3-TTS] VRAM Usage before generation: Allocated={vram_allocated:.2f}GB, Reserved={vram_reserved:.2f}GB")

        print(f"Generating audio for: {text[:20]}... (Language: {language}, Desc: {voice_description[:20]}...)")
        
        try:
            # Map "auto" to something specific if needed, or let model handle it.
            # Qwen3TTSModel expects specific languages usually.
            # If language is "auto", we might default to "Chinese" or "English" or let the user decide.
            # Based on webui copy.py, it passes "Chinese", "English", etc. directly.
            
            # Use generate_voice_design for prompt-based generation
            # text -> text
            # voice_description -> instruct
            # language -> language
            
            wavs, sr = self.model_wrapper.generate_voice_design(
                text=text,
                language=language,
                instruct=voice_description
            )
            
            if wavs is not None and len(wavs) > 0:
                audio = wavs[0]
                sf.write(output_path, audio, sr)
                print(f"Saved generated audio to {output_path}")
                return output_path
            else:
                print("Audio generation returned empty result.")
                return None

        except Exception as e:
            print(f"Generation failed: {e}")
            import traceback
            traceback.print_exc()
            return None
