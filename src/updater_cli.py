import os
import sys
import argparse
import subprocess
import time
import zipfile
import shutil
import tempfile
import urllib.request
import traceback
import psutil

def kill_process_tree(pid):
    """
    强制结束进程及其子进程
    """
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for child in children:
            try:
                print(f"终止子进程: {child.pid}")
                child.kill()
            except psutil.NoSuchProcess:
                pass
        print(f"终止主进程: {pid}")
        parent.kill()
        parent.wait(5) # 等待进程结束
    except psutil.NoSuchProcess:
        print(f"进程 {pid} 已不存在。")
    except Exception as e:
        print(f"终止进程 {pid} 失败: {e}")

def download_file(url, dest):
    print(f"正在下载更新包: {url}")

    # 内部实际执行下载的函数，方便在原链接/备用链接之间重用逻辑
    def _do_download(current_url):
        print(f"开始请求: {current_url}")
        # Gitee Raw 文件下载需要处理防盗链，有时直接请求会403
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Connection': 'keep-alive'
        }

        req = urllib.request.Request(current_url, headers=headers)

        # 设置 30秒超时
        with urllib.request.urlopen(req, timeout=30) as response, open(dest, 'wb') as out_file:
            # 检查 HTTP 状态码
            if response.getcode() != 200:
                raise Exception(f"HTTP Error {response.getcode()}")

            # 检查 Content-Type
            content_type = response.getheader('Content-Type', '')
            print(f"响应类型: {content_type}")
            if 'text/html' in content_type:
                print("警告: 下载的内容似乎是 HTML 网页，可能是登录页面或 404 页面。")

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
                    print(f"\r下载进度: {percent:.1f}%", end='', flush=True)
            print("\n下载完成。", flush=True)

    try:
        try:
            # 先按原始地址下载（例如 raw/master/update.zip）
            _do_download(url)
        except Exception as e:
            # 如果是 Gitee raw 且返回 403，则尝试改用仓库打包链接
            msg = str(e)
            if "gitee.com" in url and "/raw/" in url and ("403" in msg or "Forbidden" in msg):
                print("检测到 Gitee raw 链接 403，尝试仓库压缩包链接...")
                try:
                    # 将 .../raw/master/update.zip 转换为 .../repository/archive/master.zip
                    prefix = url.split("/raw/")[0]
                    alt_url = prefix + "/repository/archive/master.zip"
                    print(f"备用链接: {alt_url}")
                    _do_download(alt_url)
                except Exception as e2:
                    print(f"\n备用链接下载失败: {e2}")
                    raise
            else:
                # 其他错误直接抛出
                raise
    except Exception as e:
        print(f"\n下载失败: {e}")
        raise

def extract_zip(zip_path, extract_to):
    print("正在解压...", flush=True)
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        print("解压完成。", flush=True)
    except zipfile.BadZipFile:
        print("\n[错误] 下载的文件不是有效的 ZIP 包。", flush=True)
        try:
            with open(zip_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(500)
                print(f"文件前500个字符内容如下(可能包含错误信息):\n{'-'*20}\n{content}\n{'-'*20}", flush=True)
        except:
            pass
        raise
    except Exception as e:
        print(f"解压失败: {e}")
        raise

def install_update(source_dir, target_dir):
    print("正在安装更新...", flush=True)
    items = os.listdir(source_dir)
    if len(items) == 1 and os.path.isdir(os.path.join(source_dir, items[0])):
        source_dir = os.path.join(source_dir, items[0])
    
    # Windows copy command
    cmd = f'xcopy "{source_dir}" "{target_dir}" /s /e /y /i'
    print(f"执行命令: {cmd}")
    ret = subprocess.call(cmd, shell=True)
    if ret != 0:
        print("更新文件复制失败。")
        raise Exception("Copy failed")
    print("安装完成。", flush=True)

def main():
    try:
        parser = argparse.ArgumentParser(description="IndexTTS2 Updater CLI")
        parser.add_argument("--url", required=True, help="Update zip URL")
        parser.add_argument("--target", required=True, help="Target directory")
        parser.add_argument("--pid", type=int, help="Parent PID to wait/kill")
        parser.add_argument("--exe", required=True, help="Executable to restart")
        
        args = parser.parse_args()
        
        print("=== IndexTTS2 自动更新程序 ===")
        print("请勿关闭此窗口，直到更新完成。", flush=True)
        
        if args.pid:
            print(f"正在等待主程序 (PID: {args.pid}) 退出...", flush=True)
            # 给主程序一点时间自己退出
            time.sleep(1)
            
            # 如果还没退，强制结束
            if psutil.pid_exists(args.pid):
                print(f"主程序 {args.pid} 仍在运行，正在强制结束...", flush=True)
                kill_process_tree(args.pid)
            else:
                print(f"主程序 {args.pid} 已退出。", flush=True)
            
            # 再次确认
            time.sleep(1)
            if psutil.pid_exists(args.pid):
                 print(f"警告: 进程 {args.pid} 仍然存在！更新可能会失败。", flush=True)
            
        temp_dir = tempfile.mkdtemp()
        try:
            zip_path = os.path.join(temp_dir, "update.zip")
            extract_dir = os.path.join(temp_dir, "extracted")
            
            # 先下载更新包（可能是纯 update.zip，也可能是 Gitee 仓库的 archive/master.zip）
            download_file(args.url, zip_path)
            extract_zip(zip_path, extract_dir)

            # 兼容 Gitee repository/archive/master.zip：
            # 如果解压后的目录里再包含一个 update.zip，则认为真正的更新内容在内部的 update.zip 中
            inner_update_zip = None
            for root, dirs, files in os.walk(extract_dir):
                if "update.zip" in files:
                    inner_update_zip = os.path.join(root, "update.zip")
                    break

            if inner_update_zip:
                print("检测到仓库压缩包内的 update.zip，正在解压内部更新包...", flush=True)
                inner_extract_dir = os.path.join(temp_dir, "inner_extracted")
                os.makedirs(inner_extract_dir, exist_ok=True)
                extract_zip(inner_update_zip, inner_extract_dir)
                source_dir = inner_extract_dir
            else:
                source_dir = extract_dir

            install_update(source_dir, args.target)
            
            print("更新成功！正在重启程序...", flush=True)
            time.sleep(2)
            
            # 启动主程序
            subprocess.Popen(f'start "" {args.exe}', shell=True)
            
        finally:
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
                
    except Exception as e:
        print(f"\n发生严重错误: {e}")
        traceback.print_exc()
        print("\n更新失败。")
        os.system("pause")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Critical Error: {e}")
        traceback.print_exc()
        os.system("pause")
