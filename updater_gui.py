import flet as ft
import sys
import os
import subprocess
import shutil
import zipfile
import requests
import tempfile
import threading
import time
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="Update zip URL")
    parser.add_argument("--target", required=True, help="Target directory to update")
    parser.add_argument("--pid", type=int, help="Parent process ID to kill")
    parser.add_argument("--exe", required=True, help="Path to executable to restart")
    args = parser.parse_args()

    def update_task(page):
        try:
            page.add(ft.Text(f"正在更新...", size=20, weight=ft.FontWeight.BOLD))
            status = ft.Text("准备中...", size=14)
            pb = ft.ProgressBar(width=400)
            page.add(status, pb)
            page.update()

            # 1. Kill parent process
            if args.pid:
                status.value = "正在关闭旧版本..."
                page.update()
                try:
                    # Try graceful kill first, then force
                    subprocess.run(f"taskkill /PID {args.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    time.sleep(1)
                    subprocess.run(f"taskkill /F /PID {args.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass
            
            # 2. Download
            status.value = "正在下载更新包..."
            page.update()
            
            temp_dir = tempfile.mkdtemp()
            zip_path = os.path.join(temp_dir, "update.zip")
            
            resp = requests.get(args.url, stream=True, timeout=60)
            resp.raise_for_status()
            total_size = int(resp.headers.get('content-length', 0))
            downloaded = 0
            
            with open(zip_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        pb.value = downloaded / total_size
                        page.update()
            
            # 3. Extract
            status.value = "正在解压..."
            pb.value = None # Indeterminate
            page.update()
            
            extract_dir = os.path.join(temp_dir, "extracted")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
                
            # Handle GitHub archive structure (root folder)
            content_dir = extract_dir
            items = os.listdir(extract_dir)
            if len(items) == 1 and os.path.isdir(os.path.join(extract_dir, items[0])):
                content_dir = os.path.join(extract_dir, items[0])
            
            # 4. Copy files
            status.value = "正在安装更新..."
            page.update()
            
            # Copy all files from content_dir to target_dir
            # Use xcopy for better reliability on Windows or shutil
            # Using shutil here for pythonic way, but we need to handle open files?
            # Since we killed the main process, it should be fine.
            # But we are running THIS script using python from the same env?
            # If this script is standalone exe, it's fine. If it's python script, 
            # we must ensure we don't overwrite used DLLs if possible.
            # Usually xcopy /y is robust.
            
            # Use robocopy for robustness
            cmd = f'robocopy "{content_dir}" "{args.target}" /E /IS /IT /MOVE /NFL /NDL /NJH /NJS'
            # robocopy returns non-zero on success (1=files copied), so we ignore return code
            subprocess.run(cmd, shell=True) 
            
            # 5. Restart
            status.value = "更新完成，正在重启..."
            pb.value = 1
            page.update()
            time.sleep(1)
            
            subprocess.Popen(f'start "" "{args.exe}"', shell=True)
            page.window_close()
            
        except Exception as ex:
            status.value = f"更新失败: {ex}"
            status.color = "red"
            pb.value = 0
            page.add(ft.ElevatedButton("关闭", on_click=lambda _: page.window_close()))
            page.update()

    ft.app(target=update_task, view=ft.AppView.FLET_APP, title="IndexTTS 更新程序")

if __name__ == "__main__":
    main()
