import os
import sys
import argparse
import subprocess
import time
import zipfile
import shutil
import tempfile
import urllib.request
import urllib.parse
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


def _mask_url(url: str) -> str:
    """隐藏URL的敏感部分，只保留域名与文件名，避免在控制台暴露完整链接。"""
    try:
        p = urllib.parse.urlparse(url)
        host = p.netloc or ""
        tail = (p.path or "").split("/")[-1]
        if not tail:
            tail = "update.zip"
        scheme = p.scheme or "http"
        if host:
            return f"{scheme}://{host}/.../{tail}"
        return f".../{tail}"
    except Exception:
        return "(已隐藏)"


def _render_progress_bar(percent: float, width: int = 28) -> str:
    """渲染简单文本进度条。"""
    try:
        p = max(0.0, min(100.0, float(percent)))
    except Exception:
        p = 0.0
    filled = int(round(width * p / 100.0))
    filled = max(0, min(width, filled))
    return f"[{'#' * filled}{'-' * (width - filled)}] {p:5.1f}%"


def _split_cmd_first_token(cmd: str):
    """拆分命令行字符串的首个 token（支持双引号包裹路径）。

    返回：(first, rest)
    - first: 第一个 token（去掉外层引号）
    - rest: 剩余字符串（已 strip，可能为空）
    """
    try:
        s = (cmd or "").strip()
        if not s:
            return "", ""
        if s.startswith('"'):
            end = s.find('"', 1)
            if end > 1:
                first = s[1:end]
                rest = s[end + 1 :].strip()
                return first, rest
        parts = s.split(maxsplit=1)
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], parts[1].strip()
    except Exception:
        return "", (cmd or "").strip()

def download_file(url, dest):
    print(f"正在下载更新包: {_mask_url(str(url))}")
    try:
        # Gitee Raw 文件下载需要处理防盗链，有时直接请求会 403
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            # 'Referer': 'https://gitee.com/',  # 需要时可打开，用于解决 403
            'Accept': '*/*',
            'Connection': 'keep-alive'
        }
        
        # 针对 Gitee 大文件/Release 下载的特殊处理
        if "gitee.com" in url and "/raw/" in url:
            # 有些 raw 链接对大文件会重定向或禁止访问，这里保留原链接
            pass

        req = urllib.request.Request(url, headers=headers)
        
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
                    print(f"\r下载进度: {_render_progress_bar(percent)}", end='', flush=True)
            print("\n下载完成。", flush=True)
    except Exception as e:
        print(f"\n下载失败: {e}")
        raise

def extract_zip(zip_path, extract_to):
    print("正在解压...", flush=True)
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            members = zip_ref.infolist()
            total = len(members)
            if total <= 0:
                zip_ref.extractall(extract_to)
            else:
                for i, m in enumerate(members, start=1):
                    zip_ref.extract(m, extract_to)
                    percent = i * 100.0 / total
                    if i == 1 or i == total or (i % 50 == 0):
                        print(f"\r解压进度: {_render_progress_bar(percent)}", end='', flush=True)
                print("", flush=True)
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
    
    # Windows 下使用 xcopy 复制（保留目录结构）
    cmd = f'xcopy "{source_dir}" "{target_dir}" /s /e /y /i'
    print("正在复制更新文件（可能需要几分钟，请耐心等待）...", flush=True)
    ret = subprocess.call(cmd, shell=True)
    if ret != 0:
        print("更新文件复制失败。")
        raise Exception("Copy failed")
    print("安装完成。", flush=True)


def _rename_launcher_exe_to_fixed_name(target_dir: str):
    """将启动器 exe 重命名为固定文件名：IndexTTS2多功能启动器.exe。

    返回值：重命名后的 exe 完整路径；失败或找不到则返回 None。
    """
    try:
        prefix = "IndexTTS2多功能启动器"
        new_name = f"{prefix}.exe"
        new_path = os.path.join(target_dir, new_name)

        if os.path.isfile(new_path):
            return new_path

        try:
            candidates = []
            for fn in os.listdir(target_dir):
                if not fn.lower().endswith(".exe"):
                    continue
                if not fn.startswith(prefix):
                    continue
                candidates.append(os.path.join(target_dir, fn))
        except Exception:
            candidates = []

        if not candidates:
            return None

        old_path = None
        try:
            candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            old_path = candidates[0]
        except Exception:
            old_path = candidates[0]

        if not old_path or not os.path.isfile(old_path):
            return None

        if os.path.basename(old_path).lower() == new_name.lower():
            return old_path

        try:
            os.replace(old_path, new_path)
        except Exception:
            shutil.move(old_path, new_path)
        return new_path if os.path.isfile(new_path) else None
    except Exception:
        return None

def main():
    try:
        parser = argparse.ArgumentParser(description="IndexTTS2 Updater CLI")
        parser.add_argument("--url", required=True, help="Update zip URL")
        parser.add_argument("--target", required=True, help="Target directory")
        parser.add_argument("--pid", type=int, help="Parent PID to wait/kill")
        parser.add_argument("--exe", required=True, help="重启命令（可为 exe 路径或完整命令）")
        
        args = parser.parse_args()
        
        print("=== IndexTTS2 自动更新程序 ===")
        print("B站：K哥讲AI | 微信：qformatq")
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
            
            download_file(args.url, zip_path)
            extract_zip(zip_path, extract_dir)
            install_update(extract_dir, args.target)

            # 更新完成后，尝试将启动器 exe 统一重命名为固定文件名（去掉版本号）
            # 仅对“IndexTTS2多功能启动器*.exe”生效；若当前是 python 启动（开发态）则不会影响。
            new_restart_cmd = args.exe
            try:
                new_exe_path = _rename_launcher_exe_to_fixed_name(args.target)
                if new_exe_path:
                    first, rest = _split_cmd_first_token(args.exe)
                    if first and first.lower().endswith(".exe") and os.path.basename(first).startswith("IndexTTS2多功能启动器"):
                        new_restart_cmd = f'"{new_exe_path}"' + (f" {rest}" if rest else "")
            except Exception:
                pass
            
            print("更新成功！正在重启程序...", flush=True)
            time.sleep(2)
            
            # 启动主程序（使用 start 脱离当前更新器进程）
            subprocess.Popen(f'start "" {new_restart_cmd}', shell=True)
            
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
