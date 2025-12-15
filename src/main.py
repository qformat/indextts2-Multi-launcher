import os
import sys
from pathlib import Path

# 将项目根目录添加到 sys.path，确保能正确导入 src 模块
# 假设当前文件位于 <project_root>/src/main.py
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import flet as ft
from src.ui.app import IndexTTSManagerFlet

def main():
    """主函数"""
    try:
        import multiprocessing as _mp
        _mp.freeze_support()
    except Exception:
        pass
    if os.name == 'nt' and bool(getattr(sys, 'frozen', False)):
        try:
            import ctypes
            _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\IndexTTSManagerFletMutex")
            if ctypes.windll.kernel32.GetLastError() == 183:
                return
        except Exception:
            pass
    
    app = IndexTTSManagerFlet()
    ft.app(target=app.main, view=ft.AppView.FLET_APP)

if __name__ == "__main__":
    main()
