<div align="center">
  <h1>IndexTTS 2</h1>
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

**IndexTTS 2** is a breakthrough in emotionally expressive and duration-controlled auto-regressive zero-shot text-to-speech. It allows for precise control over speech duration and high-fidelity emotion synthesis.

This repository provides the official implementation and a user-friendly UI launcher for IndexTTS 2.

## ✨ Features

- **Emotion Control**: Highly expressive emotional speech synthesis.
- **Duration Control**: Precise synthesis duration control.
- **Zero-Shot Cloning**: Clone voices with just a short reference audio.
- **User-Friendly UI**: Built-in Flet-based GUI for easy operation.
- **Auto-Update**: Built-in automatic update mechanism to keep your application current.

## 🛠️ Installation

### Prerequisites
- Windows 10/11 (Recommended) or Linux
- Python 3.10+
- NVIDIA GPU with CUDA support (Recommended for faster inference)

### Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/qformat/indextts2-Multi-launcher.git
   cd indextts2-Multi-launcher
   ```

2. **Create a virtual environment (Optional but Recommended)**
   ```bash
   python -m venv venv
   # Windows
   .\venv\Scripts\activate
   # Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

## 📥 Model Download

You need to download the pre-trained models to run IndexTTS 2.

**Download Links:**
- [HuggingFace](https://huggingface.co/IndexTeam/IndexTTS-2.0)
- [ModelScope](https://modelscope.cn/models/IndexTeam/IndexTTS-2.0)

**Placement:**
Please place the downloaded model files into the corresponding directories:

- **Checkpoints**: Place main model checkpoints in `checkpoints/`.
- **BigVGAN**: Place BigVGAN vocoder files in `indextts/BigVGAN/`.
- **GPT Weights**: Place GPT weights in `gpt_weights/`.

*Note: Ensure the file structure matches the expected paths in the configuration.*

## 🚀 Usage

### Running the GUI
To start the application with the graphical user interface:

```bash
python launcher.py
```
Or directly:
```bash
python src/main.py
```

### Configuration
The application uses `config.json` for configuration. A `config_example.json` is provided as a template. The UI allows you to modify most settings directly.

## 📚 Citation

If you use this code or model in your research, please cite our paper:

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
  <h1>IndexTTS 2</h1>
</div>

## 📖 简介

**IndexTTS 2** 是一个在情感表达和时长控制方面取得突破的自回归零样本语音合成系统。它支持对语音时长的精确控制以及高保真的情感合成。

本仓库提供了 IndexTTS 2 的官方实现以及一个用户友好的启动器 UI。

## ✨ 特性

- **情感控制**：支持高表现力的情感语音合成。
- **时长控制**：支持精确的合成时长控制。
- **零样本克隆**：仅需简短的参考音频即可克隆声音。
- **友好 UI**：内置基于 Flet 的图形用户界面，操作便捷。
- **自动更新**：内置自动更新机制，保持应用为最新版本。

## 🛠️ 安装指南

### 前置要求
- Windows 10/11 (推荐) 或 Linux
- Python 3.10+
- NVIDIA GPU 并支持 CUDA (推荐用于加速推理)

### 安装步骤

1. **克隆仓库**
   ```bash
   git clone https://github.com/qformat/indextts2-Multi-launcher.git
   cd indextts2-Multi-launcher
   ```

2. **创建虚拟环境 (可选但推荐)**
   ```bash
   python -m venv venv
   # Windows
   .\venv\Scripts\activate
   # Linux
   source venv/bin/activate
   ```

3. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

## 📥 模型下载

运行 IndexTTS 2 需要下载预训练模型。

**下载链接：**
- [HuggingFace](https://huggingface.co/IndexTeam/IndexTTS-2.0)
- [ModelScope (魔搭社区)](https://modelscope.cn/models/IndexTeam/IndexTTS-2.0)

**文件放置：**
请将下载的模型文件放入对应的目录中：

- **Checkpoints**: 将主模型权重放入 `checkpoints/` 目录。
- **BigVGAN**: 将 BigVGAN 声码器文件放入 `indextts/BigVGAN/` 目录。
- **GPT Weights**: 将 GPT 权重放入 `gpt_weights/` 目录。

*注意：请确保文件结构符合配置中的路径要求。*

## 🚀 使用方法

### 启动 GUI
使用以下命令启动带有图形界面的应用程序：

```bash
python launcher.py
```
或者直接运行：
```bash
python src/main.py
```

### 配置
程序使用 `config.json` 进行配置。仓库中提供了一个 `config_example.json` 作为模板。您可以通过 UI 界面直接修改大多数设置。

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
