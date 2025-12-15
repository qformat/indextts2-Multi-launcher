import flet as ft
import os
import sys
import json
import requests
import subprocess
import time
import asyncio

# 配置 Gitee 地址
GITEE_REPO = "qformat/indextts2-Multi-launcher"
VERSION_URL = f"https://gitee.com/{GITEE_REPO}/raw/master/version.json"
# 默认下载地址 (如果 version.json 里的 url 是 github 的，我们可以强制替换或者优先使用这个)
ARCHIVE_URL = f"https://gitee.com/{GITEE_REPO}/repository/archive/master.zip"

def main(page: ft.Page):
    page.title = "IndexTTS2 启动器"
    page.window_width = 500
    page.window_height = 350
    # page.window_center() # 旧版本 Flet 可能不支持，改用 alignment
    page.window.center() if hasattr(page, "window") and hasattr(page.window, "center") else None
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.bgcolor = ft.Colors.WHITE
    
    status_text = ft.Text("正在检查更新...", size=16)
    info_text = ft.Text("", size=14, color=ft.Colors.GREY_700)
    
    # 进度条 (初始不可见)
    progress_bar = ft.ProgressBar(width=400, visible=True)
    
    # 按钮容器
    actions_row = ft.Row(alignment=ft.MainAxisAlignment.CENTER, visible=False)
    
    page.add(
        ft.Column(
            [
                ft.Image(src="assets/index_icon.png", width=80, height=80, fit=ft.ImageFit.CONTAIN),
                ft.Text("IndexTTS2", size=24, weight=ft.FontWeight.BOLD),
                ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
                status_text,
                progress_bar,
                info_text,
                ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
                actions_row
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER
        )
    )
    
    def get_local_version():
        try:
            with open("version.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("version", "0.0.0")
        except:
            return "0.0.0"

    def launch_app(e=None):
        status_text.value = "正在启动应用程序..."
        progress_bar.visible = True
        page.update()
        
        try:
            # 启动主程序
            # 假设当前目录是项目根目录
            main_script = os.path.join(os.getcwd(), "src", "main.py")
            if not os.path.exists(main_script):
                 # 尝试调整路径
                 main_script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
            
            cmd = [sys.executable, main_script]
            # 传递原始参数
            if len(sys.argv) > 1:
                cmd.extend(sys.argv[1:])
                
            subprocess.Popen(cmd, cwd=os.getcwd())
            
            # 关闭启动器
            if hasattr(page, "window_destroy"):
                page.window_destroy()
            elif hasattr(page, "window_close"):
                page.window_close()
            else:
                # Flet < 0.21.0
                page.window_visible = False
                page.update()
            
            sys.exit(0)
        except Exception as ex:
            status_text.value = f"启动失败: {ex}"
            status_text.color = ft.Colors.RED
            page.update()

    def start_update(download_url):
        # 启动 CLI 更新程序
        try:
            updater_script = os.path.join(os.getcwd(), "src", "updater_cli.py")
            current_pid = os.getpid()
            
            # 构造启动命令
            # 重新启动 launcher.py 或者 src/main.py ? 
            # 用户希望更新完自动打开软件。
            # 如果我们这里启动的是 launcher.py，那么更新完再次进入 launcher -> 检查 -> 已经是最新 -> 自动启动。
            # 这样逻辑闭环。
            
            # 查找 launcher.py
            launcher_py = os.path.join(os.getcwd(), "launcher.py")
            if os.path.exists(launcher_py):
                restart_cmd = f'"{sys.executable}" "{launcher_py}"'
            else:
                restart_cmd = f'"{sys.executable}" "{os.path.join(os.getcwd(), "src", "main.py")}"'
            
            # 使用 start cmd /k 来打开新窗口运行更新
            # update_cmd = f'python "{updater_script}" --url "{download_url}" --target "{os.getcwd()}" --pid {current_pid} --exe {restart_cmd}'
            # 注意：cmd /c 或 /k 后面的命令如果包含引号，可能需要外层引号
            
            # 简化：直接构造 args
            args = f'"{sys.executable}" "{updater_script}" --url "{download_url}" --target "{os.getcwd()}" --pid {current_pid} --exe {restart_cmd}'
            
            full_cmd = f'start "IndexTTS2 Updater" {args}'
            
            print(f"Executing: {full_cmd}")
            os.system(full_cmd)
            
            # 退出当前程序
            if hasattr(page, "window_destroy"):
                page.window_destroy()
            elif hasattr(page, "window_close"):
                page.window_close()
            else:
                page.window_visible = False
                page.update()

            sys.exit(0)
            
        except Exception as ex:
            status_text.value = f"启动更新失败: {ex}"
            page.update()

    def check_update_task():
        time.sleep(0.5) # 稍微等待界面加载
        
        local_ver = get_local_version()
        
        try:
            # 获取远程版本
            resp = requests.get(VERSION_URL, timeout=5)
            if resp.status_code == 200:
                remote_data = resp.json()
                remote_ver = remote_data.get("version", "0.0.0")
                # 优先使用 Gitee Archive，如果 json 里有特定 url 也可以用，但为了确保 Gitee...
                # 我们可以检查 remote_data['url'] 是否包含 github，如果是则替换为 Gitee archive
                download_url = remote_data.get("url", ARCHIVE_URL)
                if "github.com" in download_url and "gitee.com" not in download_url:
                    download_url = ARCHIVE_URL
                
                if remote_ver > local_ver:
                    # 发现新版本
                    async def show_update_ui():
                        status_text.value = f"发现新版本: {remote_ver}"
                        status_text.color = ft.Colors.BLUE
                        info_text.value = f"当前版本: {local_ver}\n\n更新内容:\n{remote_data.get('changelog', '暂无描述')}"
                        progress_bar.visible = False
                        
                        btn_update = ft.ElevatedButton("立即更新", on_click=lambda e: start_update(download_url), bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE)
                        btn_skip = ft.TextButton("暂不更新，直接启动", on_click=launch_app)
                        
                        actions_row.controls = [btn_skip, btn_update]
                        actions_row.visible = True
                        page.update()
                        
                    page.run_task(show_update_ui)
                else:
                    # 无更新
                    async def show_no_update():
                        status_text.value = "当前已是最新版本"
                        progress_bar.visible = False
                        info_text.value = "即将自动启动..."
                        page.update()
                        await asyncio.sleep(1.5)
                        launch_app()
                        
                    page.run_task(show_no_update)
            else:
                raise Exception(f"HTTP {resp.status_code}")
                
        except Exception as e:
            # 检查失败，直接启动
            async def show_error():
                status_text.value = f"检查更新失败: {e}"
                if "404" in str(e):
                     status_text.value = "未找到更新配置文件 (404)"
                info_text.value = "将直接启动应用程序..."
                progress_bar.visible = False
                page.update()
                await asyncio.sleep(2)
                launch_app()
            
            page.run_task(show_error)

    # 启动检查线程
    import threading
    threading.Thread(target=check_update_task, daemon=True).start()

if __name__ == "__main__":
    ft.app(target=main)
