import json
from pathlib import Path

class ConfigManager:
    """配置文件管理器"""
    
    def __init__(self, config_file="config.json"):
        self.config_file = Path(config_file)
        self.config = {}
        self.load_config()
    
    def load_config(self):
        """加载配置文件"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                print(f"配置文件已加载: {self.config_file}")
                # 兼容性：确保新增键存在
                if "subtitle_roles" not in self.config:
                    self.config["subtitle_roles"] = {}
                # 新增：启动时是否重置行情感向量（缺省为True）
                if "reset_subtitle_line_emotions_on_start" not in self.config:
                    self.config["reset_subtitle_line_emotions_on_start"] = True
                # 新增：TTS接口模式与远程API地址（缺省为本地模式）
                if "tts_api_mode" not in self.config:
                    self.config["tts_api_mode"] = "local"
                if "tts_remote_base_url" not in self.config:
                    self.config["tts_remote_base_url"] = ""
                # 新增：AI接口模式与自定义Base URL（默认使用OpenAI v1）
                if "ai_api_url_mode" not in self.config:
                    self.config["ai_api_url_mode"] = "default"
                if "ai_custom_base_url" not in self.config:
                    self.config["ai_custom_base_url"] = ""
                if "generation_history" not in self.config:
                    self.config["generation_history"] = []
                if "voice_gender_map" not in self.config:
                    self.config["voice_gender_map"] = {}
                if "voice_custom_names" not in self.config:
                    self.config["voice_custom_names"] = {}
                if "save_mp3" not in self.config:
                    self.config["save_mp3"] = False
                # 新增：更新地址
                if "update_url" not in self.config:
                    self.config["update_url"] = "https://gitee.com/qformat/indextts2-Multi-launcher/raw/master/version.json"
            else:
                # 创建默认配置
                self.config = {
                    "theme": "system",
                    "log_level": "INFO",
                    "last_voice": None,
                    "last_subtitle_voice": None,
                    "window_size": {"width": 1200, "height": 800},
                    "auto_save": True,
                    "audio_interval": 100,
                    "speaking_speed": 1.0,
                    "volume_percent": 100,
                    "ai_adjust_speed": False,
                    "ai_adjust_emotion": True,
                    # 新增：字幕角色持久化（{role_name: voice_path}）
                    "subtitle_roles": {},
                    # 新增：启动时是否重置行情感向量（默认开启一次性重置）
                    "reset_subtitle_line_emotions_on_start": True,
                    # 新增：TTS接口模式与远程API地址
                    "tts_api_mode": "local",
                    "tts_remote_base_url": "",
                    # 新增：AI接口模式与自定义Base URL（默认使用OpenAI v1）
                    "ai_api_url_mode": "default",
                    "ai_custom_base_url": "",
                    "generation_history": [],
                    "voice_gender_map": {},
                    "voice_custom_names": {},
                    "save_mp3": False,
                    "update_url": "https://gitee.com/qformat/indextts2-Multi-launcher/raw/master/version.json"
                }
                self.save_config()
                print(f"创建默认配置文件: {self.config_file}")
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            # 使用默认配置
            self.config = {
                "theme": "system",
                "log_level": "INFO",
                "last_voice": None,
                "last_subtitle_voice": None,
                "window_size": {"width": 1200, "height": 800},
                "auto_save": True,
                "audio_interval": 100,
                "speaking_speed": 1.0,
                "volume_percent": 100,
                "ai_adjust_speed": False,
                "ai_adjust_emotion": True,
                "subtitle_roles": {},
                "reset_subtitle_line_emotions_on_start": True,
                "tts_api_mode": "local",
                "tts_remote_base_url": "",
                "ai_api_url_mode": "default",
                "ai_custom_base_url": "",
                "generation_history": [],
                "voice_gender_map": {},
                "voice_custom_names": {},
                "save_mp3": False,
                "update_url": "https://gitee.com/qformat/indextts2-Multi-launcher/raw/master/version.json"
            }
    
    def save_config(self):
        """保存配置文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            print(f"配置已保存到: {self.config_file}")
            return True
        except Exception as e:
            print(f"保存配置文件失败: {e}")
            return False
    
    def get(self, key, default=None):
        """获取配置值"""
        return self.config.get(key, default)
    
    def set(self, key, value):
        """设置配置值"""
        self.config[key] = value
        if self.config.get("auto_save", True):
            self.save_config()
    
    def update(self, updates):
        """批量更新配置"""
        self.config.update(updates)
        if self.config.get("auto_save", True):
            self.save_config()
    
    def save(self):
        """保存配置文件（别名方法）"""
        return self.save_config()
