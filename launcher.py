import os
import subprocess
import sys
import ctypes

def find_python_in_venv(venv_root):
    # Standard check first
    candidates = [
        os.path.join(venv_root, "Scripts", "pythonw.exe"),
        os.path.join(venv_root, "Scripts", "python.exe"),
        os.path.join(venv_root, "bin", "pythonw"),
        os.path.join(venv_root, "bin", "python"),
    ]
    for cand in candidates:
        if os.path.exists(cand):
            return cand
            
    # Recursive search if standard locations fail
    for root, dirs, files in os.walk(venv_root):
        for file in files:
            if file.lower() in ["pythonw.exe", "python.exe"]:
                return os.path.join(root, file)
    return None

def main():
    # Get the directory where the executable is located
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    # Define paths
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
    
    # Try to find python executable
    target_python = find_python_in_venv(venv_path) if venv_path else None
    
    # 修改入口为启动器UI界面
    main_script = os.path.join(base_dir, "src", "ui", "launcher_ui.py")

    # If not found, show detailed error
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

    if not os.path.exists(main_script):
        ctypes.windll.user32.MessageBoxW(0, f"无法找到程序入口脚本。\n请确保 'src/ui/launcher_ui.py' 位于以下路径:\n{base_dir}", "启动错误", 16)
        return

    # Prepare command
    # Pass all arguments received by the launcher to the script
    cmd = [target_python, main_script] + sys.argv[1:]

    # Execute
    try:
        # Use CREATE_NO_WINDOW flag to hide console window
        # This ensures even if python.exe is used, no black window appears
        creationflags = 0x08000000 
        subprocess.Popen(cmd, cwd=base_dir, creationflags=creationflags)
    except Exception as e:
        ctypes.windll.user32.MessageBoxW(0, f"启动应用程序失败:\n{str(e)}", "启动错误", 16)

if __name__ == "__main__":
    main()
