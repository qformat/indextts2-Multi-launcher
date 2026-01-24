import os
import gc
import shutil
import sys
import subprocess
import importlib.util

def ensure_package(module_name, package_name=None):
    if package_name is None:
        package_name = module_name
    if importlib.util.find_spec(module_name) is None:
        print(f"正在安装缺失的依赖包: {package_name}")
        try:
            # 优先尝试使用 uv 安装，因为用户环境中有 uv
            try:
                subprocess.check_call(["uv", "pip", "install", package_name])
            except (subprocess.CalledProcessError, FileNotFoundError):
                # 如果 uv 失败或未找到，回退到 pip
                subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
            print(f"成功安装 {package_name}")
        except subprocess.CalledProcessError as e:
            print(f"安装 {package_name} 失败，请尝试手动安装。")
            raise e

# 自动检查并安装关键依赖
ensure_package("qwen_tts", "qwen-tts")
ensure_package("modelscope")
ensure_package("gradio")

# 自动配置 SoX 环境变量
# 检查当前目录下是否存在 sox-14.4.2-win32 文件夹，如果存在则添加到 PATH
sox_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sox-14.4.2-win32")
if os.path.exists(sox_path):
    os.environ["PATH"] = sox_path + os.pathsep + os.environ["PATH"]
    print(f"检测到本地 SoX，已添加到环境变量: {sox_path}")
else:
    # 尝试检查 sox 是否在 PATH 中
    if shutil.which("sox") is None:
        print("警告: 未检测到 SoX，请确保已安装 SoX 并添加到环境变量，或者将 sox-14.4.2-win32 解压到项目根目录。")

import torch
import soundfile as sf
import gradio as gr
from qwen_tts import Qwen3TTSModel
from modelscope import snapshot_download
from datetime import datetime

# ==========================================
# 配置与元数据
# ==========================================

MODELS_DIR = "models"
YINSE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yinse")
OUTPUTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")

os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(YINSE_DIR, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)

MODEL_CONFIG = {
    "Qwen3-TTS-12Hz-1.7B-VoiceDesign": {
        "repo_id": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
        "type": "VoiceDesign",
        "support_instruct": True,
        "support_speaker": False,
        "support_clone": False,
        "desc": "根据用户提供的描述进行声音设计。",
        "features": ["流式生成", "指令控制"],
        "languages": ["Chinese", "English", "Japanese", "Korean", "German", "French", "Russian", "Portuguese", "Spanish", "Italian"]
    },
    "Qwen3-TTS-12Hz-1.7B-CustomVoice": {
        "repo_id": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "type": "CustomVoice",
        "support_instruct": True,
        "support_speaker": True,
        "support_clone": False,
        "desc": "通过用户指令对目标音色进行风格控制；支持 9 种优质音色。",
        "features": ["流式生成", "指令控制"],
        "languages": ["Chinese", "English", "Japanese", "Korean", "German", "French", "Russian", "Portuguese", "Spanish", "Italian"]
    },
    "Qwen3-TTS-12Hz-1.7B-Base": {
        "repo_id": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        "type": "Base",
        "support_instruct": False,
        "support_speaker": False,
        "support_clone": True,
        "desc": "基础模型，支持从用户提供的 3 秒音频输入中快速克隆声音。",
        "features": ["流式生成"],
        "languages": ["Chinese", "English", "Japanese", "Korean", "German", "French", "Russian", "Portuguese", "Spanish", "Italian"]
    },
    "Qwen3-TTS-12Hz-0.6B-CustomVoice": {
        "repo_id": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
        "type": "CustomVoice",
        "support_instruct": False,
        "support_speaker": True,
        "support_clone": False,
        "desc": "支持 9 种优质音色。",
        "features": ["流式生成"],
        "languages": ["Chinese", "English", "Japanese", "Korean", "German", "French", "Russian", "Portuguese", "Spanish", "Italian"]
    },
    "Qwen3-TTS-12Hz-0.6B-Base": {
        "repo_id": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        "type": "Base",
        "support_instruct": False,
        "support_speaker": False,
        "support_clone": True,
        "desc": "基础模型，支持从用户提供的 3 秒音频输入中快速克隆声音。",
        "features": ["流式生成"],
        "languages": ["Chinese", "English", "Japanese", "Korean", "German", "French", "Russian", "Portuguese", "Spanish", "Italian"]
    }
}

# 全局状态
current_model = None
current_model_name = None
device = "cuda:0" if torch.cuda.is_available() else "cpu"

# ==========================================
# 核心功能函数
# ==========================================

def get_local_model_path(model_name):
    """获取本地模型路径"""
    return os.path.join(MODELS_DIR, model_name)

def load_model(model_name):
    global current_model, current_model_name
    
    if current_model_name == model_name and current_model is not None:
        return f"模型 {model_name} 已经加载。"

    print(f"Loading model: {model_name}...")
    
    # 卸载旧模型
    if current_model is not None:
        del current_model
        gc.collect()
        torch.cuda.empty_cache()
        current_model = None
        print("Previous model unloaded.")

    repo_id = MODEL_CONFIG[model_name]["repo_id"]
    local_path = get_local_model_path(model_name)
    
    # 检查模型是否存在，不存在则下载
    if not os.path.exists(local_path) or not os.listdir(local_path):
        print(f"Downloading {model_name} from {repo_id} to {local_path}...")
        try:
            snapshot_download(repo_id, local_dir=local_path)
            print("Download complete.")
        except Exception as e:
            return f"下载模型失败: {e}"
    else:
        print(f"Found local model at {local_path}")

    # 加载新模型
    try:
        current_model = Qwen3TTSModel.from_pretrained(
            local_path,
            device_map=device,
            dtype=torch.bfloat16 if device != "cpu" else torch.float32,
            attn_implementation="flash_attention_2" if device != "cpu" else "eager",
        )
        current_model_name = model_name
        return f"模型 {model_name} 加载成功！"
    except Exception as e:
        # Fallback
        print(f"Error loading with Flash Attention 2: {e}. Retrying with default...")
        try:
            current_model = Qwen3TTSModel.from_pretrained(
                local_path,
                device_map=device,
                dtype=torch.float32,
            )
            current_model_name = model_name
            return f"模型 {model_name} 加载成功 (Fallback Mode)！"
        except Exception as e2:
            return f"模型加载失败: {e2}"

def get_speakers():
    """获取当前模型的支持音色列表"""
    if current_model and hasattr(current_model, "get_supported_speakers"):
        return current_model.get_supported_speakers()
    return []

# 新增：获取本地音色库文件列表
def get_local_voices():
    if not os.path.exists(YINSE_DIR):
        return []
    files = [f for f in os.listdir(YINSE_DIR) if f.lower().endswith(('.wav', '.mp3', '.m4a', '.flac'))]
    return files

# 新增：保存上传的音色文件
def save_local_voice(file):
    if file is None:
        return None, "未选择文件"
    
    # file.name 是临时文件路径，我们需要获取原始文件名
    # Gradio 的 file 对象通常是 temp path，如果使用 type='filepath'
    # 如果使用 UploadButton, file 是一个 list 或 single path
    
    # 获取文件名
    original_filename = os.path.basename(file)
    target_path = os.path.join(YINSE_DIR, original_filename)
    
    try:
        shutil.copy2(file, target_path)
        return target_path, f"已保存到 {original_filename}"
    except Exception as e:
        return None, f"保存失败: {str(e)}"

# 新增：试听预置音色
def preview_preset_voice(model_name, speaker):
    if not speaker:
        return None, "请先选择音色"
    
    text = f"你好，我是{speaker}。"
    # 调用生成函数，但不保存长文件名
    # 复用 generate_audio 的部分逻辑，或直接调用模型
    
    if current_model_name != model_name or current_model is None:
        load_model(model_name)
    
    try:
        wavs, sr = current_model.generate_custom_voice(
            text=text,
            language="Chinese",
            speaker=speaker
        )
        timestamp = datetime.now().strftime("%H%M%S")
        output_filename = os.path.join(OUTPUTS_DIR, f"preview_{speaker}_{timestamp}.wav")
        sf.write(output_filename, wavs[0], sr)
        return output_filename, "试听生成成功"
    except Exception as e:
        return None, f"试听生成失败: {e}"

def generate_audio(model_name, text, language, instruct, speaker, ref_audio, ref_text, local_voice_path):
    global current_model
    
    if not text:
        return None, "请输入文本。"
    
    if current_model_name != model_name or current_model is None:
        status = load_model(model_name)
        if "失败" in status:
            return None, status
    
    config = MODEL_CONFIG[model_name]
    model_type = config["type"]
    
    print(f"Generating with {model_name} (Type: {model_type})...")
    
    try:
        wavs = None
        sr = None
        
        if model_type == "VoiceDesign":
            if not instruct: instruct = "普通话男声，清晰自然。"
            wavs, sr = current_model.generate_voice_design(
                text=text,
                language=language,
                instruct=instruct
            )
            
        elif model_type == "CustomVoice":
            if not speaker:
                return None, "错误：请选择一个音色 (Speaker)。如果是初次加载模型，请等待音色列表加载完成。"
            
            kwargs = {"text": text, "language": language, "speaker": speaker}
            if config["support_instruct"] and instruct:
                kwargs["instruct"] = instruct
            
            try:
                wavs, sr = current_model.generate_custom_voice(**kwargs)
            except TypeError:
                if "instruct" in kwargs:
                    del kwargs["instruct"]
                    wavs, sr = current_model.generate_custom_voice(**kwargs)
                else:
                    raise
                    
        elif model_type == "Base":
            print(f"DEBUG: ref_audio type: {type(ref_audio)}")
            print(f"DEBUG: ref_audio value: {ref_audio}")
            print(f"DEBUG: local_voice_path: {local_voice_path}")
            print(f"DEBUG: YINSE_DIR: {YINSE_DIR}")

            # 如果 Audio 组件没有值，但选择了本地音色库的文件，尝试使用本地音色库的文件
            if (ref_audio is None or ref_audio == "") and local_voice_path:
                full_local_path = os.path.join(YINSE_DIR, local_voice_path)
                print(f"DEBUG: Trying to fallback to local path: {full_local_path}")
                if os.path.exists(full_local_path):
                    ref_audio = full_local_path
                    print(f"Using local voice from library: {ref_audio}")
                else:
                    print(f"ERROR: File does not exist: {full_local_path}")

            if not ref_audio:
                error_msg = f"Base 模型需要参考音频。DEBUG: local_voice={local_voice_path}"
                if local_voice_path:
                     error_msg += f", path_exists={os.path.exists(os.path.join(YINSE_DIR, local_voice_path))}"
                return None, error_msg
            
            # 自动判断模式：如果没有参考文本，则启用 x_vector_only_mode
            use_x_vector = False
            if not ref_text or ref_text.strip() == "":
                use_x_vector = True
                print("未提供参考文本，自动启用 x_vector_only_mode (仅使用音色嵌入)")
            
            # ref_audio 是一个 filepath 字符串
            # 修复参数名：prompt_audio -> ref_audio, prompt_text -> ref_text
            prompt = current_model.create_voice_clone_prompt(
                ref_audio=ref_audio,
                ref_text=ref_text if ref_text else None,
                x_vector_only_mode=use_x_vector
            )
            wavs, sr = current_model.generate_voice_clone(
                text=text,
                language=language,
                voice_clone_prompt=prompt
            )
            
        if wavs is not None and len(wavs) > 0:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = os.path.join(OUTPUTS_DIR, f"output_{timestamp}.wav")
            sf.write(output_filename, wavs[0], sr)
            return output_filename, "生成成功！"
        else:
            return None, "生成结果为空。"
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None, f"生成出错: {str(e)}"

# ==========================================
# Gradio 界面逻辑
# ==========================================

def update_ui_for_model(model_name):
    """根据选择的模型更新 UI 组件可见性"""
    config = MODEL_CONFIG[model_name]
    
    # 构造模型信息 Markdown
    info_md = f"""
    ### 当前模型: {model_name}
    - **描述**: {config['desc']}
    - **支持语言**: {', '.join(config['languages'])}
    - **特性**: {' '.join(['✅ ' + f for f in config['features']])}
    """
    
    # 可见性控制
    show_instruct = config["support_instruct"]
    show_speaker = config["support_speaker"]
    show_clone = config["support_clone"]
    
    # 自动加载模型以获取 speaker 列表 (如果是 CustomVoice)
    speakers = []
    status_msg = f"已选择 {model_name}。请点击生成，模型将自动加载。"
    
    if show_speaker:
         status_msg = f"正在加载 {model_name} 以获取音色列表..."
    
    return (
        info_md,
        gr.update(visible=show_instruct), # instruct_input
        gr.update(visible=show_speaker),  # speaker_group (changed from dropdown to group)
        gr.update(visible=show_clone),    # clone_group
        gr.update(choices=[]),            # speaker_dropdown (temp)
        status_msg
    )

def on_model_select(model_name):
    # 1. 更新 UI 布局
    info, vis_instruct, vis_speaker_group, vis_clone, _, msg = update_ui_for_model(model_name)
    
    # 2. 如果需要 Speaker 列表，必须加载模型
    new_speaker_choices = []
    if MODEL_CONFIG[model_name]["support_speaker"]:
        try:
            load_result = load_model(model_name)
            msg = load_result
            new_speaker_choices = get_speakers()
        except Exception as e:
            msg = f"加载模型失败: {e}"
    
    return info, vis_instruct, vis_speaker_group, vis_clone, gr.update(choices=new_speaker_choices, value=new_speaker_choices[0] if new_speaker_choices else None), msg

def on_local_voice_select(filename):
    if not filename:
        return None, None
    filepath = os.path.join(YINSE_DIR, filename)
    return filepath, filepath

def on_upload_local_voice(file):
    if not file:
        return gr.update(), "未上传文件"
    
    target_path, msg = save_local_voice(file)
    if target_path:
        # 刷新下拉列表
        new_choices = get_local_voices()
        return gr.update(choices=new_choices, value=os.path.basename(target_path)), msg
    else:
        return gr.update(), msg

def on_refresh_local_voices():
    new_choices = get_local_voices()
    return gr.update(choices=new_choices)


with gr.Blocks(title="Qwen3-TTS 全功能 WebUI") as demo:
    gr.Markdown("# Qwen3-TTS 全功能语音合成 WebUI")
    gr.Markdown("关注b站UP：“K哥讲AI”获取更多有意思的AI产品 [点击获取](https://pan.quark.cn/s/01f7bde0e6a5)")
    
    with gr.Row():
        with gr.Column(scale=1):
            # 模型选择区
            model_dropdown = gr.Dropdown(
                label="选择模型 (Select Model)",
                choices=list(MODEL_CONFIG.keys()),
                value="Qwen3-TTS-12Hz-1.7B-VoiceDesign",
                interactive=True
            )
            model_info = gr.Markdown(value="初始化中...")
            load_status = gr.Textbox(label="系统状态", value="准备就绪", interactive=False)
            
        with gr.Column(scale=2):
            # 通用输入区
            text_input = gr.Textbox(
                label="输入文本 (Text)",
                placeholder="请输入您想让模型说的话...",
                lines=3,
                value="你好，这是 Qwen3-TTS 的语音合成测试，关注B站UP：“K哥讲AI”获取更多有意思的AI产品！"
            )
            
            language_dropdown = gr.Dropdown(
                label="语言 (Language)",
                choices=MODEL_CONFIG["Qwen3-TTS-12Hz-1.7B-VoiceDesign"]["languages"],
                value="Chinese",
                interactive=True
            )
            
            # 动态功能区
            # 1. 指令控制 (VoiceDesign / CustomVoice 1.7B)
            instruct_input = gr.Textbox(
                label="声音描述 (Instruct)",
                placeholder="描述声音风格，例如：'温柔的女声'...",
                lines=2,
                visible=True,
                value="普通话男声，清晰自然。"
            )
            
            # 2. 音色选择 (CustomVoice)
            with gr.Group(visible=False) as speaker_group:
                with gr.Row():
                    speaker_dropdown = gr.Dropdown(
                        label="选择音色 (Speaker)",
                        choices=[],
                        scale=3,
                        interactive=True,
                        allow_custom_value=True
                    )
                    preview_btn = gr.Button("🔊 试听当前音色", scale=1)
                preview_output = gr.Audio(label="试听结果", type="filepath", visible=True)
            
            # 3. 声音克隆 (Base)
            with gr.Group(visible=False) as clone_group:
                gr.Markdown("### 声音克隆 (Voice Clone)")
                
                with gr.Row():
                    local_voice_dropdown = gr.Dropdown(
                        label="📂 本地音色库 (yinse 目录)",
                        choices=get_local_voices(),
                        scale=3,
                        interactive=True,
                        allow_custom_value=True
                    )
                    refresh_btn = gr.Button("🔄 刷新", scale=1)
                
                with gr.Row():
                    upload_btn = gr.UploadButton("⬆️ 上传新音色到库", file_types=["audio"], type="filepath")
                    upload_status = gr.Textbox(label="上传状态", interactive=False, show_label=False)

                ref_audio_input = gr.Audio(label="参考音频 (Reference Audio)", type="filepath", interactive=True)
                
                ref_text_input = gr.Textbox(
                    label="参考音频文本 (Reference Text)",
                    placeholder="参考音频对应的文本内容（可选，有助于提升效果）",
                    lines=1
                )

            submit_btn = gr.Button("开始合成 (Generate)", variant="primary")
            audio_output = gr.Audio(label="合成结果 (Output)", type="filepath")

    # 事件绑定
    model_dropdown.change(
        fn=on_model_select,
        inputs=[model_dropdown],
        outputs=[model_info, instruct_input, speaker_group, clone_group, speaker_dropdown, load_status],
        api_name="select_model"
    )
    
    # 试听按钮
    preview_btn.click(
        fn=preview_preset_voice,
        inputs=[model_dropdown, speaker_dropdown],
        outputs=[preview_output, load_status],
        api_name="preview_voice"
    )
    
    # 本地音色库逻辑
    local_voice_dropdown.change(
        fn=on_local_voice_select,
        inputs=[local_voice_dropdown],
        outputs=[ref_audio_input],
        api_name="select_local_voice"
    )
    
    upload_btn.upload(
        fn=on_upload_local_voice,
        inputs=[upload_btn],
        outputs=[local_voice_dropdown, upload_status],
        api_name="upload_voice"
    )
    
    refresh_btn.click(
        fn=on_refresh_local_voices,
        outputs=[local_voice_dropdown],
        api_name="refresh_voices"
    )

    submit_btn.click(
        fn=generate_audio,
        inputs=[
            model_dropdown, 
            text_input, 
            language_dropdown, 
            instruct_input, 
            speaker_dropdown, 
            ref_audio_input, 
            ref_text_input,
            local_voice_dropdown
        ],
        outputs=[audio_output, load_status],
        api_name="generate_audio"
    )

    # 初始化加载
    demo.load(
        fn=on_model_select, 
        inputs=[model_dropdown], 
        outputs=[model_info, instruct_input, speaker_group, clone_group, speaker_dropdown, load_status]
    )

if __name__ == "__main__":
    port = int(os.environ.get("GRADIO_SERVER_PORT", "7860"))
    demo.launch(inbrowser=True, server_name="0.0.0.0", server_port=port)
