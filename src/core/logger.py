import logging
import logging.handlers
import sys
import platform
import subprocess
import os
from pathlib import Path
from datetime import datetime

class LogManager:
    """专业的日志管理器类"""
    
    def __init__(self, app_name="IndexTTS_Manager3.2", log_level=logging.INFO):
        self.app_name = app_name
        self.log_level = log_level
        self.logger = None
        self.console_handler = None
        self.file_handler = None
        self.gui_handler = None
        self.log_file_path = None
        self.gui_callback = None
        
        # 创建日志目录
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        
        self.setup_logger()
    
    def setup_logger(self):
        """设置日志记录器"""
        # 创建主日志记录器
        self.logger = logging.getLogger(self.app_name)
        self.logger.setLevel(self.log_level)
        
        # 清除现有处理器
        self.logger.handlers.clear()
        
        # 创建格式化器
        detailed_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
                        )
                        
        simple_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # 1. 控制台处理器
        self.console_handler = logging.StreamHandler(sys.stdout)
        self.console_handler.setLevel(logging.INFO)
        self.console_handler.setFormatter(simple_formatter)
        self.logger.addHandler(self.console_handler)
        
        # 2. 文件处理器（带轮转）
        self.log_file_path = self.log_dir / f"{self.app_name}_{datetime.now().strftime('%Y%m%d')}.log"
        self.file_handler = logging.handlers.RotatingFileHandler(
            self.log_file_path,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        self.file_handler.setLevel(logging.DEBUG)
        self.file_handler.setFormatter(detailed_formatter)
        self.logger.addHandler(self.file_handler)
        
        # 3. GUI处理器（自定义）
        self.gui_handler = GUILogHandler()
        self.gui_handler.setLevel(logging.INFO)
        self.gui_handler.setFormatter(simple_formatter)
        self.logger.addHandler(self.gui_handler)
    
    def set_gui_callback(self, callback):
        """设置GUI回调函数"""
        self.gui_callback = callback
        if self.gui_handler:
            self.gui_handler.set_callback(callback)
    
    def set_log_level(self, level):
        """设置日志级别"""
        self.log_level = level
        self.logger.setLevel(level)
        
        # 更新各处理器的级别
        if self.console_handler:
            self.console_handler.setLevel(max(level, logging.INFO))
        if self.file_handler:
            self.file_handler.setLevel(logging.DEBUG)
        if self.gui_handler:
            self.gui_handler.setLevel(max(level, logging.INFO))
    
    def log_system_info(self):
        """记录系统信息"""
        self.logger.info("=" * 60)
        self.logger.info(f"{self.app_name} 启动")
        self.logger.info("=" * 60)
        self.logger.info(f"Python版本: {sys.version}")
        self.logger.info(f"操作系统: {platform.system()} {platform.release()}")
        self.logger.info(f"处理器: {platform.processor()}")
        self.logger.info(f"工作目录: {os.getcwd()}")
        self.logger.info(f"日志文件: {self.log_file_path}")
        self.logger.info(f"日志级别: {logging.getLevelName(self.log_level)}")
        
        try:
            si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW; si.wShowWindow = 0
            smi = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True, timeout=4, creationflags=subprocess.CREATE_NO_WINDOW, startupinfo=si)
            if smi.returncode != 0 or not smi.stdout.strip():
                nv_path = Path("C:/Program Files/NVIDIA Corporation/NVSMI/nvidia-smi.exe")
                if nv_path.exists():
                    smi = subprocess.run([str(nv_path), "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True, timeout=4, creationflags=subprocess.CREATE_NO_WINDOW, startupinfo=si)
            gpu_info_logged = False
            if smi.returncode == 0 and smi.stdout.strip():
                names = [ln.strip() for ln in smi.stdout.splitlines() if ln.strip()]
                self.logger.info(f"检测到 NVIDIA GPU: {len(names)}")
                for i, name in enumerate(names):
                    self.logger.info(f"GPU {i}: {name}")
                gpu_info_logged = True
            is_frozen = bool(getattr(sys, 'frozen', False))
            if not is_frozen:
                try:
                    import torch
                    if torch.cuda.is_available():
                        gpu_count = torch.cuda.device_count()
                        self.logger.info(f"CUDA设备数量: {gpu_count}")
                        try:
                            for i in range(gpu_count):
                                self.logger.info(f"GPU {i}: {torch.cuda.get_device_name(i)}")
                        except Exception:
                            pass
                    elif not gpu_info_logged:
                        self.logger.info("CUDA不可用，将使用CPU模式")
                except Exception:
                    if not gpu_info_logged:
                        self.logger.info("PyTorch未安装或无法检测到GPU，将使用CPU模式")
        except Exception as e:
            self.logger.warning(f"检测GPU信息时出错: {e}")
        
        self.logger.info("=" * 60)
    
    def debug(self, message, *args, **kwargs):
        """调试级别日志"""
        self.logger.debug(message, *args, **kwargs)
    
    def info(self, message, *args, **kwargs):
        """信息级别日志"""
        self.logger.info(message, *args, **kwargs)
    
    def warning(self, message, *args, **kwargs):
        """警告级别日志"""
        self.logger.warning(message, *args, **kwargs)
    
    def error(self, message, *args, **kwargs):
        """错误级别日志"""
        self.logger.error(message, *args, **kwargs)
    
    def critical(self, message, *args, **kwargs):
        """严重错误级别日志"""
        self.logger.critical(message, *args, **kwargs)
    
    def exception(self, message, *args, **kwargs):
        """异常日志（包含堆栈跟踪）"""
        self.logger.exception(message, *args, **kwargs)


class GUILogHandler(logging.Handler):
    """自定义GUI日志处理器"""
    
    def __init__(self):
        super().__init__()
        self.callback = None
        self.log_buffer = []
        self.max_buffer_size = 1000
    
    def set_callback(self, callback):
        """设置GUI回调函数"""
        self.callback = callback
        
        # 如果有缓存的日志，立即发送
        if self.log_buffer and callback:
            for record in self.log_buffer:
                try:
                    callback(self.format(record), record.levelname)
                except Exception:
                    pass
            self.log_buffer.clear()
    
    def emit(self, record):
        """发送日志记录"""
        try:
            formatted_message = self.format(record)
            
            if self.callback:
                # 如果有回调函数，直接发送
                self.callback(formatted_message, record.levelname)
            else:
                # 否则缓存起来
                self.log_buffer.append(record)
                
                # 限制缓存大小
                if len(self.log_buffer) > self.max_buffer_size:
                    self.log_buffer = self.log_buffer[-self.max_buffer_size//2:]
                    
        except Exception:
            self.handleError(record)
