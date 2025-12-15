import os
import sys
import argparse
import subprocess
import time
import zipfile
import shutil
import tempfile
import urllib.request

def download_file(url, dest):
    print(f"正在下载更新包: {url}")
    try:
        with urllib.request.urlopen(url) as response, open(dest, 'wb') as out_file:
            total_size = int(response.getheader('Content-Length') or 0)
            block_size = 8192
            downloaded = 0
            while True:
                buffer = response.read(block_size)
                if not buffer:
                    break
                downloaded += len(buffer)
                out_file.write(buffer)
                if total_size > 0:
                    percent = downloaded * 100 / total_size
                    print(f"\r下载进度: {percent:.1f}%", end='')
        print("\n下载完成。")
    except Exception as e:
        print(f"\n下载失败: {e}")
        raise

def extract_zip(zip_path, extract_to):
    print("正在解压...")
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        print("解压完成。")
    except Exception as e:
        print(f"解压失败: {e}")
        raise

def install_update(source_dir, target_dir):
    print("正在安装更新...")
    # 处理 GitHub/Gitee 压缩包通常包含一层顶层目录的情况
    items = os.listdir(source_dir)
    if len(items) == 1 and os.path.isdir(os.path.join(source_dir, items[0])):
        source_dir = os.path.join(source_dir, items[0])
    
    # 使用 xcopy 或 robocopy (Windows)
    # 这里使用 shutil 简单处理，但为了覆盖正在运行的文件（虽然本进程是 python，但主程序已关闭），
    # Windows 上覆盖正在使用的 DLL/PYD 可能会有问题。
    # 既然是 CLI 更新，我们通常建议用户关闭所有相关程序。
    # 本脚本由 launcher 启动，launcher 应该已经退出了吗？
    # 不，launcher 启动了这个脚本（新进程），然后 launcher 自己应该退出。
    
    cmd = f'xcopy "{source_dir}" "{target_dir}" /s /e /y /i'
    print(f"执行命令: {cmd}")
    ret = subprocess.call(cmd, shell=True)
    if ret != 0:
        print("更新文件复制失败。")
        raise Exception("Copy failed")
    print("安装完成。")

def main():
    parser = argparse.ArgumentParser(description="IndexTTS2 Updater CLI")
    parser.add_argument("--url", required=True, help="Update zip URL")
    parser.add_argument("--target", required=True, help="Target directory")
    parser.add_argument("--pid", type=int, help="Parent PID to wait/kill")
    parser.add_argument("--exe", required=True, help="Executable to restart")
    
    args = parser.parse_args()
    
    print("=== IndexTTS2 自动更新程序 ===")
    
    if args.pid:
        print(f"正在等待主程序 (PID: {args.pid}) 退出...")
        try:
            # 尝试终止父进程
            subprocess.run(f"taskkill /F /PID {args.pid}", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        except Exception:
            pass
        time.sleep(2)
        
    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, "update.zip")
    extract_dir = os.path.join(temp_dir, "extracted")
    
    try:
        download_file(args.url, zip_path)
        extract_zip(zip_path, extract_dir)
        install_update(extract_dir, args.target)
        
        print("更新成功！正在重启程序...")
        time.sleep(2)
        
        # 重启程序
        # args.exe 是 python 路径还是 launcher 路径？
        # 如果是 python 脚本启动，args.exe 应该是 python.exe，后面跟 script
        # 这里假设 args.exe 是完整的启动命令或可执行文件
        
        # 解析 exe 参数
        # 如果 args.exe 包含空格，需要处理
        subprocess.Popen(f'start "" {args.exe}', shell=True)
        
    except Exception as e:
        print(f"错误: {e}")
        print("更新失败。请手动下载更新。")
        os.system("pause")
    finally:
        try:
            shutil.rmtree(temp_dir)
        except:
            pass

if __name__ == "__main__":
    main()
