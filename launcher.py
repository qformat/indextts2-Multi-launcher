import os
import subprocess
import sys
import ctypes
import glob

def find_python_in_venv(venv_root):
    # 先按常见目录查找
    candidates = [
        os.path.join(venv_root, "Scripts", "pythonw.exe"),
        os.path.join(venv_root, "Scripts", "python.exe"),
        os.path.join(venv_root, "bin", "pythonw"),
        os.path.join(venv_root, "bin", "python"),
    ]
    for cand in candidates:
        if os.path.exists(cand):
            return cand
            
    # 常见目录找不到时，递归兜底（兼容用户手动移动/重命名 venv 结构）
    for root, dirs, files in os.walk(venv_root):
        for file in files:
            if file.lower() in ["pythonw.exe", "python.exe"]:
                return os.path.join(root, file)
    return None


def _has_launcher_ui_impl(base_dir: str) -> bool:
    """判断启动器 UI 模块是否存在（源码或 .pyd）。

    说明：发布包会屏蔽 `src/ui/launcher_ui.py`，仅保留编译后的 `.pyd`。
    因此这里不能只检查 `.py`。
    """
    py_path = os.path.join(base_dir, "src", "ui", "launcher_ui.py")
    if os.path.exists(py_path):
        return True

    pyd_glob = os.path.join(base_dir, "src", "ui", "launcher_ui*.pyd")
    return bool(glob.glob(pyd_glob))

def main():
    # 获取当前可执行文件所在目录（兼容 PyInstaller/普通脚本）
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    # 定位项目根目录与 venv
    possible_roots = [base_dir, os.path.dirname(base_dir)]
    venv_path = None
    
    for root in possible_roots:
        check_path = os.path.join(root, "venv")
        if os.path.exists(check_path):
            venv_path = check_path
            base_dir = root # Update base_dir to the project root
            break
            
    if not venv_path:
         # Default to current dir for error message consistency
         venv_path = os.path.join(base_dir, "venv")
    
    # 查找 venv 内的 python 可执行文件
    target_python = find_python_in_venv(venv_path) if venv_path else None

    # 未找到 python 时，弹窗输出更完整的调试信息
    if not target_python:
        debug_info = f"Base Dir: {base_dir}\n"
        debug_info += f"Venv Path: {venv_path} (Exists: {os.path.exists(venv_path)})\n"
        
        scripts_path = os.path.join(venv_path, "Scripts")
        if os.path.exists(scripts_path):
             try:
                 files = os.listdir(scripts_path)
                 # Filter for python files to show relevant ones
                 py_files = [f for f in files if 'python' in f.lower()]
                 debug_info += f"Scripts files: {', '.join(py_files) if py_files else 'No python executables found'}\n"
             except Exception as e:
                 debug_info += f"Error listing Scripts: {e}\n"
        else:
             debug_info += f"Scripts folder not found at: {scripts_path}\n"
             # Check if bin exists (linux/mac style venv on windows?)
             bin_path = os.path.join(venv_path, "bin")
             if os.path.exists(bin_path):
                 debug_info += f"Found 'bin' folder instead.\n"

        ctypes.windll.user32.MessageBoxW(0, f"无法找到Python环境。\n\n调试信息:\n{debug_info}", "启动错误", 16)
        return

    if not _has_launcher_ui_impl(base_dir):
        ctypes.windll.user32.MessageBoxW(
            0,
            (
                "无法找到启动器 UI 模块（源码或 .pyd）。\n\n"
                "期望存在以下任一文件：\n"
                f"- {os.path.join(base_dir, 'src', 'ui', 'launcher_ui.py')}\n"
                f"- {os.path.join(base_dir, 'src', 'ui', 'launcher_ui*.pyd')}\n\n"
                "如果你发布包屏蔽了源码，请确认已将对应 .pyd 一并放入发布目录。"
            ),
            "启动错误",
            16,
        )
        return

    # 重要：发布包可能只有 `.pyd`，不能用“运行 .py 脚本路径”的方式启动。
    # 这里统一改为 `-c` 直接 import 模块并调用 `ft.app(...)`，同时兼容源码与 `.pyd`。
    code = (
        "import src.ui.launcher_ui as _m; "
        "import flet as ft; "
        "ft.app(target=_m.main)"
    )
    cmd = [target_python, "-c", code] + sys.argv[1:]

    # Execute
    try:
        # 使用 CREATE_NO_WINDOW 隐藏控制台窗口（即使实际调用 python.exe 也不会弹黑框）
        creationflags = 0x08000000 
        subprocess.Popen(cmd, cwd=base_dir, creationflags=creationflags)
    except Exception as e:
        ctypes.windll.user32.MessageBoxW(0, f"启动应用程序失败:\n{str(e)}", "启动错误", 16)

if __name__ == "__main__":
    main()
