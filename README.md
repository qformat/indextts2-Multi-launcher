<div align="center">
  <h1>IndexTTS 2-Multi-launcher</h1>
  <p>
    <a href="https://github.com/index-tts/index-tts">
        <img src="https://img.shields.io/badge/GitHub-Code-orange?logo=github"/>
    </a>
    <a href="https://huggingface.co/IndexTeam/IndexTTS-2.0">
        <img src="https://img.shields.io/badge/HuggingFace-Model-blue?logo=huggingface" />
    </a>
    <a href="https://modelscope.cn/models/IndexTeam/IndexTTS-2.0">
        <img src="https://img.shields.io/badge/ModelScope-Model-purple?logo=modelscope"/>
    </a>
  </p>
  <p>
    <strong>English</strong> | <a href="#中文说明">中文说明</a>
  </p>
</div>

## 📖 Introduction

**IndexTTS 2-Multi-launcher** is a state-of-the-art auto-regressive text-to-speech system that achieves a breakthrough in **emotional expressiveness** and **duration control**.

Unlike traditional TTS models, IndexTTS 2-Multi-launcher allows you to:

- **Control Emotion**: Generate speech with rich, specific emotions (e.g., happy, angry, sad, etc.) using text prompts or reference audio.
- **Control Duration**: Precisely dictate how long the spoken segment should be, enabling perfect synchronization for video dubbing.
- **Zero-Shot Cloning**: Clone a speaker's voice using only a short audio sample (10-15 seconds recommended).

This repository contains the official implementation along with a **built-in graphical user interface (GUI)** for easy inference and batch processing.

## ✨ Features

- **🎭 Rich Emotion Support**: Automatically detects emotion from text or allows manual specification via vectors.
- **⏱️ Duration Control**: Specify the exact duration for the generated speech.
- **🎙️ Zero-Shot Voice Cloning**: High-fidelity voice cloning with just a single reference audio.
- **🖥️ User-Friendly GUI**: A modern, dark-themed UI built with Flet, supporting:
  - Real-time generation log viewing.
  - History management and playback.
  - Batch processing editor.
  - Auto-update capability.
- **🚀 Efficient Inference**: Optimized for NVIDIA GPUs with optional CUDA kernel support for BigVGAN.

## 🛠️ Installation

### Prerequisites

- **OS**: Windows 10/11 (Recommended) or Linux.
- **Python**: Version 3.10 is recommended.
- **GPU**: NVIDIA GPU with CUDA 11.8+ (Strongly recommended for performance).

### Steps

1. **Clone the repository**

   ```bash
   git clone https://github.com/qformat/indextts2-Multi-launcher.git
   cd indextts2-Multi-launcher
   ```

2. **Create a virtual environment**

   ```bash
   python -m venv venv
   # Activate:
   # Windows:
   .\venv\Scripts\activate
   # Linux:
   source venv/bin/activate
   ```

3. **Install dependencies**

   ```bash
   # Install PyTorch with CUDA support first (adjust for your CUDA version)
   pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118

   # Install other requirements
   pip install -r requirements.txt
   ```

## 📥 Model Download & Setup

IndexTTS 2-Multi-launcher requires several model files to function. Some can be downloaded automatically, but the core models **must be downloaded manually**.

### 1. Core Models (Manual Download Required)

Download these files from [HuggingFace](https://huggingface.co/IndexTeam/IndexTTS-2.0) or [ModelScope](https://modelscope.cn/models/IndexTeam/IndexTTS-2.0) and place them in the `checkpoints/` directory:

| Filename    | Description             | Target Path             |
| :---------- | :---------------------- | :---------------------- |
| `gpt.pth`   | Main AR model weights   | `checkpoints/gpt.pth`   |
| `s2mel.pth` | Diffusion model weights | `checkpoints/s2mel.pth` |
| `feat1.pt`  | Speaker feature matrix  | `checkpoints/feat1.pt`  |
| `feat2.pt`  | Emotion feature matrix  | `checkpoints/feat2.pt`  |

### 2. Auxiliary Models (Auto-Download / Manual)

These models are handled by third-party libraries (Transformers, BigVGAN). The program will attempt to download them automatically if missing. **If you have network issues**, download them manually and place them as follows:

| Model Name       | Source                                | Manual Path (Recommended)                                          |
| :--------------- | :------------------------------------ | :----------------------------------------------------------------- |
| **Qwen Emotion** | `Qwen/Qwen1.5-0.5B-Chat`              | `checkpoints/hub/qwen0.6bemo4-merge` (Extract content here)        |
| **BigVGAN**      | `nvidia/bigvgan_v2_22khz_80band_256x` | `checkpoints/nvidia_bigvgan_v2_22khz_80band_256x`                  |
| **W2V-BERT**     | `facebook/w2v-bert-2.0`               | `checkpoints/hub/models--facebook--w2v-bert-2.0` (HF Cache format) |
| **MaskGCT**      | `amphion/MaskGCT`                     | `checkpoints/amphion_MaskGCT/semantic_codec/model.safetensors`     |

> **Note on Qwen**: The config expects the Qwen emotion model at `checkpoints/hub/qwen0.6bemo4-merge`. Please rename the folder if necessary after downloading.

### 🌐 Network Issues? Use a Mirror

If you cannot access Hugging Face, you can use a mirror site. Set the environment variable before running the program:

**PowerShell:**

```powershell
$env:HF_ENDPOINT = "https://hf-mirror.com"
python launcher.py
```

**Bash:**

```bash
export HF_ENDPOINT=https://hf-mirror.com
python src/main.py
```

## 🚀 Usage

### Start the GUI

Run the launcher script to start the application:

```bash
python launcher.py
```

### Basic Operation

1. **Select Models**: Ensure the checkpoints are loaded in the settings.
2. **Reference Audio**: Upload a clear speech sample (10-15s) of the voice you want to clone.
3. **Input Text**: Type the text you want to synthesize.
4. **Generate**: Click "Generate" and wait for the result.
5. **History**: View and play past generations in the "History" tab.

## 📚 Citation

If you use this code or model in your research, please cite:

```bibtex
@article{zhou2025indextts2,
  title={IndexTTS2: A Breakthrough in Emotionally Expressive and Duration-Controlled Auto-Regressive Zero-Shot Text-to-Speech},
  author={Siyi Zhou, Yiquan Zhou, Yi He, Xun Zhou, Jinchao Wang, Wei Deng, Jingchen Shu},
  journal={arXiv preprint arXiv:2506.21619},
  year={2025}
}
```

---

<div id="中文说明"></div>

<div align="center">
  <h1>IndexTTS 2-Multi-launcher</h1>
</div>

## 📖 简介

**IndexTTS 2-Multi-launcher** 是一个在**情感表达**和**时长控制**方面取得突破的自回归零样本语音合成系统。

与传统的 TTS 模型不同，IndexTTS 2-Multi-launcher 允许您：

- **情感控制**：通过文本提示或参考音频生成具有丰富、特定情感（如开心、愤怒、悲伤等）的语音。
- **时长控制**：精确指定语音片段的时长，完美适配视频配音对口型的需求。
- **零样本克隆**：仅需一段简短的参考音频（推荐 10-15 秒）即可实现高保真声音克隆。

本仓库包含了官方实现代码，并内置了一个**图形用户界面 (GUI)**，方便用户进行推理和批量处理。

## ✨ 特性

- **🎭 丰富的情感支持**：支持从文本自动检测情感，或通过向量手动指定。
- **⏱️ 时长控制**：支持指定生成的语音时长。
- **🎙️ 零样本声音克隆**：单段参考音频即可克隆。
- **🖥️ 友好的 GUI 界面**：基于 Flet 构建的现代化暗色主题界面，支持：
  - 实时日志查看。
  - 生成历史管理与回放。
  - 批量生成编辑器。
  - 自动更新功能。
- **🚀 高效推理**：针对 NVIDIA GPU 优化，支持 BigVGAN CUDA 算子加速。

## 🛠️ 安装指南

### 前置要求

- **操作系统**: Windows 10/11 (推荐) 或 Linux。
- **Python**: 推荐使用 Python 3.10。
- **GPU**: NVIDIA 显卡，建议安装 CUDA 11.8+ 以获得最佳性能。

### 安装步骤

1. **克隆仓库**

   ```bash
   git clone https://github.com/qformat/indextts2-Multi-launcher.git
   cd indextts2-Multi-launcher
   ```

2. **创建虚拟环境**

   ```bash
   python -m venv venv
   # 激活环境:
   # Windows:
   .\venv\Scripts\activate
   # Linux:
   source venv/bin/activate
   ```

3. **安装依赖**

   ```bash
   # 首先安装带 CUDA 支持的 PyTorch (根据您的 CUDA 版本调整)
   pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118

   # 安装其他依赖
   pip install -r requirements.txt
   ```

## 📥 模型下载与设置

IndexTTS 2-Multi-launcher 需要多个模型文件才能运行。部分模型可以自动下载，但**核心模型必须手动下载**。

### 1. 核心模型 (必须手动下载)

请从 [HuggingFace](https://huggingface.co/IndexTeam/IndexTTS-2.0) 或 [ModelScope (魔搭)](https://modelscope.cn/models/IndexTeam/IndexTTS-2.0) 下载以下文件，并放入 `checkpoints/` 目录：

| 文件名      | 说明           | 目标路径                |
| :---------- | :------------- | :---------------------- |
| `gpt.pth`   | GPT 主模型权重 | `checkpoints/gpt.pth`   |
| `s2mel.pth` | 扩散模型权重   | `checkpoints/s2mel.pth` |
| `feat1.pt`  | 说话人特征矩阵 | `checkpoints/feat1.pt`  |
| `feat2.pt`  | 情感特征矩阵   | `checkpoints/feat2.pt`  |

### 2. 辅助模型 (自动/手动)

这些模型由第三方库（Transformers, BigVGAN）管理。如果缺失，程序会尝试自动下载。**如果您的网络连接 HuggingFace 有困难**，请手动下载并按如下路径放置：

| 模型名称         | 原始来源                              | 推荐手动放置路径                                               |
| :--------------- | :------------------------------------ | :------------------------------------------------------------- |
| **Qwen Emotion** | `Qwen/Qwen1.5-0.5B-Chat`              | `checkpoints/hub/qwen0.6bemo4-merge` (解压至此)                |
| **BigVGAN**      | `nvidia/bigvgan_v2_22khz_80band_256x` | `checkpoints/nvidia_bigvgan_v2_22khz_80band_256x`              |
| **W2V-BERT**     | `facebook/w2v-bert-2.0`               | `checkpoints/hub/models--facebook--w2v-bert-2.0` (HF 缓存格式) |
| **MaskGCT**      | `amphion/MaskGCT`                     | `checkpoints/amphion_MaskGCT/semantic_codec/model.safetensors` |

> **注意**: Qwen 情感模型在配置文件中默认指向 `checkpoints/hub/qwen0.6bemo4-merge`，手动下载后请确保文件夹名称一致。

### 🌐 无法访问 HuggingFace？使用镜像站

如果您无法连接 Hugging Face，可以使用国内镜像站。在运行程序前设置环境变量：

**PowerShell (Windows):**

```powershell
$env:HF_ENDPOINT = "https://hf-mirror.com"
python launcher.py
```

**Bash (Linux):**

```bash
export HF_ENDPOINT=https://hf-mirror.com
python src/main.py
```

## 🚀 使用方法

### 启动 GUI

运行启动脚本打开程序：

```bash
python launcher.py
```

### 基本操作

1. **选择模型**：在设置页确认模型路径正确。
2. **参考音频**：上传一段清晰的语音（10-15 秒）作为克隆对象。
3. **输入文本**：输入您想要合成的文字。
4. **生成**：点击“生成”按钮，等待片刻。
5. **历史记录**：在“生成记录”页面查看和播放生成的音频。

## 📚 引用

如果您在研究中使用了本代码或模型，请引用我们的论文：

```bibtex
@article{zhou2025indextts2,
  title={IndexTTS2: A Breakthrough in Emotionally Expressive and Duration-Controlled Auto-Regressive Zero-Shot Text-to-Speech},
  author={Siyi Zhou, Yiquan Zhou, Yi He, Xun Zhou, Jinchao Wang, Wei Deng, Jingchen Shu},
  journal={arXiv preprint arXiv:2506.21619},
  year={2025}
}
```
