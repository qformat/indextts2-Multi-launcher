
import os
import time
import torch
import sys
from transformers import AutoTokenizer

# Add project root to sys.path
sys.path.append(os.getcwd())

# Define model path
model_dir = r"h:\index-tts-2-6G-0914\index-tts-2\checkpoints\hub\Qwen3-TTS-12Hz-1.7B-VoiceDesign"

print(f"Checking environment...")
print(f"Python: {sys.version}")
print(f"Torch: {torch.__version__}")
print(f"CUDA Available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"Device: {torch.cuda.get_device_name(0)}")

print("\nImporting qwen_tts...")
try:
    import qwen_tts
    from qwen_tts.inference.qwen3_tts_tokenizer import Qwen3TTSTokenizer
    from qwen_tts.core.models.modeling_qwen3_tts import Qwen3TTSForConditionalGeneration
    print("qwen_tts imported successfully.")
except ImportError as e:
    print(f"qwen_tts import failed: {e}")
    sys.exit(1)

print(f"\nLoading Tokenizer from {model_dir}...")
start_time = time.time()
try:
    # Use AutoTokenizer for text
    tokenizer = AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True)
    print(f"Tokenizer loaded in {time.time() - start_time:.2f}s")
    
    # Set chat template if missing
    if not getattr(tokenizer, 'chat_template', None):
        print("Tokenizer chat_template is missing, setting default Qwen ChatML template.")
        tokenizer.chat_template = "{% for message in messages %}{{'<|im_start|>' + message['role'] + '\n' + message['content'] + '<|im_end|>' + '\n'}}{% endfor %}{% if add_generation_prompt %}{{ '<|im_start|>assistant\n' }}{% endif %}"

except Exception as e:
    print(f"Tokenizer loading failed: {e}")
    sys.exit(1)

print(f"\nLoading Model from {model_dir}...")
start_time = time.time()
try:
    model = Qwen3TTSForConditionalGeneration.from_pretrained(
        model_dir,
        device_map="cuda" if torch.cuda.is_available() else "cpu",
        torch_dtype=torch.float16
    ).eval()
    print(f"Model loaded in {time.time() - start_time:.2f}s")
except Exception as e:
    print(f"Model loading failed: {e}")
    sys.exit(1)

# Check flash attention
print(f"\nChecking model configuration for attention implementation...")
try:
    print(f"Model config _attn_implementation: {getattr(model.config, '_attn_implementation', 'Unknown')}")
except:
    pass

print(f"\nPreparing test input...")
text = "Hello, this is a test."
voice_description = "A clear female voice."

messages = [
    {"role": "system", "content": "You are a text-to-speech synthesis model. Please generate speech according to the user's text and voice description."},
    {"role": "user", "content": f"(Voice Description: {voice_description}) {text}"}
]

text_ids = tokenizer.apply_chat_template(
    messages, 
    return_tensors="pt", 
    add_generation_prompt=True
).to(model.device)

print(f"Input shape: {text_ids.shape}")

print(f"\nStarting generation (max_new_tokens=100)...")
start_time = time.time()
try:
    with torch.no_grad():
        # Qwen3TTS expect list of tensors, each with shape [1, L]
        input_ids_list = [text_ids[i:i+1] for i in range(text_ids.shape[0])]
        
        generated_ids = model.generate(
            input_ids=input_ids_list,
            languages=["auto"] * len(input_ids_list),
            max_new_tokens=100, # Keep it short for testing
            do_sample=True,
            temperature=0.7,
        )
    print(f"Generation completed in {time.time() - start_time:.2f}s")
    print(f"Output shape: {generated_ids.shape}")
except Exception as e:
    print(f"Generation failed: {e}")
    import traceback
    traceback.print_exc()

print("\nDone.")
