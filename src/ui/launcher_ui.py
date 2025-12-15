import flet as ft
import os
import sys
import json
import asyncio
import traceback
import aiohttp  # 替换requests为异步HTTP库
import subprocess
from typing import Optional

# 配置 GitHub 地址
GITHUB_REPO = "qformat/indextts2-Multi-launcher"
VERSION_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/master/version.json"
ARCHIVE_URL = f"https://github.com/{GITHUB_REPO}/archive/refs/heads/master.zip"

# 异步获取远程版本（完全异步，无阻塞）
async def get_remote_version() -> dict:
    """异步请求远程版本信息，替换同步requests"""
    headers = {"User-Agent": "IndexTTS2-Launcher/1.0"}
    async with aiohttp.ClientSession() as session:
        async with session.get(VERSION_URL, timeout=15, headers=headers) as resp:
            if resp.status == 200:
                # GitHub raw 可能会返回 text/plain，所以这里直接获取文本并手动解析
                text = await resp.text()
                return json.loads(text)
            else:
                raise Exception(f"HTTP 请求失败，状态码: {resp.status}")

# 异步读取本地版本（放到executor避免文件IO阻塞）
async def get_local_version() -> str:
    """异步读取本地version.json，避免文件IO阻塞UI"""
    loop = asyncio.get_running_loop()
    def _read_local():
        try:
            with open("version.json", "r", encoding="utf-8") as f:
                return json.load(f).get("version", "0.0.0")
        except Exception:
            return "0.0.0"
    return await loop.run_in_executor(None, _read_local)

# 异步启动更新进程（避免同步阻塞）
async def spawn_updater(download_url: str, current_pid: int, restart_cmd: str):
    """异步启动更新器进程，所有同步操作放入executor"""
    loop = asyncio.get_running_loop()
    def _spawn():
        updater_script = os.path.join(os.getcwd(), "src", "updater_cli.py")
        args = [
            sys.executable,
            updater_script,
            "--url", download_url,
            "--target", os.getcwd(),
            "--pid", str(current_pid),
            "--exe", restart_cmd
        ]
        print(f"Updater args: {args}")
        # 尝试启动更新器
        try:
            subprocess.Popen(args, creationflags=subprocess.CREATE_NEW_CONSOLE)
        except Exception as e1:
            print(f"Method 1 failed: {e1}")
            try:
                cmd_str = subprocess.list2cmdline(args)
                subprocess.Popen(f'start "IndexTTS Updater" {cmd_str}', shell=True)
            except Exception as e2:
                print(f"Method 2 failed: {e2}")
                raise e2
        # 异步等待替代同步sleep，避免阻塞
        asyncio.run_coroutine_threadsafe(asyncio.sleep(0.5), loop)
        return True

    try:
        await loop.run_in_executor(None, _spawn)
        return True
    except Exception as ex:
        raise ex

# 异步启动主应用（避免同步阻塞）
async def launch_app_async(page: ft.Page, status_text: ft.Text, progress_bar: ft.ProgressBar):
    """异步启动主应用"""
    print("Inside launch_app_async")
    # 移除可能导致死锁的UI更新
    # status_text.value = "正在启动应用程序..."
    # progress_bar.visible = True
    # page.update()

    try:
        main_script = os.path.join(os.getcwd(), "src", "main.py")
        if not os.path.exists(main_script):
            main_script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
        
        cmd = [sys.executable, main_script]
        if len(sys.argv) > 1:
            cmd.extend(sys.argv[1:])
        
        print(f"Launch cmd: {cmd}")
        # 使用 subprocess.Popen 启动新进程，彻底分离
        # 使用 CREATE_NO_WINDOW (0x08000000) 隐藏终端窗口
        CREATE_NO_WINDOW = 0x08000000
        subprocess.Popen(cmd, cwd=os.getcwd(), creationflags=CREATE_NO_WINDOW, close_fds=True)
        result = True
    except Exception as ex:
        print(f"Launch failed: {ex}")
        result = ex

    if result is True:
        print(f"Launch success. Current PID: {os.getpid()}. Exiting...")
        # 终极退出方案：直接杀掉自己
        # 任何 Python 层面的退出（sys.exit, os._exit）在 Flet 的事件循环中都可能被捕获或死锁
        # 只有外部命令 taskkill 能确保彻底终结
        try:
            # 先尝试正常关闭
            page.window.close()
        except:
            pass
            
        print("Executing taskkill...")
        # 使用 subprocess 调用 taskkill，并且不等待返回
        subprocess.Popen(f"taskkill /F /PID {os.getpid()}", shell=True)
        # 立即停止当前代码执行
        return
    else:
        status_text.value = f"启动失败: {result}"
        status_text.color = ft.Colors.RED
        progress_bar.visible = False
        page.update()

async def check_update(page: ft.Page, status_text, progress_bar, info_text, actions_row, launch_app_func):
    print("Starting update check...")
    # 获取当前事件循环，用于后续回调
    loop = asyncio.get_running_loop()
    
    try:
        # 异步延迟，不阻塞UI
        await asyncio.sleep(1.0)
        
        status_text.value = "正在获取远程版本信息..."
        page.update()
        
        # 异步获取远程版本（无阻塞）
        remote_data = await get_remote_version()
        remote_ver = remote_data.get("version", "0.0.0")
        print(f"Remote version: {remote_ver}")
        
        # 异步获取本地版本
        local_ver = await get_local_version()
        print(f"Local version: {local_ver}")
        
        download_url = remote_data.get("url", ARCHIVE_URL)
        if "github.com" in download_url and "gitee.com" not in download_url:
            download_url = ARCHIVE_URL

        if remote_ver > local_ver:
            print("Update found.")
            status_text.value = f"发现新版本: {remote_ver}"
            status_text.color = ft.Colors.BLUE
            info_text.value = f"当前版本: {local_ver}\n\n更新内容:\n{remote_data.get('changelog', '暂无描述')}"
            progress_bar.visible = False
            
            # 异步更新按钮回调
            async def on_update_click(e):
                try:
                    current_pid = os.getpid()
                    # 查找 launcher.py
                    launcher_py = os.path.join(os.getcwd(), "launcher.py")
                    restart_cmd = f'"{sys.executable}" "{launcher_py}"' if os.path.exists(launcher_py) else f'"{sys.executable}" "{os.path.join(os.getcwd(), "src", "main.py")}"'
                    
                    # 异步启动更新器
                    await spawn_updater(download_url, current_pid, restart_cmd)
                    
                    print("Updater spawned. Exiting launcher...")
                    try:
                        page.window.close()
                    except:
                        pass
                    
                    print("Executing taskkill...")
                    subprocess.Popen(f"taskkill /F /PID {os.getpid()}", shell=True)
                    return
                except Exception as ex:
                    print(f"Update start failed: {ex}")
                    status_text.value = f"启动更新失败: {ex}"
                    status_text.color = ft.Colors.RED
                    page.update()

            # 包装异步回调为Flet可识别的形式
            def on_update_click_wrapper(e):
                asyncio.run_coroutine_threadsafe(on_update_click(e), loop)

            btn_update = ft.ElevatedButton("立即更新", on_click=on_update_click_wrapper, bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE)
            
            def on_skip_click_wrapper(e):
                 asyncio.run_coroutine_threadsafe(launch_app_func(), loop)
            
            btn_skip = ft.TextButton("暂不更新，直接启动", on_click=on_skip_click_wrapper)
            
            actions_row.controls = [btn_skip, btn_update]
            actions_row.visible = True
            page.update()
        else:
            print("No update.")
            status_text.value = "当前已是最新版本"
            progress_bar.visible = False
            info_text.value = "即将自动启动..."
            page.update()
            print("Wait 1.0s before launch...")
            await asyncio.sleep(1.0)
            print("Calling launch_app_func...")
            await launch_app_func()

    except Exception as e:
        print(f"Check failed: {e}")
        traceback.print_exc()
        status_text.value = f"检查更新失败: {e}"
        if "404" in str(e):
             status_text.value = "未找到更新配置文件 (404)"
        info_text.value = "将直接启动应用程序..."
        progress_bar.visible = False
        page.update()
        await asyncio.sleep(2.0)
        await launch_app_func()

async def main(page: ft.Page):
    print("Launcher main started.")
    page.title = "IndexTTS2 启动器"
    page.window_width = 500
    page.window_height = 350
    try:
        page.window.center()
    except:
        pass
    page.bgcolor = ft.Colors.WHITE
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    status_text = ft.Text("正在初始化...", size=16)
    info_text = ft.Text("", size=14, color=ft.Colors.GREY_700)
    progress_bar = ft.ProgressBar(width=400, visible=True)
    actions_row = ft.Row(alignment=ft.MainAxisAlignment.CENTER, visible=False)

    page.add(
        ft.Column(
            [
                ft.Image(src="assets/index_icon.png", width=80, height=80, fit=ft.ImageFit.CONTAIN),
                ft.Text("IndexTTS2 启动器", size=24, weight=ft.FontWeight.BOLD),
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
    page.update()
    print("UI Initialized.")

    # 封装异步启动应用逻辑
    async def launch_app():
        await launch_app_async(page, status_text, progress_bar)

    # 启动异步检查更新（直接使用asyncio.create_task，避免Flet版本兼容性问题）
    status_text.value = "正在连接更新服务器..."
    page.update()
    
    # 使用标准asyncio创建任务，不阻塞main
    asyncio.create_task(check_update(page, status_text, progress_bar, info_text, actions_row, launch_app))

if __name__ == "__main__":
    ft.app(target=main)
