#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IndexTTS2 多功能启动器 v3.4 - Flet版本
现代化Material Design界面
功能：
1. 启动多个IndexTTS2实例
2. 管理不同端口的服务
3. 音色选择和语音合成
4. 实时控制台输出监控
5. 美观的现代化界面
"""

import flet as ft
import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import subprocess
import time
import json
from pathlib import Path
from gradio_client import Client, handle_file
import gradio_client.utils as _gcu
_orig_json_schema_to_python_type = getattr(_gcu, "_json_schema_to_python_type", None)
if _orig_json_schema_to_python_type:
    def _safe_json_schema_to_python_type(schema, defs):
        if isinstance(schema, bool):
            return "Any" if schema else "None"
        return _orig_json_schema_to_python_type(schema, defs)
    _gcu._json_schema_to_python_type = _safe_json_schema_to_python_type
import pygame
import requests
from datetime import datetime
import asyncio
import re
import tempfile
import shutil
import zipfile
from pydub import AudioSegment
import psutil
import logging
import logging.handlers
import sys
import platform
import signal
import atexit
import threading


from src.core.logger import LogManager
from src.core.config import ConfigManager
from src.core.utils import calculate_character_length, cn_han_count, format_timestamp, remove_punctuation_from_text
from src.core.audio import save_audio_from_result, get_audio_duration, apply_speaking_speed, apply_speaking_speed_value, apply_volume
from src.ui.batch_editor import show_batch_edit_dialog

class IndexTTSManagerFlet:
    def __init__(self):
        # 初始化退出标志
        self._is_exiting = False
        self.app_version = "3.4.0"
        
        # 首先初始化配置管理器
        self.config_manager = ConfigManager()
        
        # 初始化日志管理器，使用配置中的日志级别
        log_level_str = self.config_manager.get("log_level", "INFO")
        log_level = getattr(logging, log_level_str.upper(), logging.INFO)
        self.log_manager = LogManager("IndexTTS3.4_Manager", log_level)
        
        # 启动时一次性重置行情感向量（如果开关启用）
        try:
            if self.config_manager.get("reset_subtitle_line_emotions_on_start", True):
                # 清空行情感向量；开关保持开启则每次启动都会清空
                self.config_manager.set("subtitle_line_emotions", {})
                self.log_manager.info("已在启动时重置行情感向量")
        except Exception as _reset_err:
            # 保守处理：记录但不影响应用继续
            self.log_manager.warning(f"启动重置行情感向量失败: {_reset_err}")
        
        # 记录系统信息和启动日志
        self.log_manager.log_system_info()
        self.log_manager.info("开始初始化 IndexTTS Manager Flet 应用")
        self.log_manager.info(f"配置文件已加载，主题: {self.config_manager.get('theme')}, 日志级别: {log_level_str}")
        
        self.instances = {}
        self.base_port = 7860
        self.voice_files = []
        self.current_audio_file = None
        self.selected_voice = None
        self.debug_mode = True  # 添加调试模式开关
        
        # 初始化pygame音频
        try:
            pygame.mixer.init()
            self.log_manager.info("pygame音频系统初始化成功")
            
            # 记录pygame音频系统详细信息
            mixer_info = pygame.mixer.get_init()
            if mixer_info:
                freq, format_bits, channels = mixer_info
                self.log_manager.debug(f"pygame音频配置: 频率={freq}Hz, 格式={format_bits}bit, 声道={channels}")
            
        except Exception as e:
            self.log_manager.error(f"pygame音频系统初始化失败: {e}")
            self.log_manager.exception("pygame音频系统初始化异常详情")
        
        # UI组件引用
        self.page = None
        self.voice_dropdown = None
        self.text_input = None

        self.status_table = None
        self.custom_port_field = None
        self.device_mode_dropdown = None
        
        # 字幕生成相关属性
        self.subtitle_text_input = None
        self.subtitle_preview = None
        self.subtitle_progress = None
        self.subtitle_status = None
        self.subtitle_segments = []
        self.subtitle_cpl_chinese = 18
        self.subtitle_cpl_slider = None
        self.subtitle_cpl_value_text = None
        self.quote_glue_enabled = True
        self.quote_glue_checkbox = None
        self.split_mode_dropdown = None
        self.punctuation_set_text = None
        self.temp_audio_dir = None
        self.console_output = None
        self.log_output = None
        self.progress_ring = None
        self.snack_bar = None
        self.remove_punctuation_checkbox = None
        self.voice_sample_button = None
        self.voice_sample_playing = False
        self.voice_sample_start_time = 0
        self.subtitle_sample_button = None
        self.subtitle_sample_playing = False
        self.tts_generating = False
        self.tts_stop_flag = False
        
        # 视图缓存，用于保持菜单状态
        self.cached_views = {}
        self.current_view = None
        
        # 早期日志缓存，用于在console_output创建之前缓存日志
        self.early_logs = []
        
        # 字幕播放相关属性
        self.subtitle_sync_running = False
        self.subtitle_sync_thread = None
        self.current_subtitle_text = None
        self.subtitle_dialog = None
        self.runtime_speaking_speed = None
        self.runtime_volume_percent = None

        # 批量生成相关属性
        self.bulk_selected_files = []
        self.bulk_common_base = None
        self.bulk_output_dir = None
        self.bulk_status = "空闲"
        self.bulk_progress_bar = None
        self.bulk_progress_text = None
        self.bulk_log_list = None
        self.bulk_stop_flag = False
        self.bulk_pause_flag = False
        self.bulk_thread = None

        # 设置程序退出时的清理机制
        self.setup_exit_handlers()
        
    def start_playback_monitor(self):
        """启动音频播放监控线程"""
        threading.Thread(target=self.monitor_audio_playback, daemon=True).start()

    def monitor_audio_playback(self):
        """监控音频播放状态，播放结束时重置按钮"""
        import time
        while not getattr(self, '_is_exiting', False):
            try:
                # 仅当页面已加载时才进行UI更新
                if not (hasattr(self, 'page') and self.page):
                    time.sleep(1)
                    continue

                if not pygame.mixer.get_init():
                    time.sleep(1)
                    continue
                
                is_busy = pygame.mixer.music.get_busy()
                
                if not is_busy:
                    needs_update = False
                    
                    # 1. 音色库试听按钮
                    if hasattr(self, 'voice_library_play_btn') and self.voice_library_play_btn.icon == ft.Icons.STOP:
                        self.voice_library_play_btn.icon = ft.Icons.PLAY_CIRCLE
                        self.voice_library_play_btn.text = "试听"
                        self.voice_library_play_btn.style = ft.ButtonStyle(bgcolor=ft.Colors.GREEN_600, color=ft.Colors.WHITE, padding=10)
                        needs_update = True
                            
                    # 2. 语音合成-试听音色按钮
                    if hasattr(self, 'voice_sample_button') and getattr(self, 'voice_sample_playing', False):
                         # 增加1秒的缓冲期，防止播放刚开始时 get_busy 返回 False 导致按钮立即重置
                         if time.time() - getattr(self, 'voice_sample_start_time', 0) > 1.0:
                             self.voice_sample_playing = False
                             self.voice_sample_button.text = "试听音色"
                             self.voice_sample_button.icon = ft.Icons.PLAY_CIRCLE
                             self.voice_sample_button.style = ft.ButtonStyle(bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE)
                             needs_update = True

                    # 3. 语音合成-播放结果按钮
                    if hasattr(self, 'play_result_button') and self.play_result_button.icon == ft.Icons.STOP:
                         self.play_result_button.icon = ft.Icons.PLAY_ARROW
                         self.play_result_button.text = "播放结果"
                         self.play_result_button.style = ft.ButtonStyle(bgcolor=ft.Colors.PURPLE, color=ft.Colors.WHITE)
                         needs_update = True
                            
                    # 4. 字幕生成-试听按钮
                    if hasattr(self, 'subtitle_sample_button') and getattr(self, 'subtitle_sample_playing', False):
                         self.subtitle_sample_playing = False
                         self.subtitle_sample_button.text = "试听"
                         self.subtitle_sample_button.icon = ft.Icons.PLAY_CIRCLE
                         self.subtitle_sample_button.style = ft.ButtonStyle(color=ft.Colors.WHITE, bgcolor=ft.Colors.GREEN_600)
                         needs_update = True
                    
                    # 5. 情感参考音频
                    if getattr(self, 'emo_ref_playing', False):
                        self.emo_ref_playing = False
                        if getattr(self, 'play_emo_ref_button', None):
                            self.play_emo_ref_button.text = "试听参考音频"
                            self.play_emo_ref_button.icon = ft.Icons.PLAY_CIRCLE
                        needs_update = True

                    # 6. 列表单个音色试听按钮
                    if getattr(self, 'current_list_play_btn', None):
                        try:
                            if self.current_list_play_btn.icon == ft.Icons.STOP:
                                self.current_list_play_btn.icon = ft.Icons.PLAY_CIRCLE
                                needs_update = True
                        except:
                            pass
                        self.current_list_play_btn = None

                    # 7. 历史记录播放按钮
                    if getattr(self, 'current_history_play_btn', None):
                        try:
                            if self.current_history_play_btn.icon == ft.Icons.STOP:
                                self.current_history_play_btn.icon = ft.Icons.PLAY_ARROW
                                self.current_history_play_btn.text = "播放"
                                needs_update = True
                        except:
                            pass
                        self.current_history_play_btn = None

                    if needs_update:
                        try:
                            self.page.update()
                        except Exception:
                            pass

                time.sleep(0.5)
            except Exception:
                time.sleep(1)

    def main(self, page: ft.Page):
        """主应用入口"""
        self.page = page
        
        # 立即设置GUI日志回调函数，确保从应用启动就开始记录
        self.log_manager.set_gui_callback(self.gui_log_callback)
        
        self.log_manager.info("设置页面属性")
        self.setup_page()
        
        self.log_manager.info("初始化UI界面")
        self.setup_ui()
        
        self.log_manager.info("GUI日志回调函数已设置，开始记录所有日志")
        self.log_manager.info("IndexTTS Manager Flet 应用初始化完成")
        self.start_playback_monitor()
        # self.scan_voice_files()
        
    def gui_log_callback(self, message, level):
        """GUI日志回调函数"""
        try:
            # 检查程序是否正在退出
            if hasattr(self, '_is_exiting') and self._is_exiting:
                return
                
            # 如果console_output还没有创建，先缓存日志
            if not self.console_output or not hasattr(self.console_output, 'controls'):
                self.early_logs.append((message, level))
                return
            
            # 根据日志级别设置颜色
            color_map = {
                'DEBUG': ft.Colors.GREY_400,
                'INFO': ft.Colors.BLUE_300,
                'WARNING': ft.Colors.ORANGE_300,
                'ERROR': ft.Colors.RED_300,
                'CRITICAL': ft.Colors.RED_500
            }
            
            color = color_map.get(level, ft.Colors.WHITE)
            
            # 创建带颜色的文本控件
            log_text = ft.Text(
                message,
                color=color,
                size=12,
                font_family="Consolas",
                selectable=True,
            )
            
            # 添加到ListView
            self.console_output.controls.append(log_text)
            
            # 限制显示行数
            if len(self.console_output.controls) > 1000:
                # 保留最后500行
                self.console_output.controls = self.console_output.controls[-500:]
            
            if self.page and hasattr(self.page, 'update') and not getattr(self, '_suppress_console_update', False):
                try:
                    self.page.update()
                except Exception:
                    pass
                
        except Exception as e:
            # 避免日志回调中的错误导致无限循环
            # 只在非退出状态下打印错误
            if not (hasattr(self, '_is_exiting') and self._is_exiting):
                print(f"GUI日志回调错误: {e}")
    
    def replay_early_logs(self):
        """重放早期缓存的日志"""
        try:
            if self.early_logs and self.console_output and hasattr(self.console_output, 'controls'):
                logs_to_replay = self.early_logs[-500:]
                self._suppress_console_update = True
                for message, level in logs_to_replay:
                    self.gui_log_callback(message, level)
                self._suppress_console_update = False
                try:
                    self.console_output.update()
                except Exception:
                    pass
                self.early_logs = []
        except Exception:
            pass
        
    def setup_page(self):
        """设置页面属性"""
        self.page.title = "IndexTTS2 多功能启动器 v3.4"
        
        # 从配置文件加载主题设置
        theme_setting = self.config_manager.get("theme", "system")
        if theme_setting == "system":
            self.page.theme_mode = ft.ThemeMode.SYSTEM
        elif theme_setting == "light":
            self.page.theme_mode = ft.ThemeMode.LIGHT
        elif theme_setting == "dark":
            self.page.theme_mode = ft.ThemeMode.DARK
        else:
            self.page.theme_mode = ft.ThemeMode.LIGHT  # 默认浅色主题
            
        self.page.theme = ft.Theme(
            color_scheme_seed=ft.Colors.BLUE,
            visual_density=ft.VisualDensity.COMFORTABLE,
        )
        
        # 设置页面属性
        self.page.window.width = 1400
        self.page.window.height = 900
        self.page.window.min_width = 1200
        self.page.window.min_height = 700
        self.page.window.resizable = True
        self.page.window.maximizable = True
        self.page.window.center()
        self.page.padding = 0
        
        # 创建SnackBar
        self.snack_bar = ft.SnackBar(
            content=ft.Text(""),
            action="确定",
            action_color=ft.Colors.BLUE,
        )
        self.page.overlay.append(self.snack_bar)
        
        # 设置页面关闭事件处理
        self.page.on_window_event = self.on_window_event
        
        self.log_manager.debug("页面属性设置完成")
        
    def setup_ui(self):
        """设置UI界面"""
        self.log_manager.info("开始设置UI界面")
        
        # 扫描音色文件
        self.scan_voice_files()
        
        # 设置应用栏
        self.page.appbar = ft.AppBar(
            title=ft.Text("IndexTTS2 多功能启动器 v3.4", size=20, weight=ft.FontWeight.BOLD),
            center_title=True,
            bgcolor=ft.Colors.BLUE,
            color=ft.Colors.WHITE,
            actions=[
                ft.IconButton(
                    icon=ft.Icons.UPLOAD_FILE,
                    tooltip="添加音色",
                    on_click=self.open_voice_file_picker,
                    icon_color=ft.Colors.WHITE,
                ),
                ft.IconButton(
                    icon=ft.Icons.REFRESH,
                    tooltip="刷新音色",
                    on_click=self.refresh_voices,
                    icon_color=ft.Colors.WHITE,
                ),
                ft.IconButton(
                    icon=ft.Icons.SETTINGS,
                    tooltip="设置",
                    icon_color=ft.Colors.WHITE,
                    on_click=self.show_settings_dialog,
                ),
            ],
        )
        
        # 创建导航栏
        self.nav_rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=140,  # 增加最小宽度
            min_extended_width=240,  # 增加扩展宽度
            bgcolor=ft.Colors.SURFACE,  # 添加背景色
            destinations=[
                ft.NavigationRailDestination(
                    icon=ft.Icons.DASHBOARD,
                    selected_icon=ft.Icons.DASHBOARD_OUTLINED,
                    label_content=ft.Text("实例控制", size=13, weight=ft.FontWeight.W_500),
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.RECORD_VOICE_OVER,
                    selected_icon=ft.Icons.RECORD_VOICE_OVER_OUTLINED,
                    label_content=ft.Text("语音合成", size=13, weight=ft.FontWeight.W_500),
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.CLOSED_CAPTION,
                    selected_icon=ft.Icons.CLOSED_CAPTION_OUTLINED,
                    label_content=ft.Text("字幕生成", size=13, weight=ft.FontWeight.W_500),
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.LIBRARY_MUSIC,
                    selected_icon=ft.Icons.LIBRARY_MUSIC_OUTLINED,
                    label_content=ft.Text("音色库", size=13, weight=ft.FontWeight.W_500),
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.SUBTITLES,
                    selected_icon=ft.Icons.SUBTITLES_OUTLINED,
                    label_content=ft.Text("多角色配音字幕", size=13, weight=ft.FontWeight.W_500),
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.MIC,
                    selected_icon=ft.Icons.MIC,
                    label_content=ft.Text("播客生成", size=13, weight=ft.FontWeight.W_500),
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.LIBRARY_MUSIC,
                    selected_icon=ft.Icons.LIBRARY_MUSIC_OUTLINED,
                    label_content=ft.Text("批量生成", size=13, weight=ft.FontWeight.W_500),
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.HISTORY,
                    selected_icon=ft.Icons.HISTORY_TOGGLE_OFF,
                    label_content=ft.Text("生成记录", size=13, weight=ft.FontWeight.W_500),
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.TERMINAL,
                    selected_icon=ft.Icons.TERMINAL_OUTLINED,
                    label_content=ft.Text("控制台输出", size=13, weight=ft.FontWeight.W_500),
                ),
            ],
            on_change=self.on_nav_change,
        )
        
        # 创建主内容区域
        dashboard_view = self.create_dashboard_view()
        self.main_content = ft.Container(
            content=dashboard_view,
            expand=True,
            padding=20,
        )
        
        # 设置初始视图状态
        self.current_view = 0
        self.cached_views[0] = dashboard_view
        
        # 创建底部状态栏（动态TTS状态）
        self.tts_status_icon = ft.Icon(ft.Icons.CIRCLE, color=ft.Colors.RED_400, size=12)
        self.tts_status_text = ft.Text("TTS 未启动", size=12, color=ft.Colors.RED_400)

        status_bar = ft.Container(
            content=ft.Row([
                self.tts_status_icon,
                self.tts_status_text,
                ft.VerticalDivider(width=1),
                ft.Text("技术支持：睿视信息", size=12),
                ft.VerticalDivider(width=1),
                ft.Text("wechat: qformatq", size=12),
            ]),
            bgcolor=ft.Colors.SURFACE,
            padding=ft.padding.symmetric(horizontal=20, vertical=10),
            height=40,
        )
        
        # 组装主布局
        main_layout = ft.Row([
            self.nav_rail,
            ft.VerticalDivider(width=1),
            self.main_content,
        ], expand=True)
        
        # 设置页面内容（不包含AppBar，因为已经通过page.appbar设置）
        self.page.add(
            ft.Column([
                main_layout,
                status_bar,
            ], expand=True, spacing=0)
        )

        # 预注册目录选择 FilePicker 到页面 overlay，避免首次调用时报错
        try:
            if not hasattr(self, 'dir_picker') or self.dir_picker is None:
                self.dir_picker = ft.FilePicker(on_result=self.on_pick_directory_result)
            # 确保加入到 overlay 并先更新页面，再使用
            # 某些环境中 overlay 的成员检查可能抛异常，这里双重保障
            need_append = True
            try:
                need_append = self.dir_picker not in self.page.overlay
            except Exception:
                need_append = True
            if need_append:
                self.page.overlay.append(self.dir_picker)
            # 更新页面，确保控件已注册
            self.page.update()
            # 预注册文件选择 FilePicker（用于上传音色文件）
            if not hasattr(self, 'file_picker') or self.file_picker is None:
                self.file_picker = ft.FilePicker(on_result=self.on_pick_voice_files)
            need_append_fp = True
            try:
                need_append_fp = self.file_picker not in self.page.overlay
            except Exception:
                need_append_fp = True
            if need_append_fp:
                self.page.overlay.append(self.file_picker)
            self.page.update()
        except Exception as e:
            # 注册失败不影响其他功能，仅记录日志
            try:
                self.log_manager.error(f"预注册目录选择器失败: {e}")
            except Exception:
                pass

        # 初始化底栏TTS状态显示
        try:
            self.update_tts_status_bar()
        except Exception:
            pass
        
    def create_dashboard_view(self):
        """创建控制台视图"""
        # 实例控制卡片
        instance_control_card = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.SETTINGS, color=ft.Colors.BLUE, size=20),
                        title=ft.Text("实例控制", weight=ft.FontWeight.BOLD, size=14),
                        subtitle=ft.Text("管理IndexTTS2实例", size=11),
                        content_padding=ft.padding.symmetric(horizontal=8, vertical=4),
                    ),
                    ft.Divider(height=1),
                    ft.Row([
                        ft.Text("端口号:", size=12),
                        self.create_custom_port_field(),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Row([
                        ft.Text("设备模式:", size=12),
                        self.create_device_mode_dropdown(),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Row([
                        (lambda: (
                            setattr(self, 'fp16_checkbox', ft.Checkbox(label="启用FP16（降低显存占用）", value=bool(self.config_manager.get("fp16_enabled", False)))),
                            self.fp16_checkbox
                        ))()[1],
                        (lambda: (
                            setattr(self, 'cuda_kernel_checkbox', ft.Checkbox(label="自定义CUDA内核（性能优化）", value=bool(self.config_manager.get("cuda_kernel_enabled", False)))),
                            self.cuda_kernel_checkbox
                        ))()[1],
                        (lambda: (
                            setattr(self, 'low_vram_checkbox', ft.Checkbox(
                                label="低显存模式 (基本不影响效果)", 
                                value=bool(self.config_manager.get("low_vram_enabled", False)),
                                on_change=lambda e: self.config_manager.set("low_vram_enabled", bool(e.control.value))
                            )),
                            self.low_vram_checkbox
                        ))()[1],
                        (lambda: (
                            setattr(self, 'verbose_checkbox', ft.Checkbox(label="详细日志(verbose)（不建议勾选）", value=False)),
                            self.verbose_checkbox
                        ))()[1],
                    ], alignment=ft.MainAxisAlignment.START, spacing=12, wrap=True),
                    ft.Row([
                        ft.Text("分段最大Token:", size=12),
                        (lambda: (
                            setattr(self, 'gui_seg_tokens_field', ft.TextField(width=120, value=str(int(self.config_manager.get("gui_seg_tokens", 120))), hint_text="默认120")),
                            self.gui_seg_tokens_field
                        ))()[1],
                        ft.Text("降低该值可减小显存占用", size=11, color=ft.Colors.GREY_600),
                    ], alignment=ft.MainAxisAlignment.START, spacing=8),
                    ft.Divider(height=1),
                    ft.Row([
                        ft.ElevatedButton(
                            "启动实例",
                            icon=ft.Icons.PLAY_ARROW,
                            on_click=self.start_instances,
                            style=ft.ButtonStyle(
                                bgcolor=ft.Colors.GREEN,
                                color=ft.Colors.WHITE,
                                text_style=ft.TextStyle(size=12),
                            ),
                            height=36,
                            expand=True,
                        ),
                        ft.ElevatedButton(
                            "停止所有",
                            icon=ft.Icons.STOP,
                            on_click=self.stop_all_instances,
                            style=ft.ButtonStyle(
                                bgcolor=ft.Colors.RED,
                                color=ft.Colors.WHITE,
                                text_style=ft.TextStyle(size=12),
                            ),
                            height=36,
                            expand=True,
                        ),
                        ft.ElevatedButton(
                            "刷新状态",
                            icon=ft.Icons.REFRESH,
                            on_click=self.refresh_status,
                            style=ft.ButtonStyle(
                                bgcolor=ft.Colors.BLUE,
                                color=ft.Colors.WHITE,
                                text_style=ft.TextStyle(size=12),
                            ),
                            height=36,
                            expand=True,
                        ),
                    ], spacing=6),
                ], spacing=10),
                padding=15,
            ),
            elevation=2,
        )
        
        # 实例状态卡片
        status_card = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.MONITOR, color=ft.Colors.ORANGE),
                        title=ft.Text("实例状态", weight=ft.FontWeight.BOLD),
                        subtitle=ft.Text("实时监控运行状态"),
                    ),
                    ft.Divider(),
                    self.create_status_table(),
                ], spacing=10),
                padding=20,
            ),
            elevation=2,
        )
        
        # 快速操作卡片
        quick_actions_card = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.FLASH_ON, color=ft.Colors.PURPLE),
                        title=ft.Text("快速操作", weight=ft.FontWeight.BOLD),
                        subtitle=ft.Text("常用功能快捷入口"),
                    ),
                    ft.Divider(),
                    ft.Column([
                        ft.ElevatedButton(
                            "打开WebUI",
                            icon=ft.Icons.OPEN_IN_BROWSER,
                            on_click=self.open_webui,
                            style=ft.ButtonStyle(
                                bgcolor=ft.Colors.INDIGO,
                                color=ft.Colors.WHITE,
                            ),
                            expand=True,
                        ),
                        ft.ElevatedButton(
                            "查看日志",
                            icon=ft.Icons.DESCRIPTION,
                            on_click=self.show_logs,
                            style=ft.ButtonStyle(
                                bgcolor=ft.Colors.TEAL,
                                color=ft.Colors.WHITE,
                            ),
                            expand=True,
                        ),
                    ], spacing=10),
                ], spacing=15),
                padding=20,
            ),
            elevation=2,
        )
        
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Container(
                        content=instance_control_card, 
                        expand=2,  # 给实例控制更多空间
                    ),
                    ft.Container(
                        content=quick_actions_card, 
                        expand=1,  # 快速操作占用较少空间
                        width=300,  # 限制最大宽度
                    ),
                ], spacing=15),
                ft.Container(
                    content=status_card, 
                    expand=True,
                    margin=ft.margin.only(top=15),
                ),
            ], spacing=0, scroll=ft.ScrollMode.AUTO),
            padding=10,
            expand=True,
        )
        
    def create_voice_synthesis_view(self):
        """创建语音合成视图"""
        # 音色选择卡片
        voice_card = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.RECORD_VOICE_OVER, color=ft.Colors.BLUE),
                        title=ft.Text("音色选择", weight=ft.FontWeight.BOLD, size=16),
                        subtitle=ft.Text("选择和试听音色文件", size=12),
                    ),
                    ft.Divider(),
                    ft.Container(
                                content=ft.Column([
                                    ft.Row([
                                        ft.Text("选择音色:", size=14, weight=ft.FontWeight.W_500),
                                        ft.Container(expand=True),  # 占位符
                                    ]),
                                    ft.Container(
                                        content=self.create_voice_selector_row(self.create_voice_dropdown(), "voice_category_dropdown"),
                                        width=None,  # 让下拉框自适应宽度
                                        margin=ft.margin.only(top=5),
                                    ),
                                ]),
                                margin=ft.margin.only(bottom=15),
                            ),
                    ft.Row([
                        (lambda: (
                            setattr(self, 'voice_sample_button', ft.ElevatedButton(
                                "试听音色",
                                icon=ft.Icons.PLAY_CIRCLE,
                                on_click=self.toggle_voice_sample_playback,
                                style=ft.ButtonStyle(
                                    bgcolor=ft.Colors.GREEN,
                                    color=ft.Colors.WHITE,
                                ),
                            )),
                            self.voice_sample_button
                        ))()[1],
                        ft.ElevatedButton(
                            "刷新音色",
                            icon=ft.Icons.REFRESH,
                            on_click=self.refresh_voices,
                            style=ft.ButtonStyle(
                                bgcolor=ft.Colors.ORANGE,
                                color=ft.Colors.WHITE,
                            ),
                        ),
                    ], spacing=15, wrap=True),
                ], spacing=10),
                padding=12,
            ),
            elevation=3,
        )

        # 音色控制与高级功能卡片
        # 初始化控件（保存为实例属性，供生成逻辑使用）
        self.emo_method_radio = ft.RadioGroup(
            content=ft.Row([
                ft.Radio(value="与音色参考音频相同", label="与音色参考音频相同"),
                ft.Radio(value="参考音频控制", label="参考音频控制"),
                ft.Radio(value="情绪控制", label="情绪控制"),
                ft.Radio(value="文本控制", label="文本控制"),
            ], wrap=True),
            value="与音色参考音频相同",
            on_change=lambda e: self.on_emo_method_change()
        )
        self.emo_random_checkbox = ft.Checkbox(label="随机情感", value=False, visible=False)
        self._emo_weight_text = ft.Text(f"{0.65:.2f}", size=12)
        self.emo_weight_slider = ft.Slider(
            min=0.0, 
            max=1.0, 
            divisions=100, 
            value=0.65, 
            label="情感权重: {value}", 
            width=200,
            on_change=lambda e: (
                setattr(self._emo_weight_text, "value", f"{float(e.control.value):.2f}"),
                self.page.update()
            )
        )
        # 文本控制组
        self.emo_text_input = ft.TextField(label="情感文本描述", hint_text="例如：愤怒、激动、平静...", visible=False)
        # 参考音频组
        self.emo_ref_path_input = ft.TextField(label="参考音频路径", read_only=True, visible=False)
        self.emo_ref_row_ref = ft.Ref[ft.Row]()
        # 文件选择器（一次性挂载到页面 overlay）
        if hasattr(self, 'page') and self.page:
            if not hasattr(self, 'emo_file_picker'):
                self.emo_file_picker = ft.FilePicker(on_result=self.on_emo_file_picked)
                self.page.overlay.append(self.emo_file_picker)
        self.pick_emo_file_button = ft.ElevatedButton(
            "选择参考音频",
            icon=ft.Icons.UPLOAD_FILE,
            on_click=lambda e: getattr(self, 'emo_file_picker', None) and self.emo_file_picker.pick_files(allow_multiple=False, file_type=ft.FilePickerFileType.AUDIO),
        )
        self.play_emo_ref_button = ft.ElevatedButton(
            "试听参考音频",
            icon=ft.Icons.PLAY_CIRCLE,
            on_click=self.toggle_emo_ref_playback,
        )
        # 向量控制组（8个情感维度）- 更紧凑布局：单行（图标+文字、滑块、数值）
        self.vec_names = ["喜", "怒", "哀", "惧", "厌恶", "低落", "惊喜", "平静"]
        self.vec_emojis = {
            "喜": "😊   ",
            "怒": "😠   ",
            "哀": "😢   ",
            "惧": "😨   ",
            "厌恶": "🤢",
            "低落": "😔",
            "惊喜": "😲",
            "平静": "😌",
        }
        self.vec_sliders = []
        self.vec_value_fields = []
        vec_cells = []
        for i, name in enumerate(self.vec_names):
            # 顶部显示：情感名称 + 只读数值框
            value_text = ft.Text(
                "0.00",
                size=12,
                text_align=ft.TextAlign.CENTER,
                color=ft.Colors.BLACK,
            )
            value_box = ft.Container(
                content=value_text,
                width=56,
                alignment=ft.alignment.center,
            )
            slider = ft.Slider(
                min=0.0,
                max=1.0,
                divisions=None,  # 移除过多分段，连续控制
                value=0.0,
                on_change=lambda e, idx=i: self.on_vec_slider_changed(idx, e.control.value),
                active_color=ft.Colors.BLUE_400,
                inactive_color=ft.Colors.GREY_300,
                thumb_color=ft.Colors.BLUE_600,
                height=24,
                expand=True,
            )

            self.vec_sliders.append(slider)
            self.vec_value_fields.append(value_text)

            # 单行紧凑排布：表情+文字 | 滑块（自适应） | 数值
            compact_row = ft.Row([
                ft.Text(f"{self.vec_emojis.get(name, '')} {name}", size=13, weight=ft.FontWeight.W_500),
                slider,
                value_box,
            ], spacing=8, alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.CENTER)

            cell = ft.Container(
                content=compact_row,
                expand=True,
                padding=ft.padding.all(6),
                border=ft.border.all(1, ft.Colors.OUTLINE),
                border_radius=10,
                bgcolor=ft.Colors.WHITE,
            )
            vec_cells.append(cell)

        # 两列网格排布
        vec_rows = []
        for j in range(0, len(vec_cells), 2):
            vec_rows.append(ft.Row([vec_cells[j], vec_cells[j+1]], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER))

        self.vec_group = ft.Column(vec_rows, spacing=4, visible=False)

        control_card = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.SETTINGS_VOICE, color=ft.Colors.ORANGE),
                        title=ft.Text("音色控制与高级功能", weight=ft.FontWeight.BOLD, size=16),
                        subtitle=ft.Text("对情感、参考音频、情绪控制等进行精细控制", size=12),
                    ),
                    ft.Divider(),
                    # 文本组移动到上方
                    ft.Container(content=self.emo_text_input),
                    ft.Text("情感控制方式", size=13, weight=ft.FontWeight.W_500),
                    self.emo_method_radio,
                    ft.Row([
                        self.emo_random_checkbox,
                        ft.Container(expand=True),
                        ft.Row([
                            ft.Text("情感权重:", size=12),
                            self.emo_weight_slider,
                            self._emo_weight_text
                        ], spacing=8, alignment=ft.MainAxisAlignment.END),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    # 参考音频组
                    ft.Row([
                        ft.Container(content=self.emo_ref_path_input, expand=True),
                        self.pick_emo_file_button,
                        self.play_emo_ref_button,
                    ], visible=False, ref=self.emo_ref_row_ref),
                    # 为了后续切换可见性，使用容器包裹
                    ft.Container(content=self.vec_group),
                ], spacing=8),
                padding=10,
            ),
            elevation=3,
        )

        # 文本输入卡片
        text_card = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.TEXT_FIELDS, color=ft.Colors.GREEN),
                        title=ft.Text("文本输入", weight=ft.FontWeight.BOLD, size=16),
                        subtitle=ft.Text("输入要合成的文本内容", size=12),
                    ),
                    ft.Divider(),
                    ft.Container(
                        content=self.create_text_input(),
                        margin=ft.margin.only(bottom=15),
                        expand=True,
                    ),
                    ft.Row([
                        ft.Text("语速:", size=12),
                        (lambda _cur=float(self.config_manager.get("speaking_speed", 1.0)):
                            (setattr(self, "_speed_text_generate", ft.Text(f"{_cur:.1f}x", size=12)),
                             ft.Slider(
                                min=0.1,
                                max=2.0,
                                divisions=19,
                                value=_cur,
                                label="",
                                on_change=lambda e: (
                                    setattr(self, "runtime_speaking_speed", e.control.value),
                                    setattr(self._speed_text_generate, "value", f"{float(e.control.value):.1f}x"),
                                    self.page.update()
                                ),
                                expand=True,
                             ))
                        )()[1],
                        (lambda: self._speed_text_generate)()
                    ], spacing=8),
                    ft.Row([
                        ft.Text("音量:", size=12),
                        (lambda _cur=int(self.config_manager.get("volume_percent", 100)):
                            (setattr(self, "_volume_text_generate", ft.Text(f"{_cur}%", size=12)),
                             ft.Slider(
                                min=50,
                                max=200,
                                divisions=150,
                                value=float(_cur),
                                label="",
                                on_change=lambda e: (
                                    setattr(self, "runtime_volume_percent", int(e.control.value)),
                                    setattr(self._volume_text_generate, "value", f"{int(e.control.value)}%"),
                                    self.page.update()
                                ),
                                expand=True,
                             ))
                        )()[1],
                    (lambda: self._volume_text_generate)()
                ], spacing=8),
                ft.Container(height=8),
                ft.Row([
                    (lambda: (
                        setattr(self, 'single_output_dir_field', ft.TextField(label="输出目录", read_only=True, width=420)),
                        self.single_output_dir_field
                    ))()[1],
                    (lambda: (
                        setattr(self, 'single_dir_picker', getattr(self, 'single_dir_picker', None) or ft.FilePicker(on_result=self.on_single_pick_output_dir_result)),
                        setattr(self, 'single_dir_picker_appended', False),
                        (self.page and self.single_dir_picker not in self.page.overlay and self.page.overlay.append(self.single_dir_picker)),
                        self.page and self.page.update(),
                        ft.ElevatedButton("选择输出目录", icon=ft.Icons.FOLDER_OPEN, on_click=lambda e: self.single_dir_picker.get_directory_path())
                    ))()[4],
                    ft.ElevatedButton("打开输出目录", icon=ft.Icons.FOLDER_OPEN, on_click=self.open_single_output_dir),
                ], spacing=15, wrap=True),
                ft.Row([
                    ft.ElevatedButton(
                        "生成语音",
                        icon=ft.Icons.GRAPHIC_EQ,
                        on_click=self.generate_speech,
                            style=ft.ButtonStyle(
                                bgcolor=ft.Colors.BLUE,
                                color=ft.Colors.WHITE,
                            ),
                        ),
                        ft.ElevatedButton(
                            "停止生成",
                            icon=ft.Icons.STOP,
                            on_click=self.stop_speech_generation,
                            style=ft.ButtonStyle(bgcolor=ft.Colors.RED_600, color=ft.Colors.WHITE),
                        ),
                        (lambda: (
                            setattr(self, 'play_result_button', ft.ElevatedButton(
                                "播放结果",
                                icon=ft.Icons.PLAY_ARROW,
                                on_click=self.play_generated_audio,
                                style=ft.ButtonStyle(
                                    bgcolor=ft.Colors.PURPLE,
                                    color=ft.Colors.WHITE,
                                ),
                            )),
                            self.play_result_button
                        ))()[1],
                        ft.ElevatedButton(
                            "删除生成音频",
                            icon=ft.Icons.DELETE,
                            on_click=self.delete_generated_audio,
                            style=ft.ButtonStyle(bgcolor=ft.Colors.RED_800, color=ft.Colors.WHITE),
                        ),
                        ft.ElevatedButton(
                            "打开文件位置",
                            icon=ft.Icons.FOLDER_OPEN,
                            on_click=self.open_audio_location,
                            style=ft.ButtonStyle(
                                bgcolor=ft.Colors.TEAL,
                                color=ft.Colors.WHITE,
                            ),
                        ),
                    ], spacing=15, wrap=True),
                ], spacing=10, expand=True),
                padding=12,
            ),
            elevation=3,
            expand=True,
        )

        # 状态显示卡片
        self.synthesis_status_card = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.INFO, color=ft.Colors.BLUE),
                        title=ft.Text("生成状态", weight=ft.FontWeight.BOLD, size=16),
                        subtitle=ft.Text("语音合成状态信息", size=12),
                    ),
                    ft.Divider(),
                    ft.Container(
                        content=ft.Column([
                            ft.Row([
                                ft.Text("当前状态:", size=14, weight=ft.FontWeight.W_500),
                                self.create_synthesis_status_text(),
                            ]),
                            ft.Row([
                                ft.Text("生成文件:", size=14, weight=ft.FontWeight.W_500),
                                self.create_synthesis_file_text(),
                            ]),
                            ft.Row([
                                ft.Text("生成时间:", size=14, weight=ft.FontWeight.W_500),
                                self.create_synthesis_time_text(),
                            ]),
                        ], spacing=10),
                        margin=ft.margin.only(bottom=15),
                    ),
                ], spacing=15),
                padding=12,
            ),
            elevation=3,
        )

        # 语音合成页不再内嵌生成记录卡片，统一迁移到一级“生成记录”页面

        # 左右分栏布局 - 优化版：左侧主要工作区（文本），右侧配置区
        # 左侧：工作区（文本输入、操作）
        main_col = ft.Column([
            text_card
        ], spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)

        # 右侧：配置区（音色、参数、状态）
        side_col = ft.Column([
            voice_card,
            control_card,
            self.synthesis_status_card
        ], spacing=10, scroll=ft.ScrollMode.AUTO)

        return ft.Container(
            content=ft.Row([
                ft.Container(content=main_col, expand=True),
                ft.VerticalDivider(width=1),
                ft.Container(content=side_col, width=450) # 限制右侧配置栏宽度
            ], spacing=10, expand=True),
            padding=10,
            expand=True,
        )

    def create_asr_view(self):
        """创建语音转字幕(ASR)视图"""
        # 确保默认输出目录存在，用于文件选择器初始路径
        default_outputs_dir = os.path.join(project_root, "outputs")
        if not os.path.exists(default_outputs_dir):
            try:
                os.makedirs(default_outputs_dir)
            except Exception:
                pass

        # 音频文件选择
        self.asr_audio_path_field = ft.TextField(label="音频文件路径", read_only=True, expand=True)
        self.asr_file_picker = ft.FilePicker(on_result=self.on_asr_file_picked)
        if hasattr(self, 'page') and self.page:
            if self.asr_file_picker not in self.page.overlay:
                self.page.overlay.append(self.asr_file_picker)
            
        # 模型选择
        self.asr_model_dropdown = ft.Dropdown(
            label="Whisper模型",
            options=[
                ft.dropdown.Option("turbo", "turbo (推荐)"),
                ft.dropdown.Option("large-v3", "large-v3"),
                ft.dropdown.Option("medium", "medium"),
                ft.dropdown.Option("small", "small"),
                ft.dropdown.Option("base", "base"),
                ft.dropdown.Option("tiny", "tiny"),
            ],
            value="turbo",
            width=200,
        )
        
        # 输出路径
        self.asr_output_field = ft.TextField(label="输出SRT文件路径", value="output.srt", expand=True)
        
        # 进度和日志
        self.asr_status_text = ft.Text("准备就绪", color=ft.Colors.GREY)
        self.asr_progress = ft.ProgressBar(visible=False)
        
        card = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.CLOSED_CAPTION, color=ft.Colors.BLUE),
                        title=ft.Text("语音转字幕 (Whisper)", weight=ft.FontWeight.BOLD, size=16),
                        subtitle=ft.Text("使用OpenAI Whisper模型将音频识别为SRT字幕", size=12),
                    ),
                    ft.Divider(),
                    ft.Row([
                        self.asr_audio_path_field,
                        ft.ElevatedButton("选择音频", icon=ft.Icons.AUDIO_FILE, on_click=lambda _: self.asr_file_picker.pick_files(
                            allow_multiple=False, 
                            file_type=ft.FilePickerFileType.AUDIO,
                            initial_directory=os.path.join(project_root, "outputs")
                        )),
                    ]),
                    ft.Row([
                        self.asr_model_dropdown,
                        self.asr_output_field,
                    ]),
                    ft.Row([
                        ft.ElevatedButton("开始生成", icon=ft.Icons.PLAY_ARROW, on_click=self.start_asr_generation, style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE)),
                        ft.ElevatedButton("打开文件位置", icon=ft.Icons.FOLDER, on_click=self.open_asr_output_folder),
                    ]),
                    ft.Divider(),
                    self.asr_status_text,
                    self.asr_progress,
                ], spacing=20),
                padding=20,
            ),
            elevation=3,
        )
        return ft.Container(content=card, padding=10, expand=True)

    def on_asr_file_picked(self, e: ft.FilePickerResultEvent):
        if e.files and len(e.files) > 0:
            path = e.files[0].path
            self.asr_audio_path_field.value = path
            # 自动设置输出路径
            base_dir = os.path.dirname(path)
            base_name = os.path.splitext(os.path.basename(path))[0]
            self.asr_output_field.value = os.path.join(base_dir, f"{base_name}.srt")
            self.page.update()

    def start_asr_generation(self, e):
        audio_path = self.asr_audio_path_field.value
        if not audio_path or not os.path.exists(audio_path):
            self.show_message("请先选择有效的音频文件", True)
            return
            
        model_name = self.asr_model_dropdown.value
        output_path = self.asr_output_field.value
        
        self.asr_status_text.value = "正在加载模型并生成字幕，请稍候..."
        self.asr_status_text.color = ft.Colors.BLUE
        self.asr_progress.visible = True
        self.page.update()
        
        import threading
        threading.Thread(target=self._run_asr_task, args=(audio_path, model_name, output_path), daemon=True).start()

    def _run_asr_task(self, audio_path, model_name, output_path):
        w = None
        try:
            import whisper
            import torch
            import gc
            from datetime import timedelta
            
            def format_timestamp(seconds: float) -> str:
                td = timedelta(seconds=seconds)
                total_seconds = int(td.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                secs = total_seconds % 60
                ms = int((td.total_seconds() - total_seconds) * 1000)
                return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"

            # 优先检查本地模型
            local_model_map = {
                "turbo": os.path.join(project_root, "models", "large-v3-turbo.pt"),
                "large-v3": os.path.join(project_root, "models", "large-v3.pt"),
                "medium": os.path.join(project_root, "models", "medium.pt"),
                "base": os.path.join(project_root, "models", "base.pt"),
                "small": os.path.join(project_root, "models", "small.pt"),
                "tiny": os.path.join(project_root, "models", "tiny.pt"),
            }
            
            load_path = model_name
            if model_name in local_model_map:
                local_path = local_model_map[model_name]
                if os.path.exists(local_path):
                    print(f"Loading local model from: {local_path}")
                    load_path = local_path
            
            # 加载模型
            w = whisper.load_model(load_path)
            
            # 转写
            result = w.transcribe(
                audio_path,
                language="zh",
                word_timestamps=True,
                verbose=False
            )
            segments = result["segments"]
            
            # 写入SRT
            with open(output_path, "w", encoding="utf-8") as f:
                for idx, seg in enumerate(segments, 1):
                    start = format_timestamp(seg["start"])
                    end = format_timestamp(seg["end"])
                    text = seg["text"].strip()
                    if not text:
                        continue
                    f.write(f"{idx}\n")
                    f.write(f"{start} --> {end}\n")
                    f.write(f"{text}\n\n")
            
            if hasattr(self, 'page') and self.page:
                self._on_asr_complete(output_path)
                
        except Exception as ex:
            if hasattr(self, 'page') and self.page:
                self._on_asr_error(str(ex))
        finally:
            # 释放模型和显存
            try:
                if w is not None:
                    del w
                if 'gc' in locals():
                    gc.collect()
                if 'torch' in locals() and torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

    def _on_asr_complete(self, output_path):
        self.asr_status_text.value = f"生成成功！文件已保存至: {output_path}"
        self.asr_status_text.color = ft.Colors.GREEN
        self.asr_progress.visible = False
        self.show_message("字幕生成成功")
        self.page.update()

    def _on_asr_error(self, error_msg):
        self.asr_status_text.value = f"生成失败: {error_msg}"
        self.asr_status_text.color = ft.Colors.RED
        self.asr_progress.visible = False
        self.show_message(f"字幕生成失败: {error_msg}", True)
        self.page.update()

    def open_asr_output_folder(self, e):
        path = self.asr_output_field.value
        if path:
            folder = os.path.dirname(path)
            if os.path.exists(folder):
                os.startfile(folder)

    def create_voice_library_view(self):
        # 如果正在扫描且没有缓存的音色文件，显示加载中
        if getattr(self, '_is_scanning', False) and not self.voice_files:
             return ft.Container(
                 content=ft.Column([
                     ft.ProgressRing(),
                     ft.Text("正在扫描音色库...", size=14, color=ft.Colors.GREY)
                 ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                 alignment=ft.alignment.center,
                 expand=True
             )

        # Group voices by folder
        voice_folder = Path("yinse")
        groups = {} # folder_name -> list of paths
        
        for p in self.voice_files:
            try:
                rel = p.relative_to(voice_folder)
                folder = rel.parent
                if str(folder) == ".":
                    group_name = "根目录"
                else:
                    group_name = str(folder)
            except:
                group_name = "其他"
            
            if group_name not in groups:
                groups[group_name] = []
            groups[group_name].append(p)

        if not hasattr(self, 'voice_library_selected'):
            try:
                loaded = self.config_manager.get("voice_library_selected", [])
                if isinstance(loaded, list):
                    self.voice_library_selected = set(loaded)
                else:
                    self.voice_library_selected = set()
            except Exception:
                self.voice_library_selected = set()
        
        def make_item_row(p: Path):
            path_str = str(p.absolute())
            custom_names = self.config_manager.get('voice_custom_names', {}) or {}
            
            # Determine display name
            try:
                rel = p.relative_to(voice_folder)
                if str(rel.parent) == ".":
                    display_base = p.name
                else:
                    display_base = f"{rel.parent.name}/{p.name}"
            except:
                display_base = p.name
                
            name = custom_names.get(path_str, display_base)
            dsec = self.get_audio_duration_seconds(path_str)
            dtxt = self.format_duration(dsec)
            
            cb = ft.Checkbox(
                value=False, 
                on_change=lambda e, s=path_str: self.on_library_item_select_change(s, e.control.value)
            )
            
            # Action buttons
            edit_btn = ft.IconButton(
                icon=ft.Icons.EDIT, 
                tooltip="重命名", 
                on_click=lambda e, s=path_str: self.edit_voice_name(s),
                icon_size=16
            )
            play_btn = ft.IconButton(
                icon=ft.Icons.PLAY_CIRCLE, 
                tooltip="试听", 
                on_click=lambda e, s=path_str: self.toggle_library_play(s, e.control), 
                icon_color=ft.Colors.GREEN_600,
                icon_size=16
            )
            del_btn = ft.IconButton(
                icon=ft.Icons.DELETE, 
                tooltip="删除", 
                on_click=lambda e, s=path_str: self.delete_voice(s), 
                icon_color=ft.Colors.RED_400,
                icon_size=16
            )
            
            name_text = ft.Text(name if not dtxt else f"{name} ({dtxt})", size=12, expand=True)
            
            return ft.Row([cb, name_text, edit_btn, play_btn, del_btn], spacing=2, alignment=ft.MainAxisAlignment.START)

        # Build controls list with ExpansionTiles
        list_controls = []
        
        # Sort groups: root first, then alphabetical
        sorted_groups = sorted(groups.keys(), key=lambda k: "" if k == "根目录" else k.lower())
        
        for group_name in sorted_groups:
            files = groups[group_name]
            rows = [make_item_row(p) for p in files]
            
            if group_name == "根目录":
                # 根目录仅显示文件列表
                if len(groups) > 1:
                     list_controls.append(ft.Text("根目录", weight=ft.FontWeight.BOLD, size=14, color=ft.Colors.BLUE))
                list_controls.extend(rows)
            else:
                # 分组：标题中增加文件夹删除按钮
                title_row = ft.Row([
                    ft.Text(f"{group_name} ({len(files)})", size=13, weight=ft.FontWeight.W_500),
                    ft.Container(expand=True),
                    ft.IconButton(
                        icon=ft.Icons.FOLDER_DELETE,
                        tooltip="删除此文件夹及其下所有音色",
                        icon_color=ft.Colors.RED_400,
                        icon_size=18,
                        on_click=lambda _e, g=group_name: self.delete_voice_folder(g),
                    ),
                ], spacing=4, alignment=ft.MainAxisAlignment.START)

                tile = ft.ExpansionTile(
                    title=title_row,
                    controls=rows,
                    initially_expanded=False,
                    text_color=ft.Colors.BLUE,
                    controls_padding=ft.padding.only(left=20)
                )
                list_controls.append(tile)

        self.voice_library_list = ft.ListView(spacing=2, auto_scroll=False, controls=list_controls, height=420)
        
        self.voice_library_container = ft.Container(
            content=self.voice_library_list,
            height=400,
            padding=8,
            border=ft.border.all(1, ft.Colors.OUTLINE),
            border_radius=8,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )
        
        self.voice_lib_select_all_checkbox = ft.Checkbox(label="全选", value=False, on_change=self.on_library_select_all_change)
        
        self.voice_library_search_field = ft.TextField(
            label="搜索音色",
            width=200,
            height=36,
            content_padding=ft.padding.symmetric(horizontal=10, vertical=0),
            text_size=12,
            on_change=self.on_voice_library_search_change
        )
        self.voice_library_count_text = ft.Text(f"已选用于AI: {len(self.voice_library_selected)}/20", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE)

        self.voice_library_play_btn = ft.ElevatedButton("试听", icon=ft.Icons.PLAY_CIRCLE, on_click=self.play_selected_voice, style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_600, color=ft.Colors.WHITE, padding=10))

        header_row = ft.Row([
            self.voice_library_search_field,
            self.voice_library_count_text,
            ft.ElevatedButton("添加", icon=ft.Icons.UPLOAD_FILE, on_click=self.open_voice_file_picker, style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE, padding=10)),
            ft.ElevatedButton("添加文件夹", icon=ft.Icons.CREATE_NEW_FOLDER, on_click=self.open_voice_folder_picker, style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_GREY_600, color=ft.Colors.WHITE, padding=10)),
            ft.ElevatedButton("刷新", icon=ft.Icons.REFRESH, on_click=self.refresh_voices_and_library, style=ft.ButtonStyle(bgcolor=ft.Colors.ORANGE_600, color=ft.Colors.WHITE, padding=10)),
            # self.voice_lib_select_all_checkbox, # 移除全选，避免误选过多
            ft.ElevatedButton("清空选择", icon=ft.Icons.CLEAR_ALL, on_click=self.clear_library_selection, style=ft.ButtonStyle(bgcolor=ft.Colors.GREY_600, color=ft.Colors.WHITE, padding=10)),
            ft.ElevatedButton("删除", icon=ft.Icons.DELETE_SWEEP, on_click=self.delete_selected_voices, style=ft.ButtonStyle(bgcolor=ft.Colors.RED_600, color=ft.Colors.WHITE, padding=10)),
            self.voice_library_play_btn,
            ft.ElevatedButton("导出", icon=ft.Icons.DRIVE_FILE_MOVE, on_click=self.export_selected_voices, style=ft.ButtonStyle(bgcolor=ft.Colors.PURPLE_600, color=ft.Colors.WHITE, padding=10)),
        ], spacing=8, wrap=True)
        
        card = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.LIBRARY_MUSIC, color=ft.Colors.BLUE),
                        title=ft.Text("音色库管理", weight=ft.FontWeight.BOLD, size=16),
                        subtitle=ft.Text("管理音色文件与分类，支持批量操作与导出", size=12),
                    ),
                    ft.Divider(),
                    header_row,
                    ft.Divider(),
                    self.voice_library_container,
                ], spacing=12),
                padding=12,
            ),
            elevation=3,
        )
        return ft.Container(content=card, padding=10, expand=True)

    def on_file_drop(self, e):
        try:
            files = getattr(e, 'files', None) or []
            if not files:
                return
            dest_dir = Path("yinse")
            dest_dir.mkdir(parents=True, exist_ok=True)
            allowed_exts = {".wav", ".mp3", ".wma", ".flac", ".ogg", ".m4a", ".aac", ".opus"}
            saved = []
            for f in files:
                src_path = getattr(f, 'path', None)
                if not src_path or not os.path.exists(src_path):
                    continue
                ext = Path(src_path).suffix.lower()
                if ext not in allowed_exts:
                    continue
                target_name = Path(src_path).name
                target_path = dest_dir / target_name
                if target_path.exists():
                    base = target_path.stem
                    ext2 = target_path.suffix
                    idx = 1
                    while True:
                        candidate = dest_dir / f"{base}_{idx}{ext2}"
                        if not candidate.exists():
                            target_path = candidate
                            break
                        idx += 1
                shutil.copy2(src_path, target_path)
                saved.append(str(target_path))
            if saved:
                self.show_message(f"拖拽添加 {len(saved)} 个音色文件")
                self.refresh_voices()
                try:
                    self.refresh_voice_library()
                except Exception:
                    pass
        except Exception as ex:
            self.show_message(f"拖拽上传失败: {ex}", True)

    def refresh_voices_and_library(self, e=None):
        try:
            def on_done():
                self.refresh_voice_library()
                self.show_message("音色库已刷新")
            self.scan_voice_files(on_complete=on_done)
        except Exception:
            pass

    def on_voice_library_search_change(self, e):
        self.refresh_voice_library()

    def clear_library_selection(self, e):
        self.voice_library_selected.clear()
        self.config_manager.set("voice_library_selected", [])
        self.refresh_voice_library()
        self.show_message("已清空选择")

    def refresh_voice_library(self):
        try:
            # Group voices by folder
            voice_folder = Path("yinse")
            groups = {}
            search_text = (self.voice_library_search_field.value or "").lower() if hasattr(self, 'voice_library_search_field') else ""
            
            # Update Count
            if hasattr(self, 'voice_library_count_text'):
                self.voice_library_count_text.value = f"已选用于AI: {len(self.voice_library_selected)}/20"
                if len(self.voice_library_selected) > 20:
                    self.voice_library_count_text.color = ft.Colors.RED
                else:
                    self.voice_library_count_text.color = ft.Colors.BLUE

            for p in self.voice_files:
                # Search filter
                if search_text:
                    if search_text not in p.name.lower():
                        continue

                try:
                    rel = p.relative_to(voice_folder)
                    folder = rel.parent
                    if str(folder) == ".":
                        group_name = "根目录"
                    else:
                        group_name = str(folder)
                except:
                    group_name = "其他"
                
                if group_name not in groups:
                    groups[group_name] = []
                groups[group_name].append(p)
            
            def make_item_row(p: Path):
                path_str = str(p.absolute())
                custom_names = self.config_manager.get('voice_custom_names', {}) or {}
                
                try:
                    rel = p.relative_to(voice_folder)
                    if str(rel.parent) == ".":
                        display_base = p.name
                    else:
                        display_base = f"{rel.parent.name}/{p.name}"
                except:
                    display_base = p.name
                    
                name = custom_names.get(path_str, display_base)
                dsec = self.get_audio_duration_seconds(path_str)
                dtxt = self.format_duration(dsec)
                
                cb = ft.Checkbox(
                    value=(path_str in self.voice_library_selected), 
                    on_change=lambda e, s=path_str: self.on_library_item_select_change(s, e.control.value)
                )
                
                edit_btn = ft.IconButton(icon=ft.Icons.EDIT, tooltip="重命名", on_click=lambda e, s=path_str: self.edit_voice_name(s), icon_size=16)
                play_btn = ft.IconButton(icon=ft.Icons.PLAY_CIRCLE, tooltip="试听", on_click=lambda e, s=path_str: self.toggle_library_play(s, e.control), icon_color=ft.Colors.GREEN_600, icon_size=16)
                del_btn = ft.IconButton(icon=ft.Icons.DELETE, tooltip="删除", on_click=lambda e, s=path_str: self.delete_voice(s), icon_color=ft.Colors.RED_400, icon_size=16)
                
                name_text = ft.Text(name if not dtxt else f"{name} ({dtxt})", size=12, expand=True)
                return ft.Row([cb, name_text, edit_btn, play_btn, del_btn], spacing=2, alignment=ft.MainAxisAlignment.START)

            list_controls = []
            sorted_groups = sorted(groups.keys(), key=lambda k: "" if k == "根目录" else k.lower())
            
            for group_name in sorted_groups:
                files = groups[group_name]
                rows = [make_item_row(p) for p in files]
                
                if group_name == "根目录":
                    if len(groups) > 1:
                         list_controls.append(ft.Text("根目录", weight=ft.FontWeight.BOLD, size=14, color=ft.Colors.BLUE))
                    list_controls.extend(rows)
                else:
                    # 搜索模式：全部展开；标题中加入文件夹删除按钮
                    init_expand = bool(search_text)

                    title_row = ft.Row([
                        ft.Text(f"{group_name} ({len(files)})", size=13, weight=ft.FontWeight.W_500),
                        ft.Container(expand=True),
                        ft.IconButton(
                            icon=ft.Icons.FOLDER_DELETE,
                            tooltip="删除此文件夹及其下所有音色",
                            icon_color=ft.Colors.RED_400,
                            icon_size=18,
                            on_click=lambda _e, g=group_name: self.delete_voice_folder(g),
                        ),
                    ], spacing=4, alignment=ft.MainAxisAlignment.START)

                    tile = ft.ExpansionTile(
                        title=title_row,
                        controls=rows,
                        initially_expanded=init_expand,
                        text_color=ft.Colors.BLUE,
                        controls_padding=ft.padding.only(left=20)
                    )
                    list_controls.append(tile)

            if getattr(self, 'voice_library_list', None):
                self.voice_library_list.controls = list_controls
            if hasattr(self, 'page') and self.page:
                self.page.update()
        except Exception:
            pass


    def on_library_select_all_change(self, e):
        try:
            val = bool(getattr(e.control, 'value', False))
            self.voice_library_selected = set(str(p.absolute()) for p in self.voice_files) if val else set()
            self.config_manager.set("voice_library_selected", list(self.voice_library_selected))
            self.refresh_voice_library()
        except Exception:
            pass

    def on_library_item_select_change(self, path_str: str, selected: bool):
        try:
            if selected:
                self.voice_library_selected.add(path_str)
            else:
                self.voice_library_selected.discard(path_str)
            
            # Update Count
            if hasattr(self, 'voice_library_count_text'):
                self.voice_library_count_text.value = f"已选用于AI: {len(self.voice_library_selected)}/20"
                if len(self.voice_library_selected) > 20:
                    self.voice_library_count_text.color = ft.Colors.RED
                else:
                    self.voice_library_count_text.color = ft.Colors.BLUE
                self.voice_library_count_text.update()
            
            # Save to config
            self.config_manager.set("voice_library_selected", list(self.voice_library_selected))
        except Exception:
            pass

    def on_gender_changed(self, path_str: str, gender: str):
        try:
            pass
        except Exception:
            pass

    def edit_voice_name(self, path_str: str):
        try:
            custom_names = self.config_manager.get('voice_custom_names', {}) or {}
            current = custom_names.get(path_str, os.path.basename(path_str))
            tf = ft.TextField(value=current, label="音色名称", width=280)
            def _save(_e=None):
                name = (tf.value or "").strip()
                if not name:
                    return
                custom_names[path_str] = name
                self.config_manager.set('voice_custom_names', custom_names)
                try:
                    self.refresh_voices()
                    self.refresh_voice_library()
                except Exception:
                    pass
                dlg.open = False
                if hasattr(self, 'page') and self.page:
                    self.page.update()
            dlg = ft.AlertDialog(title=ft.Text("重命名音色"), content=tf, actions=[ft.TextButton("取消", on_click=lambda e: (setattr(dlg, 'open', False), self.page.update() if hasattr(self, 'page') and self.page else None)), ft.ElevatedButton("保存", on_click=_save)])
            if hasattr(self, 'page') and self.page:
                try:
                    if dlg not in self.page.overlay:
                        self.page.overlay.append(dlg)
                    dlg.open = True
                    self.page.update()
                except Exception:
                    try:
                        self.page.dialog = dlg
                        dlg.open = True
                        self.page.update()
                    except Exception:
                        pass
        except Exception:
            pass

    def delete_selected_voices(self, e=None):
        try:
            to_del = list(self.voice_library_selected)
            cnt = 0
            for p in to_del:
                try:
                    if os.path.isfile(p):
                        os.remove(p)
                        cnt += 1
                except Exception:
                    pass
            self.voice_library_selected.clear()
            self.config_manager.set("voice_library_selected", [])
            self.refresh_voices_and_library()
            self.show_message(f"已删除 {cnt} 个音色")
        except Exception as ex:
            self.show_message(f"删除失败: {ex}", True)

    def export_selected_voices(self, e=None):
        """导出选中的音色"""
        try:
            if not self.voice_library_selected:
                self.show_message("请先勾选音色", True)
                return
            
            # Use FilePicker to select directory
            if not hasattr(self, 'export_dir_picker'):
                self.export_dir_picker = ft.FilePicker(on_result=self.on_export_dir_selected)
                self.page.overlay.append(self.export_dir_picker)
                self.page.update()
                
            self.export_dir_picker.get_directory_path()
        except Exception as ex:
            self.show_message(f"准备导出失败: {ex}", True)

    def on_export_dir_selected(self, e: ft.FilePickerResultEvent):
        """导出目录选择回调"""
        try:
            path = getattr(e, 'path', None)
            if not path:
                return
                
            dest_dir = Path(path)
            count = 0
            for voice_path_str in self.voice_library_selected:
                try:
                    src = Path(voice_path_str)
                    if src.exists():
                        target_name = src.name
                        target_path = dest_dir / target_name
                        
                        # 处理重名
                        if target_path.exists():
                            base = target_path.stem
                            ext = target_path.suffix
                            idx = 1
                            while True:
                                candidate = dest_dir / f"{base}_{idx}{ext}"
                                if not candidate.exists():
                                    target_path = candidate
                                    break
                                idx += 1
                                
                        shutil.copy2(src, target_path)
                        count += 1
                except Exception:
                    pass
            
            self.show_message(f"已成功导出 {count} 个音色到 {path}")
        except Exception as ex:
            self.show_message(f"导出失败: {ex}", True)

    def delete_voice_folder(self, group_name: str):
        """删除音色库中的一个文件夹（及其下所有音色文件）"""
        try:
            # 根目录与“其他”分组不支持整体删除
            if not group_name or group_name in ("根目录", "其他"):
                self.show_message("此分组不支持整体删除", True)
                return

            voice_folder = Path("yinse")
            folder_path = voice_folder / group_name

            if not folder_path.exists() or not folder_path.is_dir():
                self.show_message("对应文件夹不存在，可能已被删除", True)
                return

            try:
                shutil.rmtree(folder_path)
            except Exception as ex:
                self.show_message(f"删除文件夹失败: {ex}", True)
                return

            # 清理已选中的音色，移除所有来自该文件夹的路径
            try:
                new_selected = set()
                for p in list(self.voice_library_selected):
                    try:
                        pp = Path(p)
                        rel = pp.relative_to(folder_path)
                        # 能 relative_to 成功说明在被删文件夹内，跳过
                        _ = rel
                    except Exception:
                        new_selected.add(p)
                self.voice_library_selected = new_selected
                self.config_manager.set("voice_library_selected", list(self.voice_library_selected))
            except Exception:
                pass

            # 重新扫描音色并刷新音色库
            try:
                self.refresh_voices_and_library()
            except Exception:
                try:
                    self.refresh_voice_library()
                except Exception:
                    pass

            self.show_message(f"已删除文件夹: {group_name}")
        except Exception as ex:
            self.show_message(f"删除文件夹时出错: {ex}", True)

    def delete_voice(self, path_str: str):
        try:
            if os.path.isfile(path_str):
                os.remove(path_str)
            self.voice_library_selected.discard(path_str)
            self.config_manager.set("voice_library_selected", list(self.voice_library_selected))
            self.refresh_voices_and_library()
            self.show_message("已删除音色")
        except Exception as ex:
            self.show_message(f"删除失败: {ex}", True)

    def play_selected_voice(self, e=None):
        try:
            if not self.voice_library_selected:
                self.show_message("请先勾选音色", True)
                return
            p = next(iter(self.voice_library_selected))
            
            # Check if playing same file
            if getattr(self, 'current_audio_file', None) == p and pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
                if hasattr(self, 'voice_library_play_btn'):
                    self.voice_library_play_btn.icon = ft.Icons.PLAY_CIRCLE
                    self.voice_library_play_btn.text = "试听"
                    self.voice_library_play_btn.style = ft.ButtonStyle(bgcolor=ft.Colors.GREEN_600, color=ft.Colors.WHITE, padding=10)
                if hasattr(self, 'page') and self.page:
                    self.page.update()
                return

            self.play_voice_path(p)
            self.current_audio_file = p
            
            # Update button to Stop state
            if hasattr(self, 'voice_library_play_btn'):
                self.voice_library_play_btn.icon = ft.Icons.STOP
                self.voice_library_play_btn.text = "停止"
                self.voice_library_play_btn.style = ft.ButtonStyle(bgcolor=ft.Colors.RED_400, color=ft.Colors.WHITE, padding=10)
            if hasattr(self, 'page') and self.page:
                self.page.update()
                
        except Exception as ex:
            self.show_message(f"播放失败: {ex}", True)

    def play_voice_path(self, path_str: str):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
            if os.path.exists(path_str):
                pygame.mixer.music.load(path_str)
                pygame.mixer.music.play()
                self.show_message("正在播放音色")
        except Exception as ex:
            self.show_message(f"播放失败: {ex}", True)

    def toggle_emo_ref_playback(self, e=None):
        try:
            path = getattr(self.emo_ref_path_input, 'value', '') or ''
            path = path.strip()
            if not path or not os.path.isfile(path):
                self.show_message("请先选择参考音频", True)
                return
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            if getattr(self, 'emo_ref_playing', False) and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
                self.emo_ref_playing = False
                if getattr(self, 'play_emo_ref_button', None):
                    self.play_emo_ref_button.text = "试听参考音频"
                    self.play_emo_ref_button.icon = ft.Icons.PLAY_CIRCLE
                if self.page:
                    self.page.update()
                return
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            self.emo_ref_playing = True
            if getattr(self, 'play_emo_ref_button', None):
                self.play_emo_ref_button.text = "停止参考音频"
                self.play_emo_ref_button.icon = ft.Icons.STOP
            if self.page:
                self.page.update()
        except Exception as ex:
            self.show_message(f"参考音频播放失败: {ex}", True)

    def add_generation_record(self, file_path: str, text: str):
        try:
            ts = datetime.now().strftime('%H:%M:%S')
            h_data = {'time': ts, 'file': file_path, 'text': (text[:40] if text else '')}
            
            # 使用统一的构建方法创建新项
            item = self.build_history_item_control(h_data)
            
            if getattr(self, 'generation_history_list', None):
                self.generation_history_list.controls.insert(0, item)
                
            hist = self.config_manager.get('generation_history', []) or []
            hist.insert(0, h_data)
            self.config_manager.set('generation_history', hist[:500])
            if hasattr(self, 'page') and self.page:
                self.page.update()
        except Exception:
            pass

    def clear_generation_history(self, e=None):
        try:
            self.config_manager.set('generation_history', [])
            if getattr(self, 'generation_history_list', None):
                self.generation_history_list.controls.clear()
            if hasattr(self, 'page') and self.page:
                self.page.update()
        except Exception:
            pass

    def build_history_item_control(self, h):
        fp = h.get('file')
        ts = h.get('time')
        name = os.path.basename(fp) if fp else '未知文件'
        
        # 判断文件是否存在
        file_exists = False
        try:
            if fp and os.path.exists(fp):
                file_exists = True
        except:
            pass
            
        ext = os.path.splitext(fp or '')[1].lower()
        is_audio = ext in ['.wav', '.mp3', '.wma', '.flac', '.ogg', '.m4a', '.aac', '.opus']
        
        # 左侧图标
        icon = ft.Icons.AUDIO_FILE if is_audio else ft.Icons.INSERT_DRIVE_FILE
        icon_color = ft.Colors.BLUE if file_exists else ft.Colors.GREY
        
        # 中间信息
        info_col = ft.Column([
            ft.Text(name, weight=ft.FontWeight.BOLD, size=14, overflow=ft.TextOverflow.ELLIPSIS),
            ft.Row([
                ft.Icon(ft.Icons.ACCESS_TIME, size=12, color=ft.Colors.GREY),
                ft.Text(f"{ts}", size=12, color=ft.Colors.GREY),
                ft.Container(width=10),
                ft.Icon(ft.Icons.FOLDER_OPEN, size=12, color=ft.Colors.GREY),
                ft.Text(fp or "路径未知", size=12, color=ft.Colors.GREY, overflow=ft.TextOverflow.ELLIPSIS)
            ], spacing=2, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        ], spacing=4, expand=True)
        
        # 右侧按钮
        actions = []
        if is_audio and file_exists:
            actions.append(ft.IconButton(
                icon=ft.Icons.PLAY_ARROW, 
                tooltip="播放", 
                icon_color=ft.Colors.GREEN,
                on_click=lambda e, p=fp: self.toggle_history_play(p, e.control)
            ))
        
        if file_exists:
            actions.append(ft.IconButton(
                icon=ft.Icons.FOLDER, 
                tooltip="打开位置", 
                icon_color=ft.Colors.BLUE,
                on_click=lambda e, p=fp: self.open_audio_location_for(p)
            ))
            
        actions.append(ft.IconButton(
            icon=ft.Icons.DELETE, 
            tooltip="删除记录", 
            icon_color=ft.Colors.RED,
            on_click=lambda e, p=fp: self.delete_generation_record(p)
        ))

        # 选择框
        cb = ft.Checkbox(value=False)
        cb.data = h
        if not hasattr(self, 'history_checkboxes'):
            self.history_checkboxes = []
        self.history_checkboxes.append(cb)
        
        return ft.Card(
            content=ft.Container(
                content=ft.Row([
                    cb,
                    ft.Container(
                        content=ft.Icon(icon, size=24, color=icon_color),
                        padding=10,
                        bgcolor=ft.Colors.BLUE_50 if file_exists else ft.Colors.GREY_100,
                        border_radius=8,
                    ),
                    info_col,
                    ft.Row(actions, spacing=0)
                ], spacing=10, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                padding=10,
            ),
            elevation=1,
            margin=ft.margin.only(bottom=5)
        )

    def delete_generation_record(self, file_path: str):
        try:
            if file_path and os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass
            hist = self.config_manager.get('generation_history', []) or []
            new_hist = []
            removed = False
            for h in hist:
                if not removed and h.get('file') == file_path:
                    removed = True
                    continue
                new_hist.append(h)
            self.config_manager.set('generation_history', new_hist)
            try:
                # 重新构建列表以保证UI与配置一致
                self.history_checkboxes = []
                self.generation_history_list.controls = []
                # 反转显示，保持最新的在最上面
                display_hist = list(reversed(new_hist))
                for h in display_hist:
                    self.generation_history_list.controls.append(self.build_history_item_control(h))
            except Exception:
                pass
            if hasattr(self, 'page') and self.page:
                self.page.update()
            self.show_message("已删除该生成音频并移除记录")
        except Exception as ex:
            self.show_message(f"删除失败: {ex}", True)

    def delete_recent_audio(self, e=None):
        try:
            hist = self.config_manager.get('generation_history', []) or []
            if not hist:
                self.show_message("暂无生成记录", True)
                return
            item = hist[0]
            fp = item.get('file')
            if fp and os.path.isfile(fp):
                try:
                    os.remove(fp)
                except Exception:
                    pass
            # 更新记录列表与UI
            hist = hist[1:]
            self.config_manager.set('generation_history', hist)
            if getattr(self, 'generation_history_list', None) and self.generation_history_list.controls:
                try:
                    self.generation_history_list.controls.pop(0)
                except Exception:
                    pass
            if hasattr(self, 'page') and self.page:
                self.page.update()
            self.show_message("已删除最新生成的音频并移除记录")
        except Exception as ex:
            self.show_message(f"删除失败: {ex}", True)

    def open_audio_location_for(self, path: str):
        try:
            if path and os.path.exists(path):
                subprocess.run(['explorer', '/select,', path], capture_output=True, text=True)
                self.show_message("已打开文件位置")
        except Exception as ex:
            self.show_message(f"打开文件位置失败: {ex}", True)

    def on_single_pick_output_dir_result(self, e: ft.FilePickerResultEvent):
        try:
            p = getattr(e, 'path', '') or ''
            if p:
                setattr(self, 'single_output_dir', p)
                if getattr(self, 'single_output_dir_field', None):
                    self.single_output_dir_field.value = p
            if hasattr(self, 'page') and self.page:
                self.page.update()
        except Exception as ex:
            self.show_message(f"选择输出目录失败: {ex}", True)

    def open_single_output_dir(self, e=None):
        try:
            d = getattr(self, 'single_output_dir', None)
            if not d:
                self.show_message("请先选择输出目录", True)
                return
            if not os.path.isdir(d):
                self.show_message("输出目录不存在", True)
                return
            subprocess.run(['explorer', str(d)], capture_output=True, text=True)
        except Exception as ex:
            self.show_message(f"打开输出目录失败: {ex}", True)

    def on_subtitle_pick_output_dir_result(self, e: ft.FilePickerResultEvent):
        try:
            p = getattr(e, 'path', '') or ''
            if p:
                setattr(self, 'subtitle_output_dir', p)
                if getattr(self, 'subtitle_output_dir_field', None):
                    self.subtitle_output_dir_field.value = p
            if hasattr(self, 'page') and self.page:
                self.page.update()
        except Exception as ex:
            self.show_message(f"选择输出目录失败: {ex}", True)

    def open_subtitle_output_dir(self, e=None):
        try:
            d = getattr(self, 'subtitle_output_dir', None)
            if not d:
                self.show_message("请先选择输出目录", True)
                return
            if not os.path.isdir(d):
                self.show_message("输出目录不存在", True)
                return
            subprocess.run(['explorer', str(d)], capture_output=True, text=True)
        except Exception as ex:
            self.show_message(f"打开输出目录失败: {ex}", True)

    def on_vec_slider_changed(self, idx, value):
        """向量滑条变化时，更新顶部只读数值框显示"""
        try:
            val = float(value)
        except Exception:
            val = 0.0
        if hasattr(self, "vec_value_fields") and 0 <= idx < len(self.vec_value_fields):
            self.vec_value_fields[idx].value = f"{val:.2f}"
        # 立即刷新 UI
        if hasattr(self, "page") and self.page:
            try:
                self.page.update()
            except Exception:
                pass

    def on_emo_method_change(self):
        """根据情感控制方式切换相关参数组的显示"""
        try:
            method = self.emo_method_radio.value if hasattr(self, 'emo_method_radio') else "与音色参考音频相同"
            # 默认全部隐藏
            if hasattr(self, 'emo_text_input'):
                self.emo_text_input.visible = False
            if hasattr(self, 'vec_group'):
                self.vec_group.visible = False
            if hasattr(self, 'emo_random_checkbox'):
                self.emo_random_checkbox.visible = False
            if hasattr(self, 'emo_ref_row_ref') and self.emo_ref_row_ref.current:
                self.emo_ref_row_ref.current.visible = False
                # 同步隐藏内部文本框
                if hasattr(self, 'emo_ref_path_input'):
                    self.emo_ref_path_input.visible = False

            # 切换显示
            if method == "文本控制":
                if hasattr(self, 'emo_text_input'):
                    self.emo_text_input.visible = True
                if hasattr(self, 'emo_random_checkbox'):
                    self.emo_random_checkbox.visible = True
            elif method == "参考音频控制":
                if hasattr(self, 'emo_ref_row_ref') and self.emo_ref_row_ref.current:
                    self.emo_ref_row_ref.current.visible = True
                if hasattr(self, 'emo_ref_path_input'):
                    self.emo_ref_path_input.visible = True
            elif method == "情绪控制":
                if hasattr(self, 'vec_group'):
                    self.vec_group.visible = True

            if hasattr(self, 'page') and self.page:
                self.page.update()
        except Exception as e:
            # 仅记录，不影响生成流程
            if hasattr(self, 'log_manager'):
                self.log_manager.warning(f"切换情感控制方式显示失败: {e}")

    def on_emo_file_picked(self, e):
        """参考音频文件选择回调"""
        try:
            if e and hasattr(e, 'files') and e.files:
                f = e.files[0]
                path = getattr(f, 'path', None) or getattr(f, 'path_or_none', None)
                if path:
                    self.emo_ref_path_input.value = path
                    self.emo_ref_path_input.visible = True
                    if hasattr(self, 'page') and self.page:
                        self.page.update()
        except Exception as ex:
            if hasattr(self, 'log_manager'):
                self.log_manager.warning(f"选择参考音频失败: {ex}")
        
    def create_instance_monitoring_view(self):
        """创建实例监控视图"""
        return ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.MONITOR, color=ft.Colors.ORANGE),
                        title=ft.Text("实例监控", weight=ft.FontWeight.BOLD),
                        subtitle=ft.Text("详细的实例运行信息"),
                    ),
                    ft.Divider(),
                    self.create_detailed_status_table(),
                ], spacing=10),
                padding=20,
            ),
            elevation=2,
        )
    
    def create_subtitle_generation_view(self):
        """创建字幕生成视图（支持角色管理和个性化音色设置）"""
        # 如果正在扫描且没有缓存的音色文件，显示加载中
        if getattr(self, '_is_scanning', False) and not getattr(self, 'voice_files', []):
            return ft.Container(
                content=ft.Column([
                    ft.ProgressRing(),
                    ft.Text("正在扫描音色库...", size=14, color=ft.Colors.GREY)
                ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                alignment=ft.alignment.center,
                expand=True
            )

        # 初始化角色管理相关变量
        self.subtitle_roles = {}  # 存储角色信息 {role_name: voice_path}
        self.subtitle_line_roles = {}  # 存储每行字幕的角色分配 {line_index: role_name}
        self.subtitle_line_emotions = {}  # 存储每行字幕的情感向量 {line_index: [vec1..vec8]}
        self.ai_analysis_result = None  # AI分析结果
        
        # 文章输入区域 - 增加高度，改善输入体验
        self.subtitle_text_input = ft.TextField(
            label="输入文章内容",
            value=getattr(self, 'temp_subtitle_text', ""),
            multiline=True,
            min_lines=24,
            max_lines=48,
            height=435,
            hint_text="请输入需要生成字幕的文章内容...",
            on_change=self.on_subtitle_text_change,
            on_submit=lambda e: self.resegment_current_text(),
            border_color=ft.Colors.BLUE_300,
            focused_border_color=ft.Colors.BLUE_600,
            text_size=14,
        )
        
        
        # 角色管理区域 - 固定合理高度，避免父容器未设置高度时塌缩
        self.role_list = ft.ListView(spacing=6, padding=ft.padding.all(8), auto_scroll=True, height=455)

        # 加载已保存的角色并刷新列表显示
        try:
            saved_roles = self.config_manager.get("subtitle_roles", {})
            if isinstance(saved_roles, dict) and saved_roles:
                self.subtitle_roles.update(saved_roles)
                self.update_role_list()
        except Exception:
            pass

        # 加载已保存的行情感向量（将JSON中的字符串键恢复为整数索引）
        try:
            saved_line_emotions = self.config_manager.get("subtitle_line_emotions", {})
            normalized_emotions = {}
            if isinstance(saved_line_emotions, dict):
                for k, v in saved_line_emotions.items():
                    try:
                        idx = int(k)
                    except Exception:
                        # 跳过无法转换的键
                        continue
                    # 规整为长度至少8的浮点列表
                    if isinstance(v, list):
                        normalized_emotions[idx] = [float(v[j] if j < len(v) else 0.0) for j in range(8)]
            self.subtitle_line_emotions = normalized_emotions
        except Exception:
            self.subtitle_line_emotions = {}
        
        # 字幕编辑区域 - 固定合理高度，和角色列表一致
        self.subtitle_preview = ft.ListView(spacing=6, padding=ft.padding.all(8), auto_scroll=False, height=360)
        
        # 编辑后的字幕列表
        self.edited_subtitles = []
        
        # 进度条和状态
        self.subtitle_progress = ft.ProgressBar(
            value=0,
            color=ft.Colors.BLUE,
            bgcolor=ft.Colors.BLUE_100,
            height=8,
        )
        
        self.subtitle_status = ft.Text(
            "准备就绪",
            size=14,
            color=ft.Colors.GREY_700,
            weight=ft.FontWeight.W_500
        )
        
        # 去除标点符号勾选框
        self.remove_punctuation_checkbox = ft.Checkbox(
            label="生成字幕文件时去除标点符号",
            value=True,
            tooltip="勾选后生成的字幕文件将不包含标点符号"
        )
        
        # 创建响应式布局（上半部分：文章输入 + 基本设置）
        top_section = ft.ResponsiveRow(
            controls=[
                # 文章输入区域（各占一半：6/12）
                ft.Container(
                    content=ft.Card(
                        content=ft.Container(
                            content=ft.Column([
                                ft.Row([
                                    ft.Icon(ft.Icons.ARTICLE, color=ft.Colors.BLUE, size=20),
                                    ft.Text("文章输入", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE),
                                ], spacing=8),
                                ft.Divider(height=1),
                                self.subtitle_text_input,
                                ft.Row([
                                    ft.Container(expand=True),
                                    ft.ElevatedButton(
                                        "清空内容",
                                        icon=ft.Icons.CLEAR,
                                        on_click=self.clear_subtitle_content,
                                        style=ft.ButtonStyle(color=ft.Colors.WHITE, bgcolor=ft.Colors.GREY_600),
                                        height=32,
                                    ),
                                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                                ], spacing=8),
                                padding=10,
                            ),
                            elevation=2,
                    ),
                    col={"xs": 12, "md": 6, "lg": 6},
                ),

                # 音色设置和生成控制区域（各占一半：6/12）
                ft.Container(
                    content=ft.Card(
                        content=ft.Container(
                            content=ft.Column([
                                ft.Row([
                                    ft.Icon(ft.Icons.SETTINGS_VOICE, color=ft.Colors.ORANGE, size=20),
                                    ft.Text("音色设置", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE),
                                ], spacing=6),
                                ft.Divider(height=1),

                                # 默认音色选择
                                ft.Row([
                                    ft.Text("默认音色:", size=13, weight=ft.FontWeight.W_500),
                                    ft.Container(content=self.create_voice_selector_row(self.create_subtitle_voice_dropdown(), "subtitle_voice_category_dropdown"), expand=True),
                                ], spacing=6),
                                ft.Row([
                                    (lambda: (
                                        setattr(self, 'subtitle_output_dir_field', ft.TextField(label="输出目录", read_only=True, width=420)),
                                        self.subtitle_output_dir_field
                                    ))()[1],
                                    (lambda: (
                                        setattr(self, 'subtitle_dir_picker', getattr(self, 'subtitle_dir_picker', None) or ft.FilePicker(on_result=self.on_subtitle_pick_output_dir_result)),
                                        (self.page and self.subtitle_dir_picker not in self.page.overlay and self.page.overlay.append(self.subtitle_dir_picker)),
                                        self.page and self.page.update(),
                                        ft.ElevatedButton("选择输出目录", icon=ft.Icons.FOLDER_OPEN, on_click=lambda e: self.subtitle_dir_picker.get_directory_path())
                                    ))()[3],
                                    ft.ElevatedButton("打开输出目录", icon=ft.Icons.FOLDER_OPEN, on_click=self.open_subtitle_output_dir),
                                ], spacing=6, wrap=True),

                                # 语速控制（主界面可见）
                                ft.Row([
                                    ft.Text("语速:", size=12),
                                    (lambda _cur=float(self.config_manager.get("speaking_speed", 1.0)):
                                        (setattr(self, "_speed_text_main", ft.Text(f"{_cur:.1f}x", size=12)),
                                         ft.Slider(
                                            min=0.1,
                                            max=2.0,
                                            divisions=19,
                                            value=_cur,
                                            label="",
                                            on_change=lambda e: (
                                                setattr(self, "runtime_speaking_speed", e.control.value),
                                                setattr(self._speed_text_main, "value", f"{float(e.control.value):.1f}x"),
                                                self.page.update()
                                            ),
                                            expand=True,
                                         ))
                                    )()[1],
                                    (lambda: self._speed_text_main)()
                                ], spacing=8),

                                # 音量控制（字幕视图）
                                ft.Row([
                                    ft.Text("音量:", size=12),
                                    (lambda _v=int(self.config_manager.get("volume_percent", 100)):
                                        (setattr(self, "_volume_text_subtitle", ft.Text(f"{_v}%", size=12)),
                                         ft.Slider(
                                            min=50,
                                            max=200,
                                            divisions=150,
                                            value=float(_v),
                                            label="",
                                            on_change=lambda e: (
                                                setattr(self, "runtime_volume_percent", int(e.control.value)),
                                                setattr(self._volume_text_subtitle, "value", f"{int(e.control.value)}%"),
                                                self.page.update()
                                            ),
                                            expand=True,
                                         ))
                                    )()[1],
                                    (lambda: self._volume_text_subtitle)()
                                ], spacing=8),

                                # 生成选项
                                self.remove_punctuation_checkbox,

                                ft.Container(height=8),

                                # 所有按钮横向平铺排列（调小尺寸）
                                ft.Row([
                                    (lambda: (
                                        setattr(self, 'subtitle_sample_button', ft.ElevatedButton(
                                            "试听",
                                            icon=ft.Icons.PLAY_CIRCLE,
                                            on_click=self.toggle_subtitle_sample_playback,
                                            style=ft.ButtonStyle(color=ft.Colors.WHITE, bgcolor=ft.Colors.GREEN_600),
                                            height=32,
                                            expand=True,
                                        )),
                                        self.subtitle_sample_button
                                    ))()[1],
                                    ft.ElevatedButton(
                                        "刷新",
                                        icon=ft.Icons.REFRESH,
                                        on_click=self.refresh_voices,
                                        style=ft.ButtonStyle(color=ft.Colors.WHITE, bgcolor=ft.Colors.BLUE_600),
                                        height=32,
                                        expand=True,
                                    ),
                                    ft.ElevatedButton(
                                        "开始生成",
                                        icon=ft.Icons.PLAY_ARROW,
                                        on_click=self.start_subtitle_generation,
                                        style=ft.ButtonStyle(color=ft.Colors.WHITE, bgcolor=ft.Colors.GREEN_600),
                                        height=32,
                                        expand=True,
                                    ),
                                ], spacing=6),

                                ft.Row([
                                    ft.ElevatedButton(
                                        "停止生成",
                                        icon=ft.Icons.STOP,
                                        on_click=self.stop_subtitle_generation,
                                        style=ft.ButtonStyle(color=ft.Colors.WHITE, bgcolor=ft.Colors.RED_600),
                                        height=32,
                                        expand=True,
                                    ),
                                    ft.ElevatedButton(
                                        "打开文件夹",
                                        icon=ft.Icons.FOLDER_OPEN,
                                        on_click=self.open_subtitle_folder,
                                        style=ft.ButtonStyle(color=ft.Colors.WHITE, bgcolor=ft.Colors.BLUE_600),
                                        height=32,
                                        expand=True,
                                    ),
                                    ft.ElevatedButton(
                                        "播放语音",
                                        icon=ft.Icons.VOLUME_UP,
                                        on_click=self.play_subtitle_audio,
                                        style=ft.ButtonStyle(color=ft.Colors.WHITE, bgcolor=ft.Colors.PURPLE_600),
                                        height=32,
                                        expand=True,
                                    ),
                                ], spacing=6),

                                ft.Container(height=8),

                                # 状态显示
                                self.subtitle_status,
                                ft.Container(height=3),
                                self.subtitle_progress,
                            ], spacing=8),
                            padding=10,
                        ),
                        elevation=2,
                    ),
                    col={"xs": 12, "md": 6, "lg": 6},
                ),
            ],
            spacing={"xs": 12, "md": 15},
            run_spacing={"xs": 12, "md": 15},
        )
        
        # 下半部分：角色管理和字幕编辑（优化空间利用）
        bottom_section = ft.ResponsiveRow(
            controls=[
                # 角色管理区域（紧凑布局）
                ft.Container(
                    content=ft.Card(
                        content=ft.Container(
                            content=ft.Column([
                                ft.Row([
                                    ft.Icon(ft.Icons.PEOPLE, color=ft.Colors.PURPLE, size=20),
                                    ft.Text("角色管理", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.PURPLE),
                                ], spacing=8),
                                ft.Divider(height=1),
                                # AI分析按钮（如果启用AI）
                                self.create_ai_analysis_section(),
                                # 角色列表容器（扩展以占用更多空间）
                                ft.Container(
                                    content=self.role_list,
                                    border=ft.border.all(1, ft.Colors.GREY_700 if self.is_dark_theme() else ft.Colors.GREY_300),
                                    border_radius=8,
                                    expand=True,
                                ),
                                # 角色操作按钮（调小尺寸）
                                ft.Row([
                                    ft.ElevatedButton(
                                        "添加角色",
                                        icon=ft.Icons.ADD_CIRCLE,
                                        on_click=self.add_role,
                                        style=ft.ButtonStyle(color=ft.Colors.WHITE, bgcolor=ft.Colors.GREEN_600),
                                        height=32,
                                        expand=True,
                                    ),
                                    ft.ElevatedButton(
                                        "清空角色",
                                        icon=ft.Icons.CLEAR_ALL,
                                        on_click=self.clear_roles,
                                        style=ft.ButtonStyle(color=ft.Colors.WHITE, bgcolor=ft.Colors.ORANGE_600),
                                        height=32,
                                        expand=True,
                                    ),
                                ], spacing=8),
                            ], spacing=8),
                            padding=10,
                        ),
                        elevation=2,
                    ),
                    col={"xs": 12, "md": 4, "lg": 4},
                ),

                # 字幕编辑区域（紧凑布局）
                ft.Container(
                    content=ft.Card(
                        content=ft.Container(
                            content=ft.Column([
                                ft.Row([
                                    ft.Icon(ft.Icons.EDIT_NOTE, color=ft.Colors.GREEN, size=20),
                                    ft.Text("字幕编辑", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN),
                                ], spacing=8),
                                ft.Divider(height=1),
                                ft.Row([
                                    ft.Icon(ft.Icons.TUNE, color=ft.Colors.BLUE_400, size=18),
                                    ft.Text("每行字数:", size=12),
                                    (lambda _cur=float(self.subtitle_cpl_chinese): (
                                        setattr(self, "subtitle_cpl_slider", ft.Slider(
                                            min=8,
                                            max=40,
                                            divisions=32,
                                            value=_cur,
                                            label="{value}",
                                            on_change=self.on_subtitle_cpl_change,
                                            expand=True,
                                        )),
                                        self.subtitle_cpl_slider
                                    ))()[1],
                                    (lambda _txt=ft.Text(f"{int(self.subtitle_cpl_chinese)}字/行", size=12): (
                                        setattr(self, "subtitle_cpl_value_text", _txt),
                                        self.subtitle_cpl_value_text
                                    ))()[1],
                                    (lambda _cb=ft.Checkbox(label="引号粘合标点", value=self.quote_glue_enabled, on_change=self.on_quote_glue_change): (
                                        setattr(self, "quote_glue_checkbox", _cb),
                                        self.quote_glue_checkbox
                                    ))()[1],
                                ], spacing=8),
                                # 批量操作按钮（调小尺寸）
                                ft.Row([
                                    ft.ElevatedButton(
                                        "批量设置角色",
                                        icon=ft.Icons.BATCH_PREDICTION,
                                        on_click=self.batch_assign_role,
                                        style=ft.ButtonStyle(color=ft.Colors.WHITE, bgcolor=ft.Colors.BLUE_600),
                                        height=32,
                                        expand=True,
                                    ),
                                    ft.ElevatedButton(
                                        "重置角色分配",
                                        icon=ft.Icons.REFRESH,
                                        on_click=self.clear_all_assignments,
                                        style=ft.ButtonStyle(color=ft.Colors.WHITE, bgcolor=ft.Colors.GREY_600),
                                        height=32,
                                        expand=True,
                                    ),
                                ], spacing=8),

                                ft.Container(height=6),

                                # 字幕列表容器（扩展以占用更多空间）
                                ft.Container(
                                    content=self.subtitle_preview,
                                    border=ft.border.all(1, ft.Colors.GREY_700 if self.is_dark_theme() else ft.Colors.GREY_300),
                                    border_radius=8,
                                    expand=True,
                                ),
                                ft.Row([
                                    (lambda: (
                                        setattr(self, 'split_mode_dropdown', ft.Dropdown(
                                            label="分割模式",
                                            value="智能分句",
                                            options=[
                                                ft.dropdown.Option("智能分句", "智能分句"),
                                                ft.dropdown.Option("按标点分割", "按标点分割"),
                                                ft.dropdown.Option("不分割", "不分割"),
                                            ],
                                            width=160,
                                            on_change=self.on_split_mode_change,
                                        )),
                                        self.split_mode_dropdown
                                    ))()[1],
                                    (lambda: (
                                        setattr(self, 'punctuation_set_text', ft.TextField(
                                            label="标点集",
                                            hint_text="例如：。！？；…，、： . ! ? , :",
                                            value="。 ！ ？ ； … ， 、 ： . ! ? , :",
                                            width=380,
                                            on_change=self.on_punctuation_set_change,
                                        )),
                                        self.punctuation_set_text
                                    ))()[1],
                                    ft.ElevatedButton(
                                        "重新分割",
                                        icon=ft.Icons.SPLITSCREEN,
                                        on_click=self.resegment_current_text,
                                        style=ft.ButtonStyle(color=ft.Colors.WHITE, bgcolor=ft.Colors.BLUE_600),
                                        height=32,
                                    ),
                                ], spacing=8),
                            ], spacing=10),
                            padding=15,
                        ),
                        elevation=2,
                    ),
                    col={"xs": 12, "md": 8, "lg": 8},
                ),
            ],
            spacing={"xs": 10, "md": 12},
            run_spacing={"xs": 10, "md": 12},
        )
        
        # 顶部和底部改为响应式，并允许整体滚动以适配不同窗口大小
        return ft.Container(
            content=ft.Column([
                top_section,
                bottom_section,
            ], spacing=10, scroll=ft.ScrollMode.AUTO),
            padding=ft.padding.all(12),
            expand=True,
        )
    
    def create_ai_analysis_section(self):
        """创建AI分析部分"""
        # 检查是否启用AI
        ai_enabled = self.config_manager.get("ai_enabled", False)
        
        if not ai_enabled:
            return ft.Container(
                content=ft.Text(
                    "AI角色识别未启用，请在设置中配置AI参数",
                    size=12,
                    color=(ft.Colors.GREY_400 if self.is_dark_theme() else ft.Colors.GREY_500),
                    italic=True
                ),
                padding=ft.padding.all(10),
                bgcolor=(ft.Colors.with_opacity(0.06, ft.Colors.WHITE) if self.is_dark_theme() else ft.Colors.GREY_100),
                border_radius=5
            )
        
        return ft.Column([
            ft.Row([
                ft.ElevatedButton(
                    "AI智能分析",
                    icon=ft.Icons.AUTO_AWESOME,
                    on_click=self.ai_analyze_roles,
                    style=ft.ButtonStyle(
                        color=ft.Colors.WHITE,
                        bgcolor=ft.Colors.PURPLE_400
                    )
                ),
                ft.ElevatedButton(
                    "应用AI建议",
                    icon=ft.Icons.SMART_TOY,
                    on_click=self.apply_ai_suggestions,
                    style=ft.ButtonStyle(
                        color=ft.Colors.WHITE,
                        bgcolor=ft.Colors.INDIGO_400
                    )
                ),
            ], spacing=10),
            ft.Container(height=5),
        ], spacing=5)
    
    def add_role(self, e):
        """添加新角色"""
        def close_dialog(e):
            dialog.open = False
            if hasattr(self, 'page') and self.page:
                self.page.update()
        
        def save_role(e):
            role_name = role_name_field.value.strip()
            selected_voice = voice_dropdown.value
            
            if not role_name:
                self.show_message("请输入角色名称", True)
                return
            
            if not selected_voice:
                self.show_message("请选择音色", True)
                return
            
            # 添加角色到列表
            self.subtitle_roles[role_name] = selected_voice
            self.update_role_list()
            # 同时更新字幕预览中的角色下拉框
            self.update_subtitle_preview_simple()
            # 持久化保存角色列表
            if hasattr(self, 'config_manager'):
                self.config_manager.set("subtitle_roles", self.subtitle_roles)
            
            dialog.open = False
            if hasattr(self, 'page') and self.page:
                self.page.update()
            
            self.show_message(f"角色 '{role_name}' 添加成功")
        
        # 创建角色名称输入框
        role_name_field = ft.TextField(
            label="角色名称",
            hint_text="例如：旁白、男主、女主",
            width=200
        )
        
        # 创建音色选择下拉框
        voice_dropdown = ft.Dropdown(
            label="选择音色",
            width=250,
        )
        
        # 使用带分类筛选的选择器
        voice_selector = self.create_voice_selector_row(voice_dropdown, "add_role_category_dropdown")
        
        dialog = ft.AlertDialog(
            modal=False,
            title=ft.Text("添加角色"),
            content=ft.Container(
                content=ft.Column([
                    role_name_field,
                    ft.Container(height=10),
                    voice_selector,
                ], spacing=10),
                width=400, # 稍微加宽以容纳分类下拉框
                height=200
            ),
            actions=[
                ft.TextButton("取消", on_click=close_dialog),
                ft.ElevatedButton("保存", on_click=save_role),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        if hasattr(self, 'page') and self.page:
            self.page.overlay.append(dialog)
            dialog.open = True
            self.page.update()
    
    def ai_analyze_roles(self, e):
        """AI智能分析角色"""
        if not self.subtitle_text_input.value.strip():
            self.show_message("请先输入文章内容", True)
            return
        
        # 检查AI配置
        ai_enabled = self.config_manager.get("ai_enabled", False)
        if not ai_enabled:
            self.show_message("AI功能未启用，请在设置中配置", True)
            return
        
        api_key = self.config_manager.get("ai_api_key", "")
        mode = self.config_manager.get("ai_api_url_mode", "default")
        base_url = (
            self.config_manager.get("ai_custom_base_url", "") if mode == "custom" else
            self.config_manager.get("ai_base_url", "")
        )
        model = self.config_manager.get("ai_model", "")
        
        # 允许本地AI不填写Key
        bu = (base_url or "").lower()
        is_local = any(
            bu.startswith(p) for p in [
                "http://127.0.0.1",
                "https://127.0.0.1",
                "http://localhost",
                "https://localhost",
                "http://0.0.0.0",
                "https://0.0.0.0",
                "http://192.168.",
                "https://192.168.",
                "http://10.",
                "https://10."
            ]
        )

        if not base_url or not model:
            self.show_message("AI配置不完整：缺少 Base URL 或 模型名称", True)
            return
        if not api_key and not is_local:
            self.show_message("API Key 为空：云端服务需要填写 Key，本地服务可留空", True)
            return
        
        # 显示分析进度
        self.show_message("AI正在分析角色...")
        
        import threading
        
        def analyze_in_background():
            try:
                # 准备文本内容
                text_content = self.subtitle_text_input.value.strip()
                
                # 获取用户选中的音色列表
                available_voice_files = []
                if hasattr(self, 'voice_library_selected') and self.voice_library_selected:
                    selected_paths = list(self.voice_library_selected)
                    # 数量验证
                    if len(selected_paths) > 20:
                        if hasattr(self, 'page') and self.page:
                             self.page.run_task(lambda: self.show_message("AI分析最多支持选择20个音色，请在音色库中减少选择", True))
                        return
                    
                    # 提取文件名
                    for p in selected_paths:
                        try:
                            available_voice_files.append(Path(p).name)
                        except:
                            pass
                else:
                     # 此时未选中任何音色
                     if hasattr(self, 'page') and self.page:
                         self.page.run_task(lambda: self.show_message("请先在音色库中选择要用于AI分析的音色（最多20个）", True))
                     return
                
                voice_info = f"当前可用音色：{', '.join(available_voice_files)}"
                try:
                    _max_tokens_cfg = int(self.config_manager.get("ai_max_tokens", 2000))
                except Exception:
                    _max_tokens_cfg = 2000
                if self.calculate_character_length(text_content) > max(1500, _max_tokens_cfg * 2):
                    self._ai_analyze_roles_chunked(api_key, base_url, model, available_voice_files, text_content)
                    return
                
                # 构建智能字幕分割和角色分配的AI提示词
                prompt = f"""将提供的文章：【 {text_content}】
                 严格分割成一个完整JSON对象，不要包含任何解释、说明、前后文字或Markdown围栏。的字幕脚本。
                
                角色分配：

对话 (dialogue)：所有引号（“...”）内的内容，分配给说话的角色。

旁白 (narration)：所有引号外的内容，包括叙述、动作、环境、心理活动（如“心想：”）和引导词（如“他说：”），必须分配给“旁白”角色。

严格分割（关键）：

一句话中同时包含叙述和对话时，必须拆分为旁白和对话两个片段。

示例1（旁白在后）：

原文："检测到未知引力场。"零的电子音无波澜。

分割：[零: "检测到未知引力场。"] [旁白: "零的电子音无波澜。"]

示例2（旁白在前）：

原文：阿夏蹲在引擎舱：左舷引擎过载！

分割：[旁白: "阿夏蹲在引擎舱："] [阿夏: "左舷引擎过载！"]

格式要求：

内容完整：保留全部原文内容，不可删减，并且按照原文顺序进行分割，顺序不能打乱，内容不可缺少。

                字数限制：每个segments的"text"字段长度需在 [{int(self.config_manager.get("ai_seg_min_cn", 5))}, {int(self.config_manager.get("ai_seg_max_cn", 25))}] 个汉字范围内，长句按语义智能切分。

                情感标注：每个分割段需要提供一个中文情感标签（"emotion"）以及对应的8维情感向量（"emotion_vector"，范围0.1-1）。
                向量维度顺序（必须遵循）：[喜, 怒, 哀, 惧, 厌恶, 低落, 惊喜, 平静]，最多使用一个情感标签，其他维度为0，注意数值不要太夸张，尤其是旁白，情感值不要超过0.5。
                当一个分割段被进一步拆分为多个子段时，所有子段必须复制原分割段的 emotion 与 emotion_vector。

                语速标注：为每个分割段提供语速（"speaking_speed"，范围0.1-2.0；1.0为正常语速），请结合角色、情境与停顿给出自然的语速建议。

                音色分配：从 {', '.join(available_voice_files)} 列表中为roles分配 suggested_voice。
                {{
                 "roles": [ 
                   {{"name": "旁白", "description": "叙述者，负责环境描述和叙述", "suggested_voice": "播音女.wav"}},
                   {{"name": "角色名", "description": "角色描述", "suggested_voice": "音色文件名"}}
                 ], 
                 "segments": [ 
                   {{"text": "分割后的文本片段", "role": "角色名", "type": "dialogue/narration", "emotion": "情感标签", "emotion_vector": [0,0,0,0,0,0,0,0], "speaking_speed": 1.0}} 
                 ], 
                 "assignments": [ 
                   {{"line": 行号, "role": "角色名", "text": "对应文本内容", "emotion": "情感标签", "emotion_vector": [0,0,0,0,0,0,0,0], "speaking_speed": 1.0}} 
                 ] 
                }}

                """
                print(prompt)
                # 调用AI API
                headers = {"Content-Type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                
                # 根据 Base URL 判断是否为 Ollama
                base = base_url.rstrip('/')
                import re as _re
                is_ollama = (
                    ":11434" in base or
                    base.endswith('/api') or base.endswith('/api/') or
                    '/api/generate' in base or '/api/chat' in base
                )

                if is_ollama:
                    # 优先使用 /api/generate（非流式），将消息合并为 prompt
                    max_tokens = int(self.config_manager.get("ai_max_tokens", 2000))
                    data = {
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": float(self.config_manager.get("ai_temperature", 0.7)),
                            "num_predict": max_tokens
                        }
                    }

                    if base.endswith('/api/generate') or base.endswith('/api/chat'):
                        api_url = base
                    elif base.endswith('/api') or base.endswith('/api/'):
                        api_url = f"{base.rstrip('/')}/generate"
                    else:
                        api_url = f"{base}/api/generate"
                else:
                    # OpenAI 兼容接口
                    data = {
                        "model": model,
                        "messages": [
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": float(self.config_manager.get("ai_temperature", 0.7)),
                        "max_tokens": int(self.config_manager.get("ai_max_tokens", 2000))
                    }
                    # 兼容 base_url 是否已包含版本段 /vX，避免重复，并支持 v4 等
                    if _re.search(r"/v\d+$", base):
                        api_url = f"{base}/chat/completions"
                    else:
                        api_url = f"{base}/v1/chat/completions"
                
                # 添加调试日志
                self.log_message(f"AI API调用 - URL: {api_url}")
                self.log_message(f"AI API调用 - Model: {model}")
                _headers_log = {k: ('***' if k.lower() == 'authorization' else headers.get(k)) for k in headers}
                self.log_message(f"AI API调用 - Headers: {_headers_log}")
                response = requests.post(api_url, headers=headers, json=data, timeout=160)
                self.log_message(f"AI API响应状态码: {response.status_code}")
                if response.status_code != 200:
                    self.log_message(f"AI API错误响应内容: {response.text}")
                response.raise_for_status()
                ai_response = ''
                try:
                    result = response.json()
                except Exception:
                    result = {}
                    ai_response = response.text or ''
                if not ai_response:
                    if 'choices' in result and result.get('choices'):
                        ai_response = result['choices'][0]['message']['content']
                    else:
                        ai_response = result.get('response') or (result.get('message', {}).get('content', ''))
                
                # 解析AI返回的JSON
                import json
                import re
                
                def extract_roles_from_text(text):
                    """从AI输出文本中提取角色信息，即使JSON格式有问题"""
                    roles = []
                    assignments = []
                    
                    # 尝试从文本中提取角色信息
                    role_patterns = [
                        r'"name":\s*"([^"]+)"',
                        r'角色[：:]\s*([^\n,，]+)',
                        r'([女男]声|旁白|[^，,\n]+(?:先生|女士|小姐))',
                    ]
                    
                    found_roles = set()
                    for pattern in role_patterns:
                        matches = re.findall(pattern, text, re.IGNORECASE)
                        for match in matches:
                            role_name = match.strip()
                    if role_name:
                        found_roles.add(role_name)
                    
                    # 创建角色列表
                    for role_name in found_roles:
                        gender = "neutral"
                        if "女" in role_name or "小姐" in role_name or "女士" in role_name:
                            gender = "female"
                        elif "男" in role_name or "先生" in role_name:
                            gender = "male"
                        
                        roles.append({
                            "name": role_name,
                            "description": f"角色：{role_name}",
                            "gender": gender
                        })
                    
                    # 如果没有找到角色，添加默认角色
                    if not roles:
                        roles.append({"name": "旁白", "description": "叙述者", "gender": "neutral"})
                    
                    # 为每行文本分配角色（简单分配）
                    for i, line in enumerate(self.subtitle_segments):
                        # 简单的角色分配逻辑
                        role_name = "旁白"  # 默认角色
                        if len(roles) > 1:
                            # 如果有多个角色，尝试智能分配
                            if "：" in line or ":" in line:
                                # 对话格式，分配给非旁白角色
                                non_narrator_roles = [r for r in roles if r["name"] != "旁白"]
                                if non_narrator_roles:
                                    role_name = non_narrator_roles[0]["name"]
                        
                        assignments.append({
                            "line": i,
                            "role": role_name,
                            "text": line
                        })
                    
                    return roles, assignments
                
                def parse_ai_response(response_text):
                    """增强的AI响应解析函数，支持容错和截断处理"""
                    # 清理响应文本
                    response_text = response_text.strip()
                    
                    # 方法1: 尝试直接解析整个响应为JSON
                    try:
                        ai_analysis = json.loads(response_text)
                        if "roles" in ai_analysis and ai_analysis["roles"]:
                            return ai_analysis
                    except:
                        pass
                    
                    # 方法2: 查找JSON代码块
                    json_patterns = [
                        r'```json\s*(\{.*?\})\s*```',  # ```json {...} ```
                        r'```\s*(\{.*?\})\s*```',     # ``` {...} ```
                        r'(\{[^{}]*"roles"[^{}]*\})', # 包含roles的JSON对象
                    ]
                    
                    for pattern in json_patterns:
                        matches = re.findall(pattern, response_text, re.DOTALL)
                        for match in matches:
                            try:
                                ai_analysis = json.loads(match)
                                if "roles" in ai_analysis and ai_analysis["roles"]:
                                    return ai_analysis
                            except:
                                continue
                    
                    # 方法3: 尝试修复截断的JSON
                    def try_fix_truncated_json(text):
                        """尝试修复截断的JSON"""
                        json_start = text.find('{')
                        if json_start == -1:
                            return None
                            
                        # 找到最后一个完整的对象
                        brace_count = 0
                        last_complete_pos = json_start
                        
                        for i, char in enumerate(text[json_start:], json_start):
                            if char == '{':
                                brace_count += 1
                            elif char == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    last_complete_pos = i + 1
                                    break
                        
                        if last_complete_pos > json_start:
                            try:
                                json_str = text[json_start:last_complete_pos]
                                return json.loads(json_str)
                            except:
                                pass
                        
                        # 如果找不到完整的JSON，尝试修复截断
                        json_part = text[json_start:]
                        
                        # 尝试补全常见的截断情况
                        fix_attempts = [
                            json_part + '}',  # 缺少结束括号
                            json_part + ']}',  # 缺少数组和对象结束
                            json_part + '"}]}',  # 缺少字符串和结构结束
                            json_part.rstrip(',') + '}',  # 移除末尾逗号并补全
                        ]
                        
                        for attempt in fix_attempts:
                            try:
                                result = json.loads(attempt)
                                if "roles" in result:
                                    return result
                            except:
                                continue
                        
                        return None
                    
                    # 尝试修复截断的JSON
                    fixed_json = try_fix_truncated_json(response_text)
                    if fixed_json:
                        return fixed_json
                    
                    # 方法3: 查找最大的JSON对象
                    json_start = response_text.find('{')
                    if json_start != -1:
                        brace_count = 0
                        json_end = json_start
                        for i, char in enumerate(response_text[json_start:], json_start):
                            if char == '{':
                                brace_count += 1
                            elif char == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    json_end = i + 1
                                    break
                        
                        if json_end > json_start:
                            try:
                                json_str = response_text[json_start:json_end]
                                ai_analysis = json.loads(json_str)
                                if "roles" in ai_analysis and ai_analysis["roles"]:
                                    return ai_analysis
                            except:
                                pass
                    
                    # 如果所有JSON解析都失败，返回None
                    return None
                
                try:
                    # 记录AI响应用于调试
                    self.log_message(f"AI响应长度: {len(ai_response)} 字符")
                    self.log_message(f"AI响应: {ai_response}")
                    
                    ai_analysis = parse_ai_response(ai_response)
                    
                    if ai_analysis is None:
                        raise ValueError("无法解析AI响应为有效JSON")
                    
                    # 验证解析结果的完整性
                    if "roles" in ai_analysis:
                        self.log_message(f"成功解析到 {len(ai_analysis['roles'])} 个角色")
                    if "segments" in ai_analysis:
                        self.log_message(f"成功解析到 {len(ai_analysis['segments'])} 个智能分割段")
                    if "assignments" in ai_analysis:
                        self.log_message(f"成功解析到 {len(ai_analysis['assignments'])} 个分配")
                        
                except Exception as e:
                    self.log_message(f"JSON解析失败，尝试文本解析: {e}")
                    self.log_message(f"AI响应内容: {ai_response[:1000]}...")  # 记录前1000字符用于调试
                    
                    # 如果JSON解析失败，尝试从文本中提取角色信息
                    roles, assignments = extract_roles_from_text(ai_response)
                    ai_analysis = {
                        "roles": roles,
                        "assignments": assignments
                    }
                    self.log_message(f"文本解析结果: {len(roles)} 个角色, {len(assignments)} 个分配")
                
                # 保留完整的AI分析结果，同时创建兼容的内部格式
                analysis_result = ai_analysis.copy()  # 保留所有AI分析数据
                
                # 确保有基本的roles和assignments结构
                if "roles" not in analysis_result:
                    analysis_result["roles"] = []
                if "assignments" not in analysis_result:
                    analysis_result["assignments"] = []
                
                # 处理智能字幕分割的segments
                if "segments" in analysis_result and analysis_result["segments"]:
                    self.log_message(f"AI返回了 {len(analysis_result['segments'])} 个智能分割的字幕段")
                    
                    # 如果有segments，用它们替换原有的字幕段
                    new_segments = []
                    new_assignments = []
                    new_line_emotions = {}
                    
                    for i, segment in enumerate(analysis_result["segments"]):
                        text = segment.get("text", "").strip()
                        role = segment.get("role", "旁白")
                        segment_type = segment.get("type", "narration")
                        emotion_label = segment.get("emotion", "")
                        emotion_vector = segment.get("emotion_vector")
                        # 校验/默认情感向量
                        if not (isinstance(emotion_vector, list) and len(emotion_vector) == 8):
                            emotion_vector = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
                        try:
                            emotion_vector = self._normalize_vec_for_role(emotion_vector, role, emotion_label)
                        except Exception:
                            pass
                        try:
                            # 仅当AI明确标注为旁白/叙述时才回退为"旁白"
                            if segment_type == "narration":
                                role = "旁白"
                                segment_type = "narration"
                        except Exception:
                            pass
                        
                        if text:  # 只添加非空文本
                            # 对每个AI分割的段落进行20字二次分割
                            sub_segments = self.split_text_by_20_chars(text, role)
                            
                            for sub_text in sub_segments:
                                if sub_text.strip():  # 确保不添加空文本
                                    line_index = len(new_segments)
                                    new_segments.append(sub_text.strip())
                                    new_assignments.append({
                                        "line": line_index,
                                        "role": role,
                                        "text": sub_text.strip(),
                                        "type": segment_type,
                                        "emotion": emotion_label,
                                        "emotion_vector": emotion_vector,
                                        "speaking_speed": float(segment.get("speaking_speed", 1.0) or 1.0)
                                    })
                                    # 保存行情感向量
                                    if bool(self.config_manager.get("ai_adjust_emotion", True)):
                                        new_line_emotions[line_index] = emotion_vector
                    
                    if new_segments:
                        # 更新字幕段
                        self.subtitle_segments = new_segments
                        analysis_result["assignments"] = new_assignments
                        # 写入行情感向量映射
                        analysis_result["line_emotions"] = new_line_emotions
                        try:
                            analysis_result["line_speeds"] = {a["line"]: float(a.get("speaking_speed", 1.0) or 1.0) for a in new_assignments if isinstance(a, dict)}
                        except Exception:
                            analysis_result["line_speeds"] = {}
                        self.log_message(f"已应用AI智能分割+20字二次分割，共 {len(new_segments)} 个字幕段")
                        
                        # 更新UI中的字幕显示
                        if hasattr(self, 'page') and self.page:
                            async def _update_subtitles():
                                self.update_subtitle_preview_simple()
                            self.page.run_task(_update_subtitles)
                
                # 为角色添加建议音色
                for role in analysis_result["roles"]:
                    if "suggested_voice" not in role:
                        role_name = role.get("name", "")
                        role_type = role.get("type", "other")
                        role["suggested_voice"] = self.suggest_voice_for_role(role_name, role_type)
                
                # 创建兼容的assignments字典格式（用于现有的apply_suggestions功能）
                assignments_dict = {}
                for assignment in analysis_result.get("assignments", []):
                    if isinstance(assignment, dict):
                        line_index = assignment.get("line", 0)
                        role_name = assignment.get("role", "旁白")
                        assignments_dict[line_index] = role_name
                
                # 添加兼容字段
                analysis_result["assignments_dict"] = assignments_dict
                
                # 更新AI分析结果
                self.ai_analysis_result = analysis_result
                try:
                    self._log_ai_segments(self.ai_analysis_result)
                except Exception:
                    pass
                
                # 在主线程中更新UI并自动应用建议
                if hasattr(self, 'page') and self.page:
                    async def _update_ui():
                        try:
                            self.update_ai_analysis_ui()
                            if getattr(self, 'page', None):
                                self.page.update()
                        except AssertionError:
                            pass
                    self.page.run_task(_update_ui)
                
            except Exception as e:
                error_msg = str(e)
                self.log_message(f"AI分析失败: {error_msg}")
                if hasattr(self, 'page') and self.page:
                    async def _show_err():
                        self.show_message(f"AI分析失败: {error_msg}", True)
                    self.page.run_task(_show_err)
        
        # 在后台线程中执行分析
        threading.Thread(target=analyze_in_background, daemon=True).start()
        
    def _ai_analyze_roles_chunked(self, api_key, base_url, model, available_voice_files, text_content):
        try:
            if not hasattr(self, 'subtitle_segments') or not self.subtitle_segments:
                seg_mode = (self.split_mode_dropdown.value if hasattr(self, 'split_mode_dropdown') and self.split_mode_dropdown else "智能分句")
                if seg_mode == "按标点分割":
                    segments_all = self.split_text_by_punctuation(text_content)
                elif seg_mode == "不分割":
                    segments_all = [text_content]
                else:
                    segments_all = self.split_text_intelligently(text_content)
                self.subtitle_segments = segments_all
            else:
                segments_all = list(self.subtitle_segments)
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            base = (base_url or "").rstrip('/')
            import re as _re
            is_ollama = (":11434" in base or base.endswith('/api') or base.endswith('/api/') or '/api/generate' in base or '/api/chat' in base)
            def _api_url():
                if is_ollama:
                    if base.endswith('/api/generate') or base.endswith('/api/chat'):
                        return base
                    elif base.endswith('/api') or base.endswith('/api/'):
                        return f"{base.rstrip('/')}/generate"
                    else:
                        return f"{base}/api/generate"
                else:
                    return f"{base}/chat/completions" if _re.search(r"/v\d+$", base) else f"{base}/v1/chat/completions"
            try:
                max_tokens = int(self.config_manager.get("ai_max_tokens", 2000))
            except Exception:
                max_tokens = 2000
            def _clen(s):
                return self.calculate_character_length(s)
            blocks = []
            cur = []
            cur_chars = 0
            budget = max(1200, min(2800, max_tokens * 1))
            for idx, seg in enumerate(segments_all):
                l = _clen(seg)
                if cur_chars + l > budget and cur:
                    blocks.append(cur)
                    cur = []
                    cur_chars = 0
                cur.append({"line": idx, "text": seg})
                cur_chars += l
            if cur:
                blocks.append(cur)
            import json
            roles_acc = []
            roles_seen = set()
            assignments_acc = []
            line_emotions_acc = {}
            line_speeds_acc = {}
            new_segments_acc = []
            segments_output_acc = []
            for bi, block in enumerate(blocks):
                prev_roles = [{"name": r.get("name", ""), "suggested_voice": r.get("suggested_voice", "")} for r in roles_acc]
                prompt_obj = {
                    "task": "对输入分段进行合理再分割（旁白与对话分离、引号内为对话），并为每段标注角色、情感与语速，且不修改任何文字",
                    "available_voices": available_voice_files,
                    "known_roles": prev_roles,
                    "segments_input": block,
                    "rules": {
                        "keep_text_exact": True,
                        "emotion_vector_order": ["喜","怒","哀","惧","厌恶","低落","惊喜","平静"],
                        "speaking_speed_range": [0.1, 2.0],
                        "line_length_range_cn": [int(self.config_manager.get("ai_seg_min_cn", 5)), int(self.config_manager.get("ai_seg_max_cn", 25))]
                    },
                    "output_format": {
                        "roles": [{"name": "旁白", "description": "叙述者", "suggested_voice": "播音女.wav"}],
                        "segments": [{"text": "…", "role": "旁白/角色名", "type": "dialogue/narration", "emotion": "标签", "emotion_vector": [0,0,0,0,0,0,0,0], "speaking_speed": 1.0}],
                        "assignments": [{"line": 0, "role": "旁白", "emotion": "中性", "emotion_vector": [0,0,0,0,0,0,0,0], "speaking_speed": 1.0}]
                    }
                }
                if is_ollama:
                    data = {"model": model, "prompt": json.dumps(prompt_obj, ensure_ascii=False), "stream": False, "options": {"temperature": float(self.config_manager.get("ai_temperature", 0.7)), "num_predict": max_tokens}}
                else:
                    data = {"model": model, "messages": [{"role": "user", "content": json.dumps(prompt_obj, ensure_ascii=False)}], "temperature": float(self.config_manager.get("ai_temperature", 0.7)), "max_tokens": max_tokens}
                api_url = _api_url()
                self.log_message(f"AI API调用 - URL: {api_url}")
                self.log_message(f"AI API调用 - Model: {model}")
                _headers_log = {k: ('***' if k.lower() == 'authorization' else headers.get(k)) for k in headers}
                self.log_message(f"AI API调用 - Headers: {_headers_log}")
                import requests as _req
                resp = _req.post(api_url, headers=headers, json=data, timeout=160)
                self.log_message(f"AI API响应状态码: {resp.status_code}")
                if resp.status_code != 200:
                    self.log_message(f"AI API错误响应内容: {resp.text}")
                resp.raise_for_status()
                ai_response = ''
                try:
                    result = resp.json()
                except Exception:
                    result = {}
                    ai_response = resp.text or ''
                if not ai_response:
                    if 'choices' in result and result.get('choices'):
                        ai_response = result['choices'][0]['message']['content']
                    else:
                        ai_response = result.get('response') or (result.get('message', {}).get('content', ''))
                import re as _re2
                parsed = None
                try:
                    parsed = json.loads(ai_response)
                except Exception:
                    pass
                if not isinstance(parsed, dict):
                    # 尝试代码块或包含 roles 的对象
                    patterns = [r"```json\s*(\{.*?\})\s*```", r"```\s*(\{.*?\})\s*```", r"(\{[^{}]*\"roles\"[^{}]*\})"]
                    for _p in patterns:
                        _m = _re2.findall(_p, ai_response, _re2.DOTALL)
                        for _json_str in _m:
                            try:
                                _obj = json.loads(_json_str)
                                if isinstance(_obj, dict):
                                    parsed = _obj
                                    break
                            except Exception:
                                continue
                        if isinstance(parsed, dict):
                            break
                if not isinstance(parsed, dict):
                    # 尝试截断修复
                    _start = ai_response.find('{')
                    if _start != -1:
                        brace = 0
                        _end = _start
                        for i, ch in enumerate(ai_response[_start:], _start):
                            if ch == '{':
                                brace += 1
                            elif ch == '}':
                                brace -= 1
                                if brace == 0:
                                    _end = i + 1
                                    break
                        if _end > _start:
                            try:
                                parsed = json.loads(ai_response[_start:_end])
                            except Exception:
                                parsed = None
                if not isinstance(parsed, dict):
                    parsed = {}
                # 记录本块响应长度，便于排查
                try:
                    self.log_message(f"AI块{bi+1}响应长度: {len(ai_response)} 字符")
                except Exception:
                    pass
                for r in parsed.get("roles", []):
                    n = r.get("name")
                    if n and n not in roles_seen:
                        roles_seen.add(n)
                        roles_acc.append(r)
                _chunk_assigns = []
                # 优先使用AI返回的segments进行合理分割
                _seg_list = parsed.get("segments", [])
                if isinstance(_seg_list, list) and _seg_list:
                    for seg in _seg_list:
                        if not isinstance(seg, dict):
                            continue
                        _text = (seg.get("text", "") or "").strip()
                        if not _text:
                            continue
                        _role = seg.get("role", "旁白")
                        _typ = seg.get("type", "narration")
                        try:
                            # 保留AI标注的对话角色；仅当类型为旁白/叙述时才使用"旁白"
                            if _typ == "narration":
                                _role = "旁白"
                                _typ = "narration"
                        except Exception:
                            pass
                        _emo = seg.get("emotion", "")
                        _vec = seg.get("emotion_vector")
                        if isinstance(_vec, list) and len(_vec) == 8:
                            _vec = self._normalize_vec_for_role(_vec, _role, _emo)
                        else:
                            _vec = [0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]
                        try:
                            _spd = float(seg.get("speaking_speed", 1.0) or 1.0)
                        except Exception:
                            _spd = 1.0
                        new_segments_acc.append(_text)
                        _line_idx = len(new_segments_acc) - 1
                        segments_output_acc.append({"text": _text, "role": _role, "type": _typ, "emotion": _emo, "emotion_vector": _vec, "speaking_speed": _spd})
                        _assign = {"line": _line_idx, "role": _role, "text": _text, "emotion": _emo, "emotion_vector": _vec, "speaking_speed": _spd}
                        assignments_acc.append(_assign)
                        _chunk_assigns.append(_assign)
                        if bool(self.config_manager.get("ai_adjust_emotion", True)):
                            line_emotions_acc[_line_idx] = _vec
                        if bool(self.config_manager.get("ai_adjust_speed", False)):
                            line_speeds_acc[_line_idx] = _spd
                for a in parsed.get("assignments", []):
                    if isinstance(a, dict) and isinstance(a.get("line", None), int):
                        li = a["line"]
                        if "text" not in a and isinstance(self.subtitle_segments, list) and li < len(self.subtitle_segments):
                            a["text"] = self.subtitle_segments[li]
                        try:
                            _vec = a.get("emotion_vector")
                            _role = a.get("role", "旁白")
                            _lab = a.get("emotion")
                            if isinstance(_vec, list) and len(_vec) == 8:
                                a["emotion_vector"] = self._normalize_vec_for_role(_vec, _role, _lab)
                        except Exception:
                            pass
                        assignments_acc.append(a)
                        _chunk_assigns.append(a)
                        vec = a.get("emotion_vector")
                        if isinstance(vec, list) and len(vec) == 8:
                            line_emotions_acc[li] = vec
                        spd = a.get("speaking_speed")
                        try:
                            line_speeds_acc[li] = float(spd if spd is not None else 1.0)
                        except Exception:
                            line_speeds_acc[li] = 1.0
                # 如果该块没有解析出 segments/assignments，则按输入块逐行构造默认分配（旁白）
                if not _chunk_assigns:
                    default_role = "旁白"
                    if not any(r.get("name") == default_role for r in roles_acc):
                        roles_acc.append({"name": default_role, "description": "叙述者", "gender": "neutral"})
                    for item in block:
                        if not isinstance(item, dict):
                            continue
                        li = int(item.get("line", 0))
                        txt = item.get("text", "")
                        _v0 = self._normalize_vec_for_role([0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0], default_role, "中性")
                        new_segments_acc.append(txt)
                        _line_idx = len(new_segments_acc) - 1
                        a = {"line": _line_idx, "role": default_role, "text": txt, "emotion": "中性", "emotion_vector": _v0, "speaking_speed": 1.0}
                        assignments_acc.append(a)
                        _chunk_assigns.append(a)
                        segments_output_acc.append({"text": txt, "role": default_role, "type": "narration", "emotion": "中性", "emotion_vector": _v0, "speaking_speed": 1.0})
                # 本块立即打印，便于用户查看
                try:
                    self._log_ai_segments({"assignments": _chunk_assigns})
                except Exception:
                    pass
            analysis_result = {
                "roles": roles_acc,
                "assignments": assignments_acc,
                "line_emotions": line_emotions_acc,
                "line_speeds": line_speeds_acc,
                "segments": segments_output_acc
            }
            if new_segments_acc:
                self.subtitle_segments = new_segments_acc
            for role in analysis_result["roles"]:
                if "suggested_voice" not in role:
                    rn = role.get("name", "")
                    rt = role.get("type", "other")
                    role["suggested_voice"] = self.suggest_voice_for_role(rn, rt)
            assignments_dict = {}
            for a in analysis_result.get("assignments", []):
                if isinstance(a, dict):
                    assignments_dict[a.get("line", 0)] = a.get("role", "旁白")
            analysis_result["assignments_dict"] = assignments_dict
            self.ai_analysis_result = analysis_result
            try:
                self._log_ai_segments(self.ai_analysis_result)
            except Exception:
                pass
            if hasattr(self, 'page') and self.page:
                async def _update_ui():
                    self.update_ai_analysis_ui()
                    self.apply_ai_suggestions(None)
                self.page.run_task(_update_ui)
        except Exception as _e:
            if hasattr(self, 'page') and self.page:
                async def _show_err():
                    self.show_message(f"AI分析失败: {_e}", True)
                self.page.run_task(_show_err)

    def _log_ai_segments(self, analysis_result):
        try:
            segs = analysis_result.get("segments")
            if isinstance(segs, list) and segs:
                self.log_message(f"AI智能分割段数: {len(segs)}")
                for i, s in enumerate(segs):
                    role = s.get("role", "旁白")
                    typ = s.get("type", "narration")
                    emo = s.get("emotion", "")
                    spd = s.get("speaking_speed", 1.0)
                    vec = s.get("emotion_vector")
                    text = s.get("text", "")
                    self.log_message(f"段{i+1}: 角色={role} 类型={typ} 语速={spd} 情感={emo} 向量={vec} 文本={text}")
                return
            assigns = analysis_result.get("assignments", [])
            if isinstance(assigns, list) and assigns:
                self.log_message(f"AI分配结果行数: {len(assigns)}")
                for a in assigns:
                    if not isinstance(a, dict):
                        continue
                    li = a.get("line", 0)
                    role = a.get("role", "旁白")
                    emo = a.get("emotion", "")
                    vec = a.get("emotion_vector")
                    spd = a.get("speaking_speed", 1.0)
                    txt = a.get("text")
                    if not txt and isinstance(self.subtitle_segments, list) and li < len(self.subtitle_segments):
                        txt = self.subtitle_segments[li]
                    self.log_message(f"行{li+1}: 角色={role} 语速={spd} 情感={emo} 向量={vec} 文本={txt}")
        except Exception as _e:
            self.log_message(f"打印AI分割结果失败: {_e}", "WARNING")

    def _is_dialogue_text(self, text):
        try:
            t = (text or "").strip()
            if not t:
                return False
            # 中文/英文引号判断
            if any(ch in t for ch in ["“","”","\"","『","』","「","」"]):
                return True
            # 姓名或称谓 + 冒号
            import re as _re
            if _re.match(r"^\s*[\u4e00-\u9fffA-Za-z]{1,20}[：:]\s*", t):
                return True
            return False
        except Exception:
            return False

    def _normalize_vec_for_role(self, vec, role, label=None):
        try:
            if not isinstance(vec, list) or len(vec) != 8:
                return [0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]
            vals = [float(x) if x is not None else 0.0 for x in vec]
            m = max(vals)
            idx = vals.index(m) if m > 0 else 7
            res = [0.0]*8
            v = float(m)
            if role == "旁白" and v > 0.5:
                v = 0.5
            res[idx] = v
            return res
        except Exception:
            return [0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]

    def suggest_voice_for_role(self, role_name, role_type="other"):
        """智能建议音色，基于现有音色文件进行智能匹配"""
        if not hasattr(self, 'available_voices') or not self.available_voices:
            return None
        
        # 获取已使用的音色（从AI分析结果中）
        used_voices = set()
        if hasattr(self, 'ai_analysis_result') and self.ai_analysis_result:
            for role in self.ai_analysis_result.get("roles", []):
                if role.get('suggested_voice'):
                    used_voices.add(role['suggested_voice'])
        
        # 获取当前已有角色的音色
        if hasattr(self, 'roles') and self.roles:
            for role in self.roles:
                if role.get('voice'):
                    used_voices.add(role['voice'])
        
        # 基于现有音色文件的智能分配策略
        # 现有音色: 女魔王, 年轻男, 搞笑女, 播音女, 激情男, 男播音
        # 注意：这里使用不带.wav扩展名的音色名称，与available_voices保持一致
        voice_mapping = {
            # 旁白/叙述者 - 优先使用播音类音色
            "narrator": ["播音女", "男播音"],
            "叙述": ["播音女", "男播音"],
            "旁白": ["播音女", "男播音"],
            
            # 男性角色
            "male_lead": ["激情男", "年轻男", "男播音"],
            "male_supporting": ["年轻男", "激情男", "男播音"],
            "男主": ["激情男", "年轻男"],
            "男": ["激情男", "年轻男", "男播音"],
            
            # 女性角色
            "female_lead": ["女魔王", "播音女"],
            "female_supporting": ["搞笑女", "播音女", "女魔王"],
            "女主": ["女魔王", "播音女"],
            "女": ["女魔王", "搞笑女", "播音女"],
            
            # 特殊角色类型
            "villain": ["女魔王"],  # 反派
            "comic": ["搞笑女"],   # 搞笑角色
            "serious": ["播音女", "男播音"],  # 严肃角色
        }
        
        # 根据角色类型和名称确定候选音色
        candidate_voices = []
        
        # 1. 根据角色类型匹配
        if role_type in voice_mapping:
            candidate_voices.extend(voice_mapping[role_type])
        
        # 2. 根据角色名称关键词匹配
        role_name_lower = role_name.lower()
        for key, voices in voice_mapping.items():
            if key in role_name_lower or key in role_name:
                candidate_voices.extend(voices)
        
        # 3. 性别关键词匹配
        if any(keyword in role_name for keyword in ['男', 'male', '先生', '哥', '弟']):
            candidate_voices.extend(["激情男", "年轻男", "男播音"])
        elif any(keyword in role_name for keyword in ['女', 'female', '小姐', '姐', '妹']):
            candidate_voices.extend(["女魔王", "搞笑女", "播音女"])
        
        # 4. 特殊角色名称匹配（使用不带.wav扩展名的音色名称）
        special_mappings = {
            "魔王": ["女魔王"],
            "boss": ["女魔王"],
            "老板": ["激情男", "男播音"],
            "主持": ["播音女", "男播音"],
            "解说": ["播音女", "男播音"],
            "小丑": ["搞笑女"],
            "喜剧": ["搞笑女"],
        }
        
        for keyword, voices in special_mappings.items():
            if keyword in role_name_lower or keyword in role_name:
                candidate_voices.extend(voices)
        
        # 去重并保持顺序
        seen = set()
        unique_candidates = []
        for voice in candidate_voices:
            if voice not in seen and voice in self.available_voices:
                seen.add(voice)
                unique_candidates.append(voice)
        
        # 如果没有特定匹配，使用默认顺序
        if not unique_candidates:
            unique_candidates = list(self.available_voices)
        
        # 选择第一个未使用的音色
        for voice in unique_candidates:
            if voice not in used_voices:
                self.log_message(f"为角色 '{role_name}' (类型: {role_type}) 分配音色: {voice}")
                return voice
        
        # 如果所有候选音色都被使用，选择使用次数最少的
        voice_usage_count = {}
        for voice in unique_candidates:
            voice_usage_count[voice] = list(used_voices).count(voice)
        
        # 选择使用次数最少的音色
        min_usage_voice = min(voice_usage_count.items(), key=lambda x: x[1])[0]
        self.log_message(f"所有候选音色已使用，为角色 '{role_name}' 分配使用次数最少的音色: {min_usage_voice}")
        return min_usage_voice
    
    def create_info_card(self, title, content, icon):
        """创建信息卡片"""
        return ft.Card(
            content=ft.Container(
                content=ft.Row([
                    ft.Icon(icon, color=ft.Colors.BLUE, size=20),
                    ft.Column([
                        ft.Text(title, weight=ft.FontWeight.BOLD, size=12),
                        ft.Text(str(content), size=11, color=ft.Colors.GREY_700)
                    ], spacing=2, expand=True)
                ], spacing=10),
                padding=10
            ),
            elevation=1
        )
    
    def create_list_card(self, title, items, icon):
        """创建列表卡片"""
        if not items:
            items = ["无"]
        
        item_widgets = []
        for item in items[:5]:  # 限制显示前5项
            item_widgets.append(ft.Text(f"• {item}", size=10, color=ft.Colors.GREY_700))
        
        return ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(icon, color=ft.Colors.ORANGE, size=20),
                        ft.Text(title, weight=ft.FontWeight.BOLD, size=12)
                    ], spacing=10),
                    ft.Column(item_widgets, spacing=2)
                ], spacing=5),
                padding=10
            ),
            elevation=1
        )
    
    def create_emotion_changes_card(self, emotion_changes):
        """创建情感变化卡片"""
        if not emotion_changes:
            emotion_changes = [{"position": "无", "emotion": "无变化", "reason": "无"}]
        
        change_widgets = []
        for change in emotion_changes[:3]:  # 限制显示前3项
            change_widgets.append(
                ft.Container(
                    content=ft.Column([
                        ft.Text(f"位置: {change.get('position', '未知')}", size=10, weight=ft.FontWeight.BOLD),
                        ft.Text(f"情感: {change.get('emotion', '未知')}", size=10),
                        ft.Text(f"原因: {change.get('reason', '未知')}", size=10, color=ft.Colors.GREY_600)
                    ], spacing=2),
                    padding=5,
                    border=ft.border.all(1, ft.Colors.GREY_300),
                    border_radius=5
                )
            )
        
        return ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(ft.Icons.MOOD, color=ft.Colors.GREEN, size=20),
                        ft.Text("情感变化", weight=ft.FontWeight.BOLD, size=12)
                    ], spacing=10),
                    ft.Column(change_widgets, spacing=5)
                ], spacing=5),
                padding=10
            ),
            elevation=1
        )
    
    def create_score_card(self, title, score, icon):
        """创建评分卡片"""
        # 尝试解析数字评分
        try:
            score_num = float(str(score).split('/')[0])
            score_color = ft.Colors.GREEN if score_num >= 7 else ft.Colors.ORANGE if score_num >= 4 else ft.Colors.RED
        except:
            score_color = ft.Colors.GREY
        
        return ft.Card(
            content=ft.Container(
                content=ft.Row([
                    ft.Icon(icon, color=score_color, size=24),
                    ft.Column([
                        ft.Text(title, weight=ft.FontWeight.BOLD, size=12),
                        ft.Text(str(score), size=16, weight=ft.FontWeight.BOLD, color=score_color)
                    ], spacing=2, expand=True)
                ], spacing=10),
                padding=15
            ),
            elevation=2
        )
    
    def update_ai_analysis_ui(self):
        """更新AI分析结果UI - 支持详细分析结果"""
        if not hasattr(self, 'ai_analysis_result') or not self.ai_analysis_result:
            return
        
        # 获取分析结果数据
        analysis_data = self.ai_analysis_result
        
        # 创建分析结果对话框
        def close_dialog(e):
            dialog.open = False
            self.page.update()
        
        def apply_suggestions(e):
            self.apply_ai_suggestions(None)
            close_dialog(e)
        
        # 创建标签页内容
        tabs = []
        
        # 1. 文章分析标签页
        if "article_analysis" in analysis_data:
            article_info = analysis_data["article_analysis"]
            article_content = ft.Column([
                self.create_info_card("文章类型", article_info.get("type", "未知"), ft.Icons.ARTICLE),
                self.create_info_card("主要主题", article_info.get("theme", "无"), ft.Icons.TOPIC),
                self.create_info_card("写作风格", article_info.get("style", "无"), ft.Icons.STYLE),
                self.create_info_card("情感色调", article_info.get("emotion_tone", "中性"), ft.Icons.MOOD),
                self.create_info_card("目标受众", article_info.get("target_audience", "通用"), ft.Icons.PEOPLE),
                self.create_info_card("复杂度等级", f"{article_info.get('complexity_level', 3)}/5", ft.Icons.SIGNAL_CELLULAR_ALT),
                self.create_info_card("阅读难度", article_info.get("reading_difficulty", "中等"), ft.Icons.SCHOOL),
                self.create_info_card("预估时长", f"{article_info.get('estimated_duration', '未知')}分钟", ft.Icons.TIMER),
            ], spacing=10, scroll=ft.ScrollMode.AUTO)
            
            tabs.append(ft.Tab(
                text="文章分析",
                icon=ft.Icons.ANALYTICS,
                content=ft.Container(content=article_content, padding=20, height=400)
            ))
        
        # 2. 语音指导标签页
        if "voice_guidance" in analysis_data:
            voice_info = analysis_data["voice_guidance"]
            voice_content = ft.Column([
                self.create_info_card("建议语速", voice_info.get("recommended_pace", "正常"), ft.Icons.SPEED),
                self.create_info_card("语调风格", voice_info.get("tone_style", "自然"), ft.Icons.RECORD_VOICE_OVER),
                self.create_list_card("重点强调", voice_info.get("emphasis_points", []), ft.Icons.PRIORITY_HIGH),
                self.create_list_card("停顿建议", voice_info.get("pause_suggestions", []), ft.Icons.PAUSE),
                self.create_emotion_changes_card(voice_info.get("emotion_changes", [])),
            ], spacing=10, scroll=ft.ScrollMode.AUTO)
            
            tabs.append(ft.Tab(
                text="语音指导",
                icon=ft.Icons.RECORD_VOICE_OVER,
                content=ft.Container(content=voice_content, padding=20, height=400)
            ))
        
        # 3. 角色信息标签页
        roles = analysis_data.get("roles", [])
        role_items = []
        for role in roles:
            role_card = ft.Card(
                content=ft.Container(
                    content=ft.Column([
                        ft.ListTile(
                            leading=ft.Icon(
                                ft.Icons.PERSON if role.get("gender") == "neutral" 
                                else ft.Icons.MAN if role.get("gender") == "male" 
                                else ft.Icons.WOMAN,
                                color=ft.Colors.BLUE
                            ),
                            title=ft.Text(role["name"], weight=ft.FontWeight.BOLD, size=16),
                            subtitle=ft.Text(role.get("description", "无描述"))
                        ),
                        ft.Divider(height=1),
                        ft.Row([
                            ft.Text("性别:", weight=ft.FontWeight.BOLD),
                            ft.Text(role.get("gender", "neutral"))
                        ]),
                        ft.Row([
                            ft.Text("性格:", weight=ft.FontWeight.BOLD),
                            ft.Text(role.get("personality", "无"), expand=True)
                        ]),
                        ft.Row([
                            ft.Text("声音特征:", weight=ft.FontWeight.BOLD),
                            ft.Text(role.get("voice_characteristics", "无"), expand=True)
                        ]),
                        ft.Row([
                            ft.Text("年龄范围:", weight=ft.FontWeight.BOLD),
                            ft.Text(role.get("age_range", "无"))
                        ]),
                        ft.Row([
                            ft.Text("说话风格:", weight=ft.FontWeight.BOLD),
                            ft.Text(role.get("speaking_style", "无"), expand=True)
                        ]),
                        ft.Row([
                            ft.Text("建议音色:", weight=ft.FontWeight.BOLD),
                            ft.Text(role.get("suggested_voice", "无"), expand=True)
                        ]),
                    ], spacing=5),
                    padding=15
                ),
                elevation=2
            )
            role_items.append(role_card)
        
        role_content = ft.ListView(controls=role_items, spacing=10, height=400)
        tabs.append(ft.Tab(
            text="角色信息",
            icon=ft.Icons.PEOPLE,
            content=ft.Container(content=role_content, padding=20)
        ))
        
        # 4. 内容结构标签页
        if "content_structure" in analysis_data:
            structure_info = analysis_data["content_structure"]
            paragraphs = structure_info.get("paragraphs", [])
            structure_items = []
            
            for para in paragraphs:
                importance_stars = "★" * para.get("importance", 1)
                structure_card = ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Row([
                                ft.Text(f"段落 {para.get('index', 0) + 1}", weight=ft.FontWeight.BOLD),
                                ft.Chip(label=ft.Text(str(para.get("type", "未知"))), bgcolor=ft.Colors.BLUE_100),
                                ft.Text(importance_stars, color=ft.Colors.ORANGE)
                            ]),
                            ft.Text(f"主要内容: {para.get('main_idea', '无')}", size=12),
                            ft.Text(f"情感色彩: {para.get('emotion', '中性')}", size=12, color=ft.Colors.GREY_600)
                        ], spacing=5),
                        padding=10
                    ),
                    elevation=1
                )
                structure_items.append(structure_card)
            
            structure_content = ft.ListView(controls=structure_items, spacing=5, height=400)
            tabs.append(ft.Tab(
                text="内容结构",
                icon=ft.Icons.ACCOUNT_TREE,
                content=ft.Container(content=structure_content, padding=20)
            ))
        
        # 5. 分配预览标签页
        assignments = analysis_data.get("assignments", {})
        assignment_items = []
        for assignment in assignments:
            if isinstance(assignment, dict):
                line_index = assignment.get("line", 0)
                role_name = assignment.get("role", "未知")
                text = assignment.get("text", "")
                emotion = assignment.get("emotion", "中性")
                emphasis = assignment.get("emphasis_level", 1)
                speed = assignment.get("speaking_speed", 1.0)
                
                # 截断文本显示（放宽显示长度）
                display_text = text[:120] + "..." if len(text) > 120 else text
                
                assignment_card = ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Row([
                                ft.Text(f"第{line_index + 1}行", weight=ft.FontWeight.BOLD),
                                ft.Chip(label=ft.Text(str(role_name)), bgcolor=ft.Colors.BLUE_100),
                                ft.Text(f"强调度: {emphasis}/5", size=10)
                            ]),
                            ft.Text(display_text, size=12),
                            ft.Row([
                                ft.Text(f"情感: {emotion}", size=10, color=ft.Colors.GREY_600),
                                ft.Text(f"语速: {speed}x", size=10, color=ft.Colors.GREY_600)
                            ])
                        ], spacing=3),
                        padding=10
                    ),
                    elevation=1
                )
                assignment_items.append(assignment_card)
        
        assignment_content = ft.ListView(controls=assignment_items, spacing=5, height=400)  # 显示所有字幕
        tabs.append(ft.Tab(
            text="分配预览",
            icon=ft.Icons.ASSIGNMENT,
            content=ft.Container(content=assignment_content, padding=20)
        ))
        
        # 6. 质量评估标签页
        if "quality_assessment" in analysis_data:
            quality_info = analysis_data["quality_assessment"]
            quality_content = ft.Column([
                self.create_score_card("适合度评分", quality_info.get("suitability_score", "未评分"), ft.Icons.STAR),
                self.create_list_card("潜在问题", quality_info.get("potential_issues", []), ft.Icons.WARNING),
                self.create_list_card("改进建议", quality_info.get("improvement_suggestions", []), ft.Icons.LIGHTBULB),
                self.create_list_card("技术注意事项", quality_info.get("technical_notes", []), ft.Icons.SETTINGS),
            ], spacing=10, scroll=ft.ScrollMode.AUTO)
            
            tabs.append(ft.Tab(
                text="质量评估",
                icon=ft.Icons.ASSESSMENT,
                content=ft.Container(content=quality_content, padding=20, height=400)
            ))
        
        # 7. 合成建议标签页
        if "synthesis_recommendations" in analysis_data:
            synth_info = analysis_data["synthesis_recommendations"]
            synth_content = ft.Column([
                self.create_info_card("多角色混合", synth_info.get("voice_mixing", "无"), ft.Icons.MIX),
                self.create_info_card("背景音乐", synth_info.get("background_music", "无"), ft.Icons.MUSIC_NOTE),
                self.create_info_card("音效建议", synth_info.get("sound_effects", "无"), ft.Icons.GRAPHIC_EQ),
                self.create_info_card("后期处理", synth_info.get("post_processing", "无"), ft.Icons.TUNE),
            ], spacing=10, scroll=ft.ScrollMode.AUTO)
            
            tabs.append(ft.Tab(
                text="合成建议",
                icon=ft.Icons.BUILD,
                content=ft.Container(content=synth_content, padding=20, height=400)
            ))
        
        # 创建标签页控件
        tab_bar = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            tabs=tabs,
            expand=1
        )
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.PSYCHOLOGY, color=ft.Colors.BLUE),
                ft.Text("AI深度分析结果", weight=ft.FontWeight.BOLD, size=18)
            ]),
            content=ft.Container(
                content=tab_bar,
                width=800,
                height=500
            ),
            actions=[
                ft.TextButton("取消", on_click=close_dialog),
                ft.ElevatedButton("应用建议", on_click=apply_suggestions)
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )
        
        try:
            if dialog not in self.page.overlay:
                self.page.overlay.append(dialog)
            dialog.open = True
        except Exception:
            try:
                self.page.dialog = dialog
                dialog.open = True
            except Exception:
                pass
        
        self.show_message(f"AI分析完成！识别了 {len(roles)} 个角色，分配了 {len(assignments)} 条字幕")
        
    def apply_ai_suggestions(self, e):
        """应用AI建议"""
        if not hasattr(self, 'ai_analysis_result') or not self.ai_analysis_result:
            self.show_message("请先进行AI分析", True)
            return
        
        try:
            # 清空现有的角色和分配
            self.subtitle_roles.clear()
            self.subtitle_line_roles.clear()
            
            # 应用AI建议的角色
            for role_info in self.ai_analysis_result.get("roles", []):
                role_name = role_info["name"]
                suggested_voice = role_info.get("suggested_voice", "")
                
                # 处理AI返回的音色名称（可能包含扩展名或路径）
                voice_to_use = None
                if suggested_voice and hasattr(self, 'available_voices'):
                    sv = str(suggested_voice).strip()
                    # 1) 直接按可用音色（stem）匹配
                    if sv in self.available_voices:
                        voice_to_use = sv
                    else:
                        # 2) 提取文件名与stem，支持多种扩展（mp3/wav/...）
                        base = os.path.basename(sv)
                        stem = os.path.splitext(base)[0]
                        # 先看是否完全匹配已扫描的文件名
                        try:
                            scanned_names = [vf.name for vf in getattr(self, 'voice_files', [])]
                        except Exception:
                            scanned_names = []
                        if base in scanned_names:
                            voice_to_use = stem
                        elif stem in self.available_voices:
                            voice_to_use = stem
                        else:
                            # 3) 大小写不敏感兜底
                            lower_map = {v.lower(): v for v in self.available_voices}
                            if sv.lower() in lower_map:
                                voice_to_use = lower_map[sv.lower()]
                            elif stem.lower() in lower_map:
                                voice_to_use = lower_map[stem.lower()]
                
                # 分配音色
                if voice_to_use:
                    self.subtitle_roles[role_name] = voice_to_use
                elif hasattr(self, 'available_voices') and self.available_voices:
                    self.subtitle_roles[role_name] = self.available_voices[0]
                else:
                    # 如果没有可用音色，使用空字符串作为占位符
                    self.subtitle_roles[role_name] = ""
            
            # 应用AI建议的字幕分配
            # 优先使用兼容的assignments_dict格式
            assignments = self.ai_analysis_result.get("assignments_dict", {})
            if not assignments:
                # 如果没有assignments_dict，尝试从assignments列表转换
                assignments_list = self.ai_analysis_result.get("assignments", [])
                assignments = {}
                for assignment in assignments_list:
                    if isinstance(assignment, dict):
                        line_index = assignment.get("line", 0)
                        role_name = assignment.get("role", "旁白")
                        assignments[line_index] = role_name
            
            for line_index, role_name in assignments.items():
                # 确保角色存在；若不在角色列表中，加入占位以便下拉显示
                if role_name not in self.subtitle_roles:
                    self.subtitle_roles[role_name] = ""
                self.subtitle_line_roles[int(line_index)] = role_name

            # 写入行情感向量映射（优先使用 line_emotions，其次从 assignments 列表回填）
            try:
                line_emotions = self.ai_analysis_result.get("line_emotions")
                emotions_map = {}
                if isinstance(line_emotions, dict):
                    for k, v in line_emotions.items():
                        try:
                            idx = int(k)
                        except:
                            idx = int(k) if isinstance(k, int) else None
                        if idx is not None and isinstance(v, list) and len(v) == 8:
                            emotions_map[idx] = v
                else:
                    # 回退：从 assignments 列表查找行情感向量
                    for assignment in self.ai_analysis_result.get("assignments", []):
                        if isinstance(assignment, dict):
                            idx = assignment.get("line")
                            vec = assignment.get("emotion_vector")
                            if isinstance(idx, int) and isinstance(vec, list) and len(vec) == 8:
                                emotions_map[idx] = vec
                if emotions_map and bool(self.config_manager.get("ai_adjust_emotion", True)):
                    self.subtitle_line_emotions = emotions_map
                try:
                    if bool(self.config_manager.get("ai_adjust_speed", False)):
                        ls = self.ai_analysis_result.get("line_speeds", {})
                        if isinstance(ls, dict):
                            self.subtitle_line_speeds = {int(k): float(v) for k, v in ls.items()}
                except Exception:
                    pass
            except Exception as _emo_err:
                self.log_message(f"写入行情感向量时出现问题: {_emo_err}")
            
            # 更新UI
            self.update_role_list()
            self.update_subtitle_preview_simple()
            # 持久化保存角色列表
            if hasattr(self, 'config_manager'):
                self.config_manager.set("subtitle_roles", self.subtitle_roles)
            
            applied_roles = len(self.subtitle_roles)
            applied_assignments = len([k for k, v in self.subtitle_line_roles.items() if v in self.subtitle_roles])
            
            self.show_message(f"已应用AI建议：{applied_roles} 个角色，{applied_assignments} 条分配")
            
        except Exception as e:
            self.log_message(f"应用AI建议失败: {e}")
            self.show_message(f"应用AI建议失败: {e}", True)
    
    def batch_assign_role(self, e):
        """批量分配角色"""
        if not self.subtitle_roles:
            self.show_message("请先添加角色", True)
            return
        
        def close_dialog(e):
            dialog.open = False
            if hasattr(self, 'page') and self.page:
                self.page.update()
        
        def apply_batch_assignment(e):
            selected_role = role_dropdown.value
            start_line = int(start_line_field.value) if start_line_field.value.isdigit() else 0
            end_line = int(end_line_field.value) if end_line_field.value.isdigit() else len(self.subtitle_segments) - 1
            
            if not selected_role:
                self.show_message("请选择角色", True)
                return
            
            # 应用批量分配
            for i in range(start_line, min(end_line + 1, len(self.subtitle_segments))):
                self.subtitle_line_roles[i] = selected_role
            
            self.update_subtitle_preview_simple()
            
            dialog.open = False
            if hasattr(self, 'page') and self.page:
                self.page.update()
            
            self.show_message(f"已将第{start_line+1}-{min(end_line+1, len(self.subtitle_segments))}行分配给角色'{selected_role}'")
        
        # 创建批量分配对话框
        role_dropdown = ft.Dropdown(
            label="选择角色",
            width=200,
            options=[ft.dropdown.Option(role, role) for role in self.subtitle_roles.keys()]
        )
        
        start_line_field = ft.TextField(
            label="起始行号",
            value="0",
            width=100,
            keyboard_type=ft.KeyboardType.NUMBER
        )
        
        end_line_field = ft.TextField(
            label="结束行号", 
            value=str(len(self.subtitle_segments) - 1) if hasattr(self, 'subtitle_segments') and self.subtitle_segments else "0",
            width=100,
            keyboard_type=ft.KeyboardType.NUMBER
        )
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("批量分配角色"),
            content=ft.Container(
                content=ft.Column([
                    role_dropdown,
                    ft.Container(height=10),
                    ft.Row([
                        start_line_field,
                        ft.Text("到"),
                        end_line_field,
                    ], spacing=10),
                    ft.Container(height=5),
                    ft.Text("提示：行号从0开始", size=12, color=ft.Colors.GREY_600),
                ], spacing=10),
                width=300,
                height=180
            ),
            actions=[
                ft.TextButton("取消", on_click=close_dialog),
                ft.ElevatedButton("应用", on_click=apply_batch_assignment),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        if hasattr(self, 'page') and self.page:
            self.page.overlay.append(dialog)
            dialog.open = True
            self.page.update()
    
    def clear_all_assignments(self, e):
        """清空所有分配"""
        self.subtitle_line_roles.clear()
        self.update_subtitle_preview_simple()
        self.show_message("已清空所有角色分配")
    
    def assign_role_to_line(self, line_index, role_name):
        """为指定行分配角色"""
        if role_name == "未分配":
            if line_index in self.subtitle_line_roles:
                del self.subtitle_line_roles[line_index]
        else:
            self.subtitle_line_roles[line_index] = role_name
        
        # 仅更新页面，避免滚动位置丢失
        # 确保页面更新
        if hasattr(self, 'page') and self.page:
            self.page.update()
    

    
    def clear_roles(self, e):
        """清空所有角色"""
        self.subtitle_roles.clear()
        self.subtitle_line_roles.clear()
        self.update_role_list()
        self.update_subtitle_preview_simple()
        # 持久化保存角色列表（清空）
        if hasattr(self, 'config_manager'):
            self.config_manager.set("subtitle_roles", self.subtitle_roles)
        self.show_message("已清空所有角色")
    
    def update_role_list(self):
        """更新角色列表显示"""
        if not hasattr(self, 'role_list') or not self.role_list:
            return
        
        self.role_list.controls.clear()
        dark = self.is_dark_theme()
        
        if not self.subtitle_roles:
            # 显示空状态
            empty_state = ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.PEOPLE_OUTLINE, size=40, color=(ft.Colors.GREY_400 if not dark else ft.Colors.GREY_300)),
                    ft.Text("暂无角色", size=14, color=(ft.Colors.GREY_500 if not dark else ft.Colors.GREY_400)),
                    ft.Text("点击'添加角色'开始", size=12, color=(ft.Colors.GREY_400 if not dark else ft.Colors.GREY_500)),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                alignment=ft.alignment.center,
                padding=ft.padding.all(20)
            )
            self.role_list.controls.append(empty_state)
        else:
            # 显示角色列表
            for role_name, voice_path in self.subtitle_roles.items():
                voice_name = os.path.basename(voice_path) if voice_path else "未选择"
                
                role_item = ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.PERSON, color=ft.Colors.PURPLE_400),
                        ft.Column([
                            ft.Text(role_name, weight=ft.FontWeight.BOLD, size=14),
                            ft.Text(voice_name, size=12, color=(ft.Colors.GREY_400 if dark else ft.Colors.GREY_600)),
                        ], spacing=2, expand=True),
                        ft.Row([
                            ft.IconButton(
                                icon=ft.Icons.PLAY_CIRCLE,
                                tooltip="试听音色",
                                on_click=lambda e, voice=voice_path: self.play_role_voice_sample(voice),
                                icon_color=ft.Colors.GREEN
                            ),
                            ft.IconButton(
                                icon=ft.Icons.EDIT,
                                tooltip="编辑角色",
                                on_click=lambda e, role=role_name: self.edit_role(role),
                                icon_color=ft.Colors.BLUE
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE,
                                tooltip="删除角色",
                                on_click=lambda e, role=role_name: self.delete_role(role),
                                icon_color=ft.Colors.RED
                            ),
                        ], spacing=0),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    padding=ft.padding.all(10),
                    bgcolor=(ft.Colors.with_opacity(0.06, ft.Colors.WHITE) if dark else ft.Colors.GREY_50),
                    border_radius=5,
                    border=ft.border.all(1, ft.Colors.GREY_700 if dark else ft.Colors.GREY_200),
                )
                self.role_list.controls.append(role_item)
        
        if hasattr(self, 'page') and self.page:
            self.page.update()
    
    def play_role_voice_sample(self, voice_path):
        """播放角色音色示例"""
        # 解析为实际文件路径，支持多种扩展名与大小写
        resolved_path = None

        try:
            if voice_path:
                p = Path(voice_path)
                # 如果是绝对路径且存在，直接使用
                if p.is_absolute() and p.exists():
                    resolved_path = str(p.absolute())
                else:
                    # 基于文件名（stem）在已扫描文件中查找
                    stem = p.stem if p.suffix else str(p)

                    candidates = []
                    if hasattr(self, 'voice_files') and self.voice_files:
                        # 先按 stem 匹配（不区分大小写）
                        candidates = [vf for vf in self.voice_files if vf.stem.lower() == stem.lower()]
                        # 如果传入带扩展的文件名，尝试按完整文件名匹配
                        if not candidates and p.suffix:
                            candidates = [vf for vf in self.voice_files if vf.name.lower() == str(p.name).lower()]

                    if candidates:
                        resolved_path = str(candidates[0].absolute())
                    else:
                        # 回退：在 yinse 文件夹中尝试不同扩展
                        voice_folder = Path('yinse')
                        if p.suffix:
                            fp = voice_folder / p.name
                            if fp.exists():
                                resolved_path = str(fp.absolute())
                        else:
                            supported_exts = [".wav", ".mp3", ".wma", ".flac", ".ogg", ".m4a", ".aac", ".opus"]
                            for ext in supported_exts:
                                fp = voice_folder / f"{stem}{ext}"
                                if fp.exists():
                                    resolved_path = str(fp.absolute())
                                    break

            if not resolved_path or not os.path.exists(resolved_path):
                self.show_message("音色文件不存在", True)
                return

            # 初始化并播放
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
            pygame.mixer.music.load(resolved_path)
            pygame.mixer.music.play()
            self.show_message("正在播放音色示例...")
        except Exception as e:
            self.show_message(f"播放失败: {e}", True)
    
    def edit_role(self, role_name):
        """编辑角色"""
        if role_name not in self.subtitle_roles:
            return
        
        def close_dialog(e):
            dialog.open = False
            if hasattr(self, 'page') and self.page:
                self.page.update()
        
        def save_changes(e):
            new_name = role_name_field.value.strip()
            selected_voice = voice_dropdown.value
            
            if not new_name:
                self.show_message("请输入角色名称", True)
                return
            
            if not selected_voice:
                self.show_message("请选择音色", True)
                return
            
            # 如果角色名称改变了，需要更新相关引用
            if new_name != role_name:
                # 更新角色列表
                del self.subtitle_roles[role_name]
                self.subtitle_roles[new_name] = selected_voice
                
                # 更新字幕行的角色分配
                for line_index, assigned_role in self.subtitle_line_roles.items():
                    if assigned_role == role_name:
                        self.subtitle_line_roles[line_index] = new_name
            else:
                self.subtitle_roles[role_name] = selected_voice
            
            self.update_role_list()
            self.update_subtitle_preview_simple()
            # 持久化保存角色列表
            if hasattr(self, 'config_manager'):
                self.config_manager.set("subtitle_roles", self.subtitle_roles)
            
            dialog.open = False
            if hasattr(self, 'page') and self.page:
                self.page.update()
            
            self.show_message(f"角色 '{new_name}' 更新成功")
        
        # 创建编辑对话框
        role_name_field = ft.TextField(
            label="角色名称",
            value=role_name,
            width=200
        )
        
        voice_dropdown = ft.Dropdown(
            label="选择音色",
            value=self.subtitle_roles[role_name],
            width=250,
            options=[ft.dropdown.Option(voice) for voice in self.available_voices] if hasattr(self, 'available_voices') else []
        )
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"编辑角色: {role_name}"),
            content=ft.Container(
                content=ft.Column([
                    role_name_field,
                    ft.Container(height=10),
                    voice_dropdown,
                ], spacing=10),
                width=300,
                height=150
            ),
            actions=[
                ft.TextButton("取消", on_click=close_dialog),
                ft.ElevatedButton("保存", on_click=save_changes),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        if hasattr(self, 'page') and self.page:
            self.page.overlay.append(dialog)
            dialog.open = True
            self.page.update()
    
    def delete_role(self, role_name):
        """删除角色"""
        def confirm_delete(e):
            # 删除角色
            if role_name in self.subtitle_roles:
                del self.subtitle_roles[role_name]
            
            # 清除相关的字幕行分配
            lines_to_clear = [line_index for line_index, assigned_role in self.subtitle_line_roles.items() 
                             if assigned_role == role_name]
            for line_index in lines_to_clear:
                del self.subtitle_line_roles[line_index]
            
            self.update_role_list()
            self.update_subtitle_preview_simple()
            # 持久化保存角色列表
            if hasattr(self, 'config_manager'):
                self.config_manager.set("subtitle_roles", self.subtitle_roles)
            
            dialog.open = False
            if hasattr(self, 'page') and self.page:
                self.page.update()
            
            self.show_message(f"角色 '{role_name}' 已删除")
        
        def cancel_delete(e):
            dialog.open = False
            if hasattr(self, 'page') and self.page:
                self.page.update()
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("确认删除"),
            content=ft.Text(f"确定要删除角色 '{role_name}' 吗？\n这将清除所有相关的字幕分配。"),
            actions=[
                ft.TextButton("取消", on_click=cancel_delete),
                ft.ElevatedButton("删除", on_click=confirm_delete, 
                                style=ft.ButtonStyle(color=ft.Colors.WHITE, bgcolor=ft.Colors.RED)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        if hasattr(self, 'page') and self.page:
            self.page.overlay.append(dialog)
            dialog.open = True
            self.page.update()
        
    def create_console_output_view(self):
        """创建控制台输出视图"""
        # 使用ListView替代TextField，支持自动滚动
        self.console_output = ft.ListView(
            expand=1,
            spacing=2,
            padding=10,
            auto_scroll=True,  # 启用自动滚动
            controls=[],
        )
        
        # 重放早期缓存的日志
        self.replay_early_logs()
        
        # 创建调试模式开关
        debug_switch = ft.Switch(
            label="调试模式",
            value=self.debug_mode,
            on_change=self.toggle_debug_mode,
        )
        
        # 创建日志级别下拉菜单
        self.log_level_dropdown = ft.Dropdown(
            label="日志级别",
            value="INFO",
            options=[
                ft.dropdown.Option("DEBUG", "调试"),
                ft.dropdown.Option("INFO", "信息"),
                ft.dropdown.Option("WARNING", "警告"),
                ft.dropdown.Option("ERROR", "错误"),
                ft.dropdown.Option("CRITICAL", "严重"),
            ],
            width=120,
            on_change=self.on_log_level_change,
        )
        
        return ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.TERMINAL, color=ft.Colors.GREEN),
                        title=ft.Text("控制台输出", weight=ft.FontWeight.BOLD),
                        subtitle=ft.Text("实时显示webui实例的控制台日志"),
                        trailing=ft.Row([
                            self.log_level_dropdown,
                            debug_switch,
                            ft.IconButton(
                                icon=ft.Icons.CLEAR,
                                tooltip="清空日志",
                                on_click=self.clear_console,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.SAVE,
                                tooltip="保存日志",
                                on_click=self.save_console_log,
                            ),
                        ], tight=True),
                    ),
                    ft.Divider(),
                    ft.Container(
                        content=self.console_output,
                        bgcolor=ft.Colors.BLACK,
                        border_radius=8,
                        padding=5,
                        height=400,  # 固定高度
                    ),
                ], spacing=10),
                padding=20,
            ),
            elevation=2,
        )

    def create_generation_history_view(self):
        setattr(self, 'generation_history_list', ft.ListView(spacing=8, auto_scroll=False, height=520, controls=[]))
        self.history_checkboxes = []
        try:
            hist = self.config_manager.get('generation_history', []) or []
            # 反转列表，让最新的记录显示在最上面
            hist = list(reversed(hist))
            for h in hist:
                try:
                    self.generation_history_list.controls.append(self.build_history_item_control(h))
                except Exception:
                    pass
        except Exception:
            pass
        
        # 功能区
        self.select_all_cb = ft.Checkbox(label="全选", on_change=self.on_history_select_all)
        delete_selected_btn = ft.ElevatedButton("删除选中", icon=ft.Icons.DELETE_SWEEP, style=ft.ButtonStyle(color=ft.Colors.RED), on_click=self.delete_selected_history_items)
        open_folder_btn = ft.ElevatedButton("打开输出目录", icon=ft.Icons.FOLDER, on_click=lambda e: os.startfile("outputs") if os.path.exists("outputs") else None)
        delete_recent_btn = ft.ElevatedButton("删除刚生成的音频", icon=ft.Icons.DELETE, on_click=self.delete_recent_audio)
        
        card = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.HISTORY, color=ft.Colors.BLUE, size=30), 
                        title=ft.Text("生成记录", weight=ft.FontWeight.BOLD, size=18), 
                        subtitle=ft.Text("管理您生成的语音、字幕、播客及批量任务文件"),
                        trailing=ft.Row([self.select_all_cb, delete_selected_btn, open_folder_btn, delete_recent_btn], alignment=ft.MainAxisAlignment.END, spacing=10, width=550)
                    ),
                    ft.Divider(),
                    ft.Container(
                        content=self.generation_history_list,
                        expand=True,
                        padding=ft.padding.only(bottom=10)
                    )
                ], spacing=5),
                padding=15,
            ),
            elevation=3,
            margin=10
        )
        return ft.Container(content=card, expand=True)

    def on_history_select_all(self, e):
        """全选/取消全选历史记录"""
        is_selected = self.select_all_cb.value
        if hasattr(self, 'history_checkboxes'):
            for cb in self.history_checkboxes:
                cb.value = is_selected
            if self.page:
                self.page.update()

    def delete_selected_history_items(self, e):
        """删除选中的历史记录及文件"""
        if not hasattr(self, 'history_checkboxes'):
            return
            
        selected_items = [cb.data for cb in self.history_checkboxes if cb.value]
        if not selected_items:
             self.show_message("请先选择要删除的记录")
             return
        
        deleted_count = 0
        for item in selected_items:
            fp = item.get('file')
            # 删除文件
            if fp and os.path.exists(fp):
                try:
                    os.remove(fp)
                except:
                    pass
            deleted_count += 1
            
        # 更新配置
        current_hist = self.config_manager.get('generation_history', []) or []
        selected_files = set(item.get('file') for item in selected_items)
        
        new_hist = [h for h in current_hist if h.get('file') not in selected_files]
        self.config_manager.set('generation_history', new_hist)
        
        self.show_message(f"已删除 {deleted_count} 条记录及对应文件")
        
        # 刷新列表
        self.history_checkboxes = []
        self.generation_history_list.controls = []
        display_hist = list(reversed(new_hist))
        for h in display_hist:
            self.generation_history_list.controls.append(self.build_history_item_control(h))
            
        # 重置全选框
        self.select_all_cb.value = False
        
        if self.page:
            self.page.update()
        

        
    def create_custom_port_field(self):
        """创建自定义端口号输入框"""
        self.custom_port_field = ft.TextField(
            value="7860",
            width=80,
            text_align=ft.TextAlign.CENTER,
            keyboard_type=ft.KeyboardType.NUMBER,
            suffix_text="端口",
            tooltip="自定义启动端口号",
            # helper_text="范围: 1024-65535",
            text_size=12,
            content_padding=ft.padding.symmetric(horizontal=8, vertical=8),
        )
        return self.custom_port_field
    
    def create_device_mode_dropdown(self):
        """创建设备模式选择下拉框"""
        self.device_mode_dropdown = ft.Dropdown(
            width=120,
            options=[
                ft.dropdown.Option("auto", "自动检测"),
                ft.dropdown.Option("gpu", "GPU模式"),
                ft.dropdown.Option("cpu", "CPU模式"),
            ],
            value="auto",
            tooltip="选择运行设备模式",
            text_size=12,
            content_padding=ft.padding.symmetric(horizontal=8, vertical=8),
        )
        return self.device_mode_dropdown

    def create_voice_selector_row(self, target_dropdown, category_attr_name):
        """创建一个带有分类筛选功能的音色选择行"""
        # 1. Analyze categories
        categories = set()
        if hasattr(self, 'voice_files'):
            voice_folder = Path("yinse")
            for p in self.voice_files:
                try:
                    rel = p.relative_to(voice_folder)
                    folder = rel.parent
                    if str(folder) == ".":
                        categories.add("根目录")
                    else:
                        categories.add(str(folder))
                except:
                    categories.add("其他")
        
        sorted_categories = sorted(list(categories))
        sorted_categories.insert(0, "全部")
        sorted_categories.insert(1, "已选(AI候选)")

        # 2. Create Category Dropdown
        category_dropdown = ft.Dropdown(
            label="分类筛选",
            width=120,
            options=[ft.dropdown.Option(c) for c in sorted_categories],
            value="全部",
            text_size=12,
            content_padding=ft.padding.symmetric(horizontal=8, vertical=6),
        )
        setattr(self, category_attr_name, category_dropdown)

        # 3. Define Change Handler
        def on_category_change(e):
            cat = category_dropdown.value
            self.update_voice_dropdown_options(target_dropdown, cat)
            if hasattr(self, 'page') and self.page:
                self.page.update()

        category_dropdown.on_change = on_category_change
        
        # Initialize options based on current category (Default All)
        self.update_voice_dropdown_options(target_dropdown, "全部")

        # 4. Return Row
        return ft.Row([category_dropdown, target_dropdown], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def update_voice_dropdown_options(self, target_dropdown, category):
        """根据分类更新音色下拉框选项"""
        if not hasattr(self, 'voice_files') or not self.voice_files:
            target_dropdown.options = []
            return

        voice_folder = Path("yinse")
        custom_names = self.config_manager.get("voice_custom_names", {}) or {}
        
        filtered_files = []
        
        # Special category for selected voices
        if category == "已选(AI候选)":
            if hasattr(self, 'voice_library_selected'):
                for p in self.voice_files:
                    if str(p.absolute()) in self.voice_library_selected:
                        filtered_files.append(p)
        else:
            for p in self.voice_files:
                # Filter logic
                if category == "全部":
                    filtered_files.append(p)
                    continue
                    
                try:
                    rel = p.relative_to(voice_folder)
                    folder_name = str(rel.parent)
                    if folder_name == ".":
                        folder_name = "根目录"
                    
                    if folder_name == category:
                        filtered_files.append(p)
                except:
                    if category == "其他":
                        filtered_files.append(p)

        # Build Options
        options = []
        for voice in filtered_files:
            vp = str(voice.absolute())
            try:
                rel_path = voice.relative_to(voice_folder)
                if str(rel_path.parent) == ".":
                    display_base = voice.stem
                else:
                    display_base = f"{rel_path.parent.name}/{voice.stem}"
            except:
                display_base = voice.stem
                
            name = custom_names.get(vp, display_base)
            
            # Mark analyzed/selected voices
            if hasattr(self, 'voice_library_selected') and vp in self.voice_library_selected:
                name = f"★ {name}"
                
            dur = self.get_audio_duration_seconds(vp)
            ds = self.format_duration(dur)
            display = f"{name} ({ds})" if ds else name
            options.append(ft.dropdown.Option(vp, display))
            
        target_dropdown.options = options
        
        # Reset value if current value is not in new options
        if target_dropdown.value:
            if not any(o.key == target_dropdown.value for o in options):
                 target_dropdown.value = options[0].key if options else None
        else:
             target_dropdown.value = options[0].key if options else None

    def create_voice_dropdown(self):
        """创建音色选择下拉框"""
        self.voice_dropdown = ft.Dropdown(width=300, options=[], hint_text="请选择音色文件", text_size=12, content_padding=ft.padding.symmetric(horizontal=8, vertical=6))
        return self.voice_dropdown

    def create_subtitle_voice_dropdown(self):
        """创建字幕界面用的音色下拉框"""
        self.subtitle_voice_dropdown = ft.Dropdown(width=300, options=[], hint_text="请选择音色文件", on_change=self.on_subtitle_voice_change, text_size=12, content_padding=ft.padding.symmetric(horizontal=8, vertical=6))
        return self.subtitle_voice_dropdown

    def on_subtitle_voice_change(self, e):
        """字幕界面音色选择变更时更新 selected_voice"""
        try:
            self.selected_voice = self.subtitle_voice_dropdown.value
            if not self.selected_voice:
                return
            self.show_message("已选择音色: " + Path(self.selected_voice).stem)
        except Exception as ex:
            self.log_message(f"更新字幕音色选择失败: {ex}")
        
    def create_text_input(self):
        """创建文本输入框"""
        self.text_input = ft.TextField(
            multiline=True,
            min_lines=15,
            max_lines=None,
            expand=True,
            hint_text="请输入要合成的文本内容...",
            border=ft.InputBorder.OUTLINE,
        )
        return self.text_input

    def create_synthesis_status_text(self):
        """创建语音合成状态文本"""
        self.synthesis_status_text = ft.Text(
            "等待生成",
            size=14,
            color=ft.Colors.GREY_600,
        )
        return self.synthesis_status_text

    def create_synthesis_file_text(self):
        """创建语音合成文件文本"""
        self.synthesis_file_text = ft.Text(
            "无",
            size=14,
            color=ft.Colors.GREY_600,
        )
        return self.synthesis_file_text

    def create_synthesis_time_text(self):
        """创建语音合成时间文本"""
        self.synthesis_time_text = ft.Text(
            "无",
            size=14,
            color=ft.Colors.GREY_600,
        )
        return self.synthesis_time_text

    def update_synthesis_status(self, status, file_path=None, duration=None):
        """更新语音合成状态显示"""
        try:
            # 更新状态
            if status == "生成成功":
                self.synthesis_status_text.value = status
                self.synthesis_status_text.color = ft.Colors.GREEN_600
            elif status == "生成中":
                self.synthesis_status_text.value = status
                self.synthesis_status_text.color = ft.Colors.BLUE_600
            elif status == "生成失败":
                self.synthesis_status_text.value = status
                self.synthesis_status_text.color = ft.Colors.RED_600
            else:
                self.synthesis_status_text.value = status
                self.synthesis_status_text.color = ft.Colors.GREY_600
            
            # 更新文件路径
            if file_path:
                file_name = os.path.basename(file_path)
                self.synthesis_file_text.value = file_name
                self.synthesis_file_text.color = ft.Colors.BLUE_600
            
            # 更新生成时间
            if duration:
                current_time = datetime.now().strftime("%H:%M:%S")
                self.synthesis_time_text.value = f"{current_time} (耗时: {duration:.2f}s)"
                self.synthesis_time_text.color = ft.Colors.GREEN_600
            
            # 刷新页面
            if hasattr(self, 'page') and self.page:
                self.page.update()
                
        except Exception as e:
            self.log_manager.error(f"更新语音合成状态失败: {e}")
        
    def create_status_table(self):
        """创建状态表格"""
        self.status_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("端口", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("状态", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("设备模式", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("PID", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("启动时间", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("操作", weight=ft.FontWeight.BOLD)),
            ],
            rows=[],
            border=ft.border.all(1, ft.Colors.OUTLINE),
            border_radius=8,
            vertical_lines=ft.BorderSide(1, ft.Colors.OUTLINE),
            horizontal_lines=ft.BorderSide(1, ft.Colors.OUTLINE),
        )
        
        return ft.Container(
            content=self.status_table,
            border=ft.border.all(1, ft.Colors.OUTLINE),
            border_radius=8,
            padding=10,
        )
        
    def create_detailed_status_table(self):
        """创建详细状态表格"""
        return ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("端口", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("状态", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("PID", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("启动时间", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("最后活动", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("操作", weight=ft.FontWeight.BOLD)),
            ],
            rows=[],
            border=ft.border.all(1, ft.Colors.OUTLINE),
            border_radius=8,
        )
        
    def on_nav_change(self, e):
        """导航栏切换事件，实现状态保持"""
        selected_index = e.control.selected_index
        
        # 保存当前视图到缓存
        if self.current_view is not None and hasattr(self, 'main_content') and self.main_content.content:
            self.cached_views[self.current_view] = self.main_content.content
        
        # 获取或创建目标视图
        if selected_index in self.cached_views:
            # 使用缓存的视图
            target_view = self.cached_views[selected_index]
        else:
            # 创建新视图
            def on_scan_done():
                """扫描完成回调"""
                if not hasattr(self, 'page') or not self.page:
                    return
                    
                # 更新已缓存的视图，确保下次切换回来时显示最新内容
                try:
                    if 3 in self.cached_views:
                        self.cached_views[3] = self.create_voice_library_view()
                    if 4 in self.cached_views:
                        self.cached_views[4] = self.create_subtitle_generation_view()
                    if 5 in self.cached_views:
                        self.cached_views[5] = self.create_podcast_view()
                    if 6 in self.cached_views:
                        self.cached_views[6] = self.create_bulk_generation_view()
                except:
                    pass
                    
                # 如果当前显示的视图就是更新的视图，立即刷新界面
                if self.current_view in [3, 4, 5, 6] and self.current_view in self.cached_views:
                    self.main_content.content = self.cached_views[self.current_view]
                
                # 刷新页面
                try: self.page.update() 
                except: pass

            if selected_index == 0:  # 控制台
                target_view = self.create_dashboard_view()
                self.refresh_status()
            elif selected_index == 1:  # 语音合成
                target_view = self.create_voice_synthesis_view()
                # 在切换到语音合成界面时自动刷新音色列表
                self.scan_voice_files(on_complete=on_scan_done)
                self.log_message("已自动刷新音色列表")
            elif selected_index == 2:  # 字幕生成 (ASR)
                target_view = self.create_asr_view()
            elif selected_index == 3:  # 音色库
                target_view = self.create_voice_library_view()
                self.scan_voice_files(on_complete=on_scan_done)
            elif selected_index == 4:  # 多角色配音字幕
                target_view = self.create_subtitle_generation_view()
                self.scan_voice_files(on_complete=on_scan_done)
            elif selected_index == 5:  # 播客生成
                target_view = self.create_podcast_view()
                self.scan_voice_files(on_complete=on_scan_done)
            elif selected_index == 6:  # 批量生成
                target_view = self.create_bulk_generation_view()
                self.scan_voice_files(on_complete=on_scan_done)
            elif selected_index == 7:  # 生成记录
                target_view = self.create_generation_history_view()
            elif selected_index == 8:  # 控制台输出
                target_view = self.create_console_output_view()
            else:
                return
            
            # 缓存新创建的视图
            self.cached_views[selected_index] = target_view
        
        # 更新当前视图
        self.current_view = selected_index
        self.main_content.content = target_view
        self.page.update()
        
    def show_message(self, message, is_error=False):
        """显示消息"""
        try:
            if hasattr(self, 'snack_bar') and self.snack_bar and hasattr(self, 'page') and self.page:
                self.snack_bar.content = ft.Text(message)
                self.snack_bar.bgcolor = ft.Colors.RED if is_error else ft.Colors.GREEN
                self.snack_bar.open = True
                self.page.update()
            else:
                # 如果UI未初始化，使用日志记录
                if is_error:
                    self.log_manager.error(f"消息: {message}")
                else:
                    self.log_manager.info(f"消息: {message}")
        except Exception as e:
            # 如果显示消息失败，至少记录到日志
            self.log_manager.error(f"显示消息失败: {e}, 原消息: {message}")
    
    def show_settings_dialog(self, e):
        """显示设置对话框"""
        # 主题设置，从配置文件加载
        theme_dropdown = ft.Dropdown(
            label="主题模式",
            value=self.config_manager.get("theme", "system"),
            options=[
                ft.dropdown.Option("system", "跟随系统"),
                ft.dropdown.Option("light", "浅色主题"),
                ft.dropdown.Option("dark", "深色主题"),
            ],
            width=200
        )
        
        # 默认端口范围设置，从配置文件加载
        start_port_field = ft.TextField(
            label="起始端口",
            value=str(self.config_manager.get("start_port", "7860")),
            width=120,
            keyboard_type=ft.KeyboardType.NUMBER
        )
        
        end_port_field = ft.TextField(
            label="结束端口", 
            value=str(self.config_manager.get("end_port", "7869")),
            width=120,
            keyboard_type=ft.KeyboardType.NUMBER
        )
        
        # 默认设备模式，从配置文件加载
        device_mode_dropdown = ft.Dropdown(
            label="默认设备模式",
            value=self.config_manager.get("device_mode", "auto"),
            options=[
                ft.dropdown.Option("auto", "自动"),
                ft.dropdown.Option("cpu", "CPU"),
                ft.dropdown.Option("cuda", "CUDA"),
            ],
            width=200
        )
        
        # 日志级别设置，从配置文件加载
        log_level_dropdown = ft.Dropdown(
            label="日志级别",
            value=self.config_manager.get("log_level", "INFO"),
            options=[
                ft.dropdown.Option("DEBUG", "调试"),
                ft.dropdown.Option("INFO", "信息"),
                ft.dropdown.Option("WARNING", "警告"),
                ft.dropdown.Option("ERROR", "错误"),
            ],
            width=200
        )

        # MP3保存设置，从配置文件加载
        save_mp3_switch = ft.Switch(
            label="仅保存为MP3格式 (不保留WAV)",
            value=self.config_manager.get("save_mp3", False),
            width=300
        )
        
        # 自动刷新间隔，从配置文件加载
        refresh_interval_field = ft.TextField(
            label="状态刷新间隔(秒)",
            value=str(self.config_manager.get("refresh_interval", "5")),
            width=150,
            keyboard_type=ft.KeyboardType.NUMBER
        )
        
        # 界面字体大小，从配置文件加载
        font_size_slider = ft.Slider(
            min=10,
            max=20,
            divisions=10,
            value=float(self.config_manager.get("font_size", 14)),
            label="界面字体大小: {value}px",
            width=300
        )
        
        # 音频间隔设置，从配置文件加载
        audio_interval_slider = ft.Slider(
            min=0,
            max=1000,
            divisions=20,
            value=float(self.config_manager.get("audio_interval", 100)),
            label="音频间隔: {value}ms",
            width=300
        )

        speaking_speed_value_text = ft.Text(f"{float(self.config_manager.get('speaking_speed', 1.0)):.1f}x", size=12)
        def on_speaking_speed_change(e):
            try:
                self.config_manager.set("speaking_speed", e.control.value)
                speaking_speed_value_text.value = f"{float(e.control.value):.1f}x"
                if hasattr(self, 'page') and self.page:
                    self.page.update()
            except Exception:
                pass
        speaking_speed_slider = ft.Slider(
            min=0.1,
            max=2.0,
            divisions=19,
            value=float(self.config_manager.get("speaking_speed", 1.0)),
            label="",
            on_change=on_speaking_speed_change,
            width=300
        )

        volume_value_text = ft.Text(f"{int(self.config_manager.get('volume_percent', 100))}%", size=12)
        def on_volume_change(e):
            try:
                v = int(e.control.value)
                self.config_manager.set("volume_percent", v)
                volume_value_text.value = f"{v}%"
                if hasattr(self, 'page') and self.page:
                    self.page.update()
            except Exception:
                pass
        volume_slider = ft.Slider(
            min=50,
            max=200,
            divisions=150,
            value=float(self.config_manager.get("volume_percent", 100)),
            label="",
            on_change=on_volume_change,
            width=300
        )

        # TTS 接口设置
        tts_api_mode_dropdown = ft.Dropdown(
            label="接口模式",
            value=self.config_manager.get("tts_api_mode", "local"),
            options=[
                ft.dropdown.Option("local", "本地实例"),
                ft.dropdown.Option("remote", "远程API"),
            ],
            width=200
        )
        tts_remote_base_url_field = ft.TextField(
            label="远程API地址",
            value=self.config_manager.get("tts_remote_base_url", ""),
            width=300,
            hint_text="示例: http://127.0.0.1:7860 或 https://your-space.gradio.app"
        )
        
        # AI配置设置，从配置文件加载
        ai_enabled_switch = ft.Switch(
            label="启用AI角色识别",
            value=self.config_manager.get("ai_enabled", False),
            width=200
        )
        ai_adjust_speed_switch = ft.Switch(
            label="AI调整语速",
            value=bool(self.config_manager.get("ai_adjust_speed", False)),
            width=200
        )
        ai_adjust_emotion_switch = ft.Switch(
            label="AI调整情感向量",
            value=bool(self.config_manager.get("ai_adjust_emotion", True)),
            width=200
        )
        
        ai_api_key_field = ft.TextField(
            label="API Key",
            value=self.config_manager.get("ai_api_key", ""),
            width=300,
            password=True,
            can_reveal_password=True,
            hint_text="输入您的AI服务API密钥"
        )
        
        ai_base_url_field = ft.TextField(
            label="Base URL",
            value=self.config_manager.get("ai_base_url", "https://api.openai.com"),
            width=300,
            hint_text="云端示例: https://api.openai.com；本地示例: http://localhost:11434 (Ollama)"
        )
        ai_api_url_mode_dropdown = ft.Dropdown(
            label="AI接口模式",
            value=self.config_manager.get("ai_api_url_mode", "default"),
            options=[
                ft.dropdown.Option("default", "默认(v1)"),
                ft.dropdown.Option("custom", "自定义")
            ],
            width=200
        )
        ai_custom_base_url_field = ft.TextField(
            label="自定义 Base URL",
            value=self.config_manager.get("ai_custom_base_url", ""),
            width=300,
            hint_text="示例: https://your-api.example.com/v4 或 https://xxx/v1"
        )
        def on_ai_mode_change(e):
            m = ai_api_url_mode_dropdown.value
            ai_custom_base_url_field.visible = (m == "custom")
            ai_base_url_field.visible = (m != "custom")
            if hasattr(self, 'page') and self.page:
                self.page.update()
        ai_api_url_mode_dropdown.on_change = on_ai_mode_change
        _m = self.config_manager.get("ai_api_url_mode", "default")
        ai_custom_base_url_field.visible = (_m == "custom")
        ai_base_url_field.visible = (_m != "custom")
        
        ai_model_field = ft.TextField(
            label="模型名称",
            value=self.config_manager.get("ai_model", "gpt-3.5-turbo"),
            width=300,
            hint_text="使用的AI模型名称"
        )
        
        ai_temperature_slider = ft.Slider(
            min=0.0,
            max=2.0,
            divisions=20,
            value=float(self.config_manager.get("ai_temperature", 0.7)),
            label="AI创造性: {value}",
            width=300
        )
        
        ai_max_tokens_field = ft.TextField(
            label="最大Token数",
            value=str(self.config_manager.get("ai_max_tokens", "1000")),
            width=150,
            keyboard_type=ft.KeyboardType.NUMBER,
            hint_text="AI响应的最大长度"
        )
        ai_seg_min_cn_field = ft.TextField(
            label="AI分段最少汉字",
            value=str(self.config_manager.get("ai_seg_min_cn", "5")),
            width=120,
            keyboard_type=ft.KeyboardType.NUMBER,
            hint_text="如 5"
        )
        ai_seg_max_cn_field = ft.TextField(
            label="AI分段最多汉字",
            value=str(self.config_manager.get("ai_seg_max_cn", "25")),
            width=120,
            keyboard_type=ft.KeyboardType.NUMBER,
            hint_text="如 25"
        )
        
        # 自动更新设置
        update_url_field = ft.TextField(
            label="更新源地址 (Update URL)",
            value=self.config_manager.get("update_url", ""),
            width=300,
            hint_text="e.g. http://myserver.com/updates"
        )
        check_update_btn = ft.ElevatedButton(
            "检查更新",
            icon=ft.Icons.UPDATE,
            on_click=self.check_for_updates
        )
        
        def save_settings(e):
            """保存设置"""
            try:
                # 保存主题设置到配置文件
                self.config_manager.set("theme", (theme_dropdown.value or "").strip())
                
                # 应用主题设置
                if theme_dropdown.value == "system":
                    self.page.theme_mode = ft.ThemeMode.SYSTEM
                elif theme_dropdown.value == "light":
                    self.page.theme_mode = ft.ThemeMode.LIGHT
                elif theme_dropdown.value == "dark":
                    self.page.theme_mode = ft.ThemeMode.DARK
                
                # 保存日志级别到配置文件
                self.config_manager.set("log_level", (log_level_dropdown.value or "").strip())
                
                # 保存MP3设置
                self.config_manager.set("save_mp3", save_mp3_switch.value)

                # 应用日志级别
                level_map = {
                    "DEBUG": logging.DEBUG,
                    "INFO": logging.INFO,
                    "WARNING": logging.WARNING,
                    "ERROR": logging.ERROR
                }
                if log_level_dropdown.value in level_map:
                    self.log_manager.set_log_level(level_map[log_level_dropdown.value])
                
                # 保存其他设置到配置文件
                self.config_manager.set("start_port", (start_port_field.value or "").strip())
                self.config_manager.set("end_port", (end_port_field.value or "").strip())
                self.config_manager.set("device_mode", (device_mode_dropdown.value or "").strip())
                self.config_manager.set("refresh_interval", refresh_interval_field.value)
                self.config_manager.set("font_size", font_size_slider.value)
                self.config_manager.set("audio_interval", audio_interval_slider.value)
                self.config_manager.set("speaking_speed", speaking_speed_slider.value)

                # 保存 TTS 接口配置
                self.config_manager.set("tts_api_mode", (tts_api_mode_dropdown.value or "").strip())
                _tts_remote = (tts_remote_base_url_field.value or "").strip().replace("\r","" ).replace("\n","" )
                self.config_manager.set("tts_remote_base_url", _tts_remote)
                
                # 保存AI配置到配置文件
                self.config_manager.set("ai_enabled", bool(ai_enabled_switch.value))
                _api_key = (ai_api_key_field.value or "").strip().replace("\r","" ).replace("\n","" )
                _api_key = "".join(_api_key.split())
                _base_url = (ai_base_url_field.value or "").strip().replace("\r","" ).replace("\n","" )
                _api_mode = (ai_api_url_mode_dropdown.value or "").strip()
                _custom_base = (ai_custom_base_url_field.value or "").strip().replace("\r","" ).replace("\n","" )
                _model = (ai_model_field.value or "").strip().replace("\r","" ).replace("\n","" )
                _model = "".join(_model.split())
                self.config_manager.set("ai_api_key", _api_key)
                self.config_manager.set("ai_base_url", _base_url)
                self.config_manager.set("ai_api_url_mode", _api_mode)
                self.config_manager.set("ai_custom_base_url", _custom_base)
                self.config_manager.set("ai_model", _model)
                self.config_manager.set("ai_temperature", ai_temperature_slider.value)
                self.config_manager.set("ai_max_tokens", ai_max_tokens_field.value)
                self.config_manager.set("ai_adjust_speed", ai_adjust_speed_switch.value)
                self.config_manager.set("ai_adjust_emotion", ai_adjust_emotion_switch.value)
                self.config_manager.set("update_url", (update_url_field.value or "").strip())
                try:
                    self.config_manager.set("ai_seg_min_cn", int(ai_seg_min_cn_field.value))
                    self.config_manager.set("ai_seg_max_cn", int(ai_seg_max_cn_field.value))
                except Exception:
                    pass
                
                # 保存配置文件
                self.config_manager.save()
                
                self.page.update()
                self.show_message("设置已保存到配置文件")
                settings_dialog.open = False
                self.page.update()
                
                self.log_manager.info(f"设置已保存: 主题={theme_dropdown.value}, 日志级别={log_level_dropdown.value}")
                
            except Exception as ex:
                self.show_message(f"保存设置失败: {str(ex)}", True)
                self.log_manager.error(f"保存设置失败: {ex}")
        
        def close_dialog(e):
            """关闭对话框"""
            settings_dialog.open = False
            self.page.update()
        
        # 创建设置对话框
        settings_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("应用设置", size=18, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column([
                    # 外观设置
                    ft.Card(
                        content=ft.Container(
                            content=ft.Column([
                                ft.ListTile(
                                    leading=ft.Icon(ft.Icons.PALETTE, color=ft.Colors.BLUE),
                                    title=ft.Text("外观设置", weight=ft.FontWeight.BOLD),
                                ),
                                ft.Divider(height=1),
                                ft.Row([theme_dropdown], spacing=10),
                                ft.Row([
                                    ft.Text("字体大小:", size=12),
                                    font_size_slider
                                ], spacing=10),
                                ft.Row([
                                    ft.Text("音频间隔:", size=12),
                                    audio_interval_slider
                                ], spacing=10),
                                ft.Row([
                                    ft.Text("语速:", size=12),
                                    speaking_speed_slider,
                                    speaking_speed_value_text,
                                ], spacing=10),
                                ft.Row([
                                    ft.Text("音量:", size=12),
                                    volume_slider,
                                    volume_value_text,
                                ], spacing=10),
                            ], spacing=10),
                            padding=15,
                        ),
                        elevation=1,
                    ),
                    
                    # 默认参数设置
                    ft.Card(
                        content=ft.Container(
                            content=ft.Column([
                                ft.ListTile(
                                    leading=ft.Icon(ft.Icons.SETTINGS, color=ft.Colors.GREEN),
                                    title=ft.Text("默认参数", weight=ft.FontWeight.BOLD),
                                ),
                                ft.Divider(height=1),
                                ft.Row([
                                    ft.Text("端口范围:", size=12, width=80),
                                    start_port_field,
                                    ft.Text("-", size=12),
                                    end_port_field,
                                ], spacing=10),
                                ft.Row([device_mode_dropdown], spacing=10),
                                ft.Row([refresh_interval_field], spacing=10),
                            ], spacing=10),
                            padding=15,
                        ),
                        elevation=1,
                    ),

                    # TTS 接口设置
                    ft.Card(
                        content=ft.Container(
                            content=ft.Column([
                                ft.ListTile(
                                    leading=ft.Icon(ft.Icons.LINK, color=ft.Colors.BLUE_GREY),
                                    title=ft.Text("TTS 接口设置", weight=ft.FontWeight.BOLD),
                                ),
                                ft.Divider(height=1),
                                ft.Row([tts_api_mode_dropdown], spacing=10),
                                ft.Row([tts_remote_base_url_field], spacing=10),
                                ft.Container(
                                    content=ft.Text(
                                        "说明：远程API模式将直接调用远端的 /update_prompt_audio 与 /gen_single 接口，无需本地实例。",
                                        size=11,
                                        color=ft.Colors.GREY_600,
                                        italic=True,
                                    ),
                                    padding=ft.padding.only(top=6),
                                ),
                            ], spacing=10),
                            padding=15,
                        ),
                        elevation=1,
                    ),
                    
                    # 高级设置
                    ft.Card(
                        content=ft.Container(
                            content=ft.Column([
                                ft.ListTile(
                                    leading=ft.Icon(ft.Icons.TUNE, color=ft.Colors.ORANGE),
                                    title=ft.Text("高级设置", weight=ft.FontWeight.BOLD),
                                ),
                                ft.Divider(height=1),
                                ft.Row([log_level_dropdown], spacing=10),
                                ft.Row([save_mp3_switch], spacing=10),
                            ], spacing=10),
                            padding=15,
                        ),
                        elevation=1,
                    ),
                    
                    # AI配置设置
                    ft.Card(
                        content=ft.Container(
                            content=ft.Column([
                                ft.ListTile(
                                    leading=ft.Icon(ft.Icons.SMART_TOY, color=ft.Colors.PURPLE),
                                    title=ft.Text("AI角色识别配置", weight=ft.FontWeight.BOLD),
                                ),
                                ft.Divider(height=1),
                                ft.Row([ai_enabled_switch], spacing=10),
                                ft.Row([ai_api_key_field], spacing=10),
                                ft.Row([ai_api_url_mode_dropdown], spacing=10),
                                ft.Row([ai_base_url_field], spacing=10),
                                ft.Row([ai_custom_base_url_field], spacing=10),
                                ft.Row([ai_model_field], spacing=10),
                                ft.Row([
                                    ft.Text("创造性:", size=12, width=80),
                                    ai_temperature_slider
                                ], spacing=10),
                                ft.Row([ai_max_tokens_field], spacing=10),
                                ft.Row([ai_seg_min_cn_field, ai_seg_max_cn_field], spacing=10),
                                ft.Row([ai_adjust_speed_switch, ai_adjust_emotion_switch], spacing=10),
                                ft.Container(
                                    content=ft.Text(
                                        "💡 提示：启用AI角色识别后，系统将自动分析文本中的角色并分配合适的音色。\n"
                                        "使用本地AI时，API Key可留空；使用云端服务需填写Key。\n"
                                        "当接口为 /v4 或其他版本时，请选择‘自定义’，并在‘自定义 Base URL’中填写包含版本的地址，例如：https://your-api.example.com/v4。",
                                        size=11,
                                        color=ft.Colors.GREY_600,
                                        italic=True
                                    ),
                                    padding=ft.padding.only(top=10),
                                ),
                            ], spacing=10),
                            padding=15,
                        ),
                        elevation=1,
                    ),
                    
                    # 自动更新
                    ft.Card(
                        content=ft.Container(
                            content=ft.Column([
                                ft.ListTile(
                                    leading=ft.Icon(ft.Icons.SYSTEM_UPDATE, color=ft.Colors.TEAL),
                                    title=ft.Text("自动更新", weight=ft.FontWeight.BOLD),
                                ),
                                ft.Divider(height=1),
                                ft.Row([update_url_field], spacing=10),
                                ft.Row([check_update_btn], spacing=10),
                                ft.Container(
                                    content=ft.Text(
                                        f"当前版本: {self.app_version}\n"
                                        "配置更新源地址后，点击检查更新可在线升级。",
                                        size=11,
                                        color=ft.Colors.GREY_600,
                                        italic=True
                                    ),
                                    padding=ft.padding.only(top=6),
                                ),
                            ], spacing=10),
                            padding=15,
                        ),
                        elevation=1,
                    ),
                ], spacing=15, scroll=ft.ScrollMode.AUTO),
                width=500,
                height=650,
            ),
            actions=[
                ft.TextButton("取消", on_click=close_dialog),
                ft.ElevatedButton("保存设置", on_click=save_settings),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        self.page.overlay.append(settings_dialog)
        settings_dialog.open = True
        self.page.update()
    
    def on_window_event(self, e):
        """窗口事件处理"""
        if e.data == "close":
            self.log_manager.info("检测到窗口关闭事件，开始清理...")
            self.cleanup_on_exit()
        
    def toggle_debug_mode(self, e):
        """切换调试模式"""
        self.debug_mode = e.control.value
        status_text = "开启" if self.debug_mode else "关闭"
        self.log_message(f"调试模式已{status_text}")
        self.show_message(f"调试模式已{status_text}")
        
    def on_log_level_change(self, e):
        """切换日志级别"""
        if hasattr(self, 'log_manager') and self.log_manager:
            level_map = {
                "DEBUG": logging.DEBUG,
                "INFO": logging.INFO,
                "WARNING": logging.WARNING,
                "ERROR": logging.ERROR,
                "CRITICAL": logging.CRITICAL
            }
            new_level = level_map.get(e.control.value, logging.INFO)
            self.log_manager.set_log_level(new_level)
            self.log_message(f"日志级别已切换为: {e.control.value}", "INFO")
            self.show_message(f"日志级别已切换为: {e.control.value}")
        
    def log_message(self, message, level="INFO"):
        """记录日志消息（兼容旧版本的方法）"""
        # 使用新的日志管理器
        if hasattr(self, 'log_manager'):
            if level.upper() == "DEBUG":
                self.log_manager.debug(message)
            elif level.upper() == "WARNING":
                self.log_manager.warning(message)
            elif level.upper() == "ERROR":
                self.log_manager.error(message)
            elif level.upper() == "CRITICAL":
                self.log_manager.critical(message)
            else:
                self.log_manager.info(message)
        else:
            # 如果日志管理器不存在，回退到原有方式
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_entry = f"[{timestamp}] {message}"
            print(log_entry)
            
            # 如果控制台输出组件存在，也更新到GUI
            if hasattr(self, 'console_output') and self.console_output:
                try:
                    current_text = self.console_output.value or ""
                    new_text = current_text + log_entry + "\n"
                    
                    # 限制行数
                    lines = new_text.split('\n')
                    if len(lines) > 1000:
                        new_text = '\n'.join(lines[-1000:])
                        
                    self.console_output.value = new_text
                    if self.page:
                        self.page.update()
                except Exception as e:
                    print(f"更新GUI日志失败: {e}")
        
    def update_voice_category_options(self, category_dropdown, target_dropdown):
        """更新分类下拉框选项并联动更新目标下拉框"""
        if not hasattr(self, 'voice_files') or not category_dropdown:
            return

        voice_folder = Path("yinse")
        categories = set()
        
        for p in self.voice_files:
            try:
                rel = p.relative_to(voice_folder)
                folder = rel.parent
                if str(folder) == ".":
                    categories.add("根目录")
                else:
                    categories.add(str(folder))
            except:
                categories.add("其他")
        
        sorted_categories = sorted(list(categories))
        sorted_categories.insert(0, "全部")
        sorted_categories.insert(1, "已选(AI候选)")
        
        # 更新选项
        category_dropdown.options = [ft.dropdown.Option(c) for c in sorted_categories]
        
        # 保持选中值有效性
        if category_dropdown.value not in sorted_categories:
            category_dropdown.value = "全部"
            
        # 触发目标下拉框更新
        if target_dropdown:
            self.update_voice_dropdown_options(target_dropdown, category_dropdown.value)

    def refresh_voice_selectors(self):
        """刷新所有带分类筛选的音色选择器"""
        selectors = [
            ('voice_category_dropdown', 'voice_dropdown'),
            ('subtitle_voice_category_dropdown', 'subtitle_voice_dropdown'),
            ('podcast_voice_a_category_dropdown', 'podcast_voice_a_dropdown'),
            ('podcast_voice_b_category_dropdown', 'podcast_voice_b_dropdown'),
            ('podcast_voice_c_category_dropdown', 'podcast_voice_c_dropdown'),
            ('podcast_voice_d_category_dropdown', 'podcast_voice_d_dropdown')
        ]
        
        for cat_attr, target_attr in selectors:
            cat_dd = getattr(self, cat_attr, None)
            target_dd = getattr(self, target_attr, None)
            if cat_dd and target_dd:
                self.update_voice_category_options(cat_dd, target_dd)

    # 以下是业务逻辑方法，保持与原版本相同的功能
    def scan_voice_files(self, on_complete=None):
        """扫描音色文件（异步包装）"""
        if getattr(self, '_is_scanning', False):
            return
        self._is_scanning = True
        threading.Thread(target=self._scan_voice_files_impl, args=(on_complete,), daemon=True).start()

    def _scan_voice_files_impl(self, on_complete=None):
        """扫描音色文件（实际逻辑）"""
        try:
            voice_folder = Path("yinse")
            if not voice_folder.exists():
                self.log_message("音色文件夹 'yinse' 不存在")
                self.available_voices = []
                return
            
            # 支持多种音频格式
            supported_exts = {".wav", ".mp3", ".wma", ".flac", ".ogg", ".m4a", ".aac", ".opus"}
            voice_files = []
            
            # 递归扫描
            try:
                for root, dirs, files in os.walk(voice_folder):
                    for file in files:
                        if Path(file).suffix.lower() in supported_exts:
                            voice_files.append(Path(root) / file)
            except Exception as e:
                self.log_message(f"扫描音色文件出错: {e}")

            # 去重并排序（按相对路径）
            try:
                self.voice_files = sorted(voice_files, key=lambda p: str(p.relative_to(voice_folder)).lower())
            except Exception:
                self.voice_files = sorted(voice_files, key=lambda p: p.name.lower())
                
            self.log_message(f"发现 {len(self.voice_files)} 个音色文件")
            
            # 设置 available_voices 属性 - 使用 stem
            self.available_voices = [voice.stem for voice in self.voice_files]
            
            # 自定义名称映射
            custom_names = self.config_manager.get("voice_custom_names", {}) or {}
            # 刷新所有带分类筛选的音色选择器
            self.refresh_voice_selectors()
            
            # 更新 selected_voice
            if getattr(self, 'subtitle_voice_dropdown', None) and self.subtitle_voice_dropdown.value:
                self.selected_voice = self.subtitle_voice_dropdown.value

            # 刷新音色库视图（如果存在）
            try:
                if hasattr(self, 'voice_library_list') and self.voice_library_list:
                    self.refresh_voice_library()
            except Exception:
                pass

            if hasattr(self, 'page') and self.page:
                self.page.update()
                
        except Exception as e:
            self.log_message(f"扫描音色文件执行出错: {e}")
        finally:
            self._is_scanning = False
            if on_complete:
                try:
                    on_complete()
                except Exception:
                    pass
            
    def refresh_voices(self, e=None):
        """刷新音色列表"""
        def on_done():
            self.show_message("音色列表已刷新")
        self.scan_voice_files(on_complete=on_done)

    def get_audio_duration_seconds(self, path: str):
        try:
            import mutagen
            f = mutagen.File(path)
            info = getattr(f, 'info', None)
            length = getattr(info, 'length', None)
            if length:
                return float(length)
        except Exception:
            pass
        try:
            if path.lower().endswith('.wav'):
                import wave
                with wave.open(path, 'rb') as w:
                    frames = w.getnframes()
                    rate = w.getframerate()
                    if rate:
                        return float(frames) / float(rate)
        except Exception:
            pass
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            snd = pygame.mixer.Sound(path)
            return float(getattr(snd, 'get_length', lambda: 0.0)())
        except Exception:
            pass
        return None

    def format_duration(self, seconds: float | None):
        try:
            if not seconds or seconds <= 0:
                return ""
            m = int(seconds) // 60
            s = int(seconds) % 60
            return f"{m:02d}:{s:02d}"
        except Exception:
            return ""

    def write_simple_srt_from_text(self, audio_path: str, text: str):
        try:
            dur = self.get_audio_duration_seconds(audio_path) or 0.0
            def fmt_srt_time(sec: float):
                try:
                    if sec < 0:
                        sec = 0.0
                    h = int(sec // 3600)
                    m = int((sec % 3600) // 60)
                    s = int(sec % 60)
                    ms = int((sec - int(sec)) * 1000)
                    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
                except Exception:
                    return "00:00:00,000"
            srt_path = os.path.splitext(audio_path)[0] + ".srt"
            with open(srt_path, 'w', encoding='utf-8') as f:
                f.write("1\n")
                f.write(f"00:00:00,000 --> {fmt_srt_time(float(dur))}\n")
                f.write((text or "").strip() + "\n\n")
            return srt_path
        except Exception:
            return None

    def resolve_voice_path_any(self, val: str | None) -> str | None:
        try:
            v = (val or '').strip()
            if not v:
                return None
            if os.path.isabs(v) and os.path.exists(v):
                return v
            nm = v.split('(')[0].strip()
            for p in getattr(self, 'voice_files', []) or []:
                if p and (p.name == nm or p.stem == nm or os.path.basename(str(p)) == nm):
                    return str(p.absolute())
            return None
        except Exception:
            return None
        
    def start_instances(self, e=None):
        """启动实例"""
        try:
            # 检查是否已有实例运行
            if self.instances:
                self.show_message("已有实例正在运行", True)
                return
            
            # 获取自定义端口
            try:
                custom_port = int(self.custom_port_field.value)
                if not (1024 <= custom_port <= 65535):
                    self.show_message("端口号必须在1024-65535范围内", True)
                    return
                port = custom_port
            except (ValueError, AttributeError):
                port = self.base_port
                self.show_message(f"使用默认端口: {port}")
            
            # 获取设备模式
            device_mode = self.device_mode_dropdown.value if self.device_mode_dropdown else "auto"
            
            self.log_message(f"开始启动IndexTTS2实例 - 端口: {port}, 设备模式: {device_mode}")
            
            # 立即更新状态显示为"启动中"
            self.show_message(f"正在启动实例... 端口: {port}, 设备模式: {device_mode}")
            self.refresh_status()  # 立即刷新状态表
            
            self.start_single_instance(port, device_mode)
            
            # 启动完成后再次刷新状态
            self.refresh_status()
            self.show_message(f"实例启动完成 - 端口: {port}, 设备模式: {device_mode}")
            
        except Exception as e:
            self.show_message(f"启动实例失败: {e}", True)
            # 失败时也要刷新状态
            self.refresh_status()

    def start_single_instance(self, port, device_mode="auto"):
        """启动单个实例"""
        try:
            self.log_manager.info(f"准备启动IndexTTS2实例 - 端口: {port}, 设备模式: {device_mode}")
            
            venv_pythonw = r"venv\pythonw.exe"
            venv_python = venv_pythonw if os.path.exists(venv_pythonw) else r"venv\python.exe"
            cmd = [
                venv_python, "webui.py",
                "--port", str(port),
                "--host", "127.0.0.1"
            ]
            
            # 根据设备模式添加参数
            if device_mode == "gpu":
                cmd.extend(["--device", "cuda"])
                self.log_manager.info("强制使用GPU模式启动")
            elif device_mode == "cpu":
                cmd.extend(["--device", "cpu"])
                self.log_manager.info("强制使用CPU模式启动")
            else:
                self.log_manager.info("使用自动检测设备模式启动")

            try:
                if getattr(self, 'fp16_checkbox', None) and bool(self.fp16_checkbox.value):
                    cmd.append("--fp16")
                
                if getattr(self, 'cuda_kernel_checkbox', None) and bool(self.cuda_kernel_checkbox.value):
                    cmd.append("--cuda_kernel")
                if getattr(self, 'low_vram_checkbox', None) and bool(self.low_vram_checkbox.value):
                    cmd.append("--low_vram")
                if getattr(self, 'verbose_checkbox', None) and bool(self.verbose_checkbox.value):
                    cmd.append("--verbose")
                if getattr(self, 'gui_seg_tokens_field', None):
                    try:
                        seg_tokens = int(self.gui_seg_tokens_field.value)
                        if seg_tokens > 0:
                            cmd.extend(["--gui_seg_tokens", str(seg_tokens)])
                    except Exception:
                        pass
            except Exception:
                pass
            
            # 记录详细的启动参数信息
            self.log_manager.info("=" * 50)
            self.log_manager.info("启动参数详情:")
            self.log_manager.info(f"  端口号: {port}")
            self.log_manager.info(f"  主机地址: 127.0.0.1")
            self.log_manager.info(f"  设备模式: {device_mode}")
            self.log_manager.info(f"  启动命令: {' '.join(cmd)}")
            self.log_manager.info(f"  工作目录: {os.getcwd()}")
            self.log_manager.info(f"  启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self.log_manager.info("=" * 50)
            
            env = os.environ.copy()
            env["NO_PROXY"] = "127.0.0.1,localhost"
            env["HTTP_PROXY"] = ""
            env["HTTPS_PROXY"] = ""
            try:
                if getattr(self, 'verbose_checkbox', None) and bool(self.verbose_checkbox.value):
                    env["TRANSFORMERS_VERBOSITY"] = "info"
                else:
                    env["TRANSFORMERS_VERBOSITY"] = "error"
            except Exception:
                env["TRANSFORMERS_VERBOSITY"] = "error"
            env["TOKENIZERS_PARALLELISM"] = "false"
            env["GRADIO_ANALYTICS_ENABLED"] = "0"
            
            si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW; si.wShowWindow = 0
            cf = subprocess.CREATE_NO_WINDOW
            try:
                cf |= subprocess.DETACHED_PROCESS
            except Exception:
                pass
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=os.getcwd(),
                bufsize=1,
                universal_newlines=True,
                env=env,
                creationflags=cf,
                startupinfo=si,
            )
            
            self.instances[port] = {
                'process': process,
                'client': None,
                'status': '启动中',
                'start_time': datetime.now(),
                'last_activity': datetime.now(),
                'device_mode': device_mode
            }
            
            self.log_manager.info(f"实例启动成功 - 端口: {port}, PID: {process.pid}, 设备模式: {device_mode}")
            
            # 启动输出监控线程
            output_thread = threading.Thread(
                target=self.monitor_process_output,
                args=(port, process),
                daemon=True
            )
            output_thread.start()
            
            # 在后台线程中等待服务启动，避免阻塞UI
            self.log_manager.debug(f"启动后台线程等待服务启动 - 端口: {port}")
            wait_thread = threading.Thread(
                target=self.wait_for_service,
                args=(port,),
                daemon=True
            )
            wait_thread.start()
            
            # 更新底栏状态为“启动中”
            try:
                self.update_tts_status_bar()
            except Exception:
                pass

        except Exception as e:
            self.log_manager.error(f"启动端口 {port} 失败: {e}")
            self.log_manager.exception(f"启动端口 {port} 异常详情")
            
    def monitor_process_output(self, port, process):
        """监控进程输出的线程函数"""
        try:
            self.log_manager.info(f"开始监控端口 {port} 的输出")
            
            while True:
                # 检查进程是否还在运行
                if process.poll() is not None:
                    self.log_manager.info(f"端口 {port} 进程已结束，停止输出监控")
                    break
                
                # 读取一行输出
                line = process.stdout.readline()
                if line:
                    line = line.strip()
                    if line:  # 只处理非空行
                        # 只通过update_console_output统一处理，避免重复日志
                        if hasattr(self, 'page') and self.page:
                            try:
                                self.update_console_output(port, line)
                            except Exception as e:
                                print(f"更新UI控制台失败: {e}")
                else:
                    # 如果没有输出，稍微等待一下避免CPU占用过高
                    time.sleep(0.1)
                    
        except Exception as e:
            self.log_manager.error(f"监控端口 {port} 输出时发生错误: {e}")
            self.log_manager.exception(f"监控端口 {port} 输出异常详情")

    def update_console_output(self, port, line):
        """更新控制台输出 - 通过日志系统统一处理，避免重复"""
        try:
            suppressed = [
                "If you're using `trust_remote_code=True`",
                "inherits from `GenerationMixin`",
                "If you are not the owner of the model architecture class",
                "please contact the model code owner to update it",
            ]
            if any(x in line for x in suppressed):
                return
            # 根据消息内容确定日志级别
            if any(keyword in line.lower() for keyword in ['error', '错误', 'exception', 'failed', '失败']):
                level = 'ERROR'
            elif any(keyword in line.lower() for keyword in ['warning', '警告', 'warn']):
                level = 'WARNING'
            else:
                level = 'INFO'
            
            # 格式化消息，包含端口信息
            formatted_message = f"[端口{port}] {line}"
            
            # 通过日志系统记录，这样会自动显示在GUI中
            if level == 'ERROR':
                self.log_manager.error(formatted_message)
            elif level == 'WARNING':
                self.log_manager.warning(formatted_message)
            else:
                self.log_manager.info(formatted_message)
                
        except Exception as e:
            print(f"更新控制台输出失败: {e}")
            
    def wait_for_service(self, port):
        """等待服务启动"""
        max_wait = 280
        wait_time = 0
        
        self.log_manager.debug(f"开始等待端口 {port} 服务启动，最大等待时间: {max_wait}秒")
        
        while wait_time < max_wait:
            try:
                self.log_manager.debug(f"检测端口 {port} 服务状态 (已等待 {wait_time}秒)")
                response = requests.get(f"http://127.0.0.1:{port}/", timeout=5)
                if response.status_code == 200:
                    self.log_manager.info(f"端口 {port} HTTP服务响应正常，状态码: {response.status_code}")
                    
                    try:
                        client = Client(f"http://127.0.0.1:{port}/")
                        self.instances[port]['client'] = client
                        self.instances[port]['status'] = '运行中'
                        self.log_manager.info(f"端口 {port} Gradio客户端连接成功")
                        self.log_manager.info(f"端口 {port} 服务完全启动成功，总耗时: {wait_time}秒")
                        
                        # 使用线程安全的方式更新UI
                        def update_ui():
                            self.refresh_status()
                            # 服务就绪后更新底栏状态
                            try:
                                self.update_tts_status_bar()
                            except Exception:
                                pass
                        
                        # 在主线程中执行UI更新
                        self.page.run_thread(update_ui)
                        return
                    except Exception as client_error:
                        # 连接到 Gradio 客户端失败：即时标注为“连接失败”，避免一直显示“启动中”
                        self.log_manager.warning(f"端口 {port} Gradio客户端连接失败: {client_error}")
                        try:
                            self.instances[port]['status'] = '连接失败'
                        except Exception:
                            pass
                        # 线程安全地刷新UI状态栏与表格
                        def update_ui_conn_failed():
                            try:
                                self.refresh_status()
                            except Exception:
                                pass
                            try:
                                self.update_tts_status_bar()
                            except Exception:
                                pass
                        if hasattr(self, 'page') and self.page:
                            self.page.run_thread(update_ui_conn_failed)
                        
            except requests.exceptions.Timeout:
                self.log_manager.debug(f"端口 {port} 连接超时，继续等待...")
            except requests.exceptions.ConnectionError:
                self.log_manager.debug(f"端口 {port} 连接被拒绝，服务可能还未启动")
            except Exception as e:
                self.log_manager.debug(f"端口 {port} 检测异常: {e}")
                
            time.sleep(2)
            wait_time += 2
            
        # 服务启动超时处理
        self.instances[port]['status'] = '启动失败'
        self.log_manager.error(f"端口 {port} 服务启动超时，已等待 {max_wait} 秒")
        self.log_manager.warning(f"端口 {port} 可能存在以下问题：1) 模型加载时间过长 2) 端口被占用 3) 系统资源不足")
        
        # 检查进程是否还在运行
        if port in self.instances and self.instances[port]['process']:
            process = self.instances[port]['process']
            if process.poll() is None:
                self.log_manager.warning(f"端口 {port} 进程仍在运行 (PID: {process.pid})，但HTTP服务未响应")
            else:
                self.log_manager.error(f"端口 {port} 进程已退出，退出码: {process.returncode}")
        
        # 使用线程安全的方式更新UI
        def update_ui_timeout():
            self.refresh_status()
            # 启动失败时更新底栏状态
            try:
                self.update_tts_status_bar()
            except Exception:
                pass
        
        # 在主线程中执行UI更新
        self.page.run_thread(update_ui_timeout)
        
    def stop_all_instances(self, e=None):
        """停止所有实例"""
        for port, instance in list(self.instances.items()):
            try:
                process = instance['process']
                if process.poll() is None:
                    process.terminate()
                    self.log_message(f"停止实例 - 端口: {port}")
            except Exception as e:
                self.log_message(f"停止端口 {port} 失败: {e}")
                
        self.instances.clear()
        self.refresh_status()
        try:
            self.update_tts_status_bar()
        except Exception:
            pass
        self.show_message("所有实例已停止")
        
    def stop_single_instance(self, port):
        """停止单个实例"""
        if port in self.instances:
            try:
                process = self.instances[port]['process']
                if process.poll() is None:
                    process.terminate()
                    self.log_message(f"停止实例 - 端口: {port}")
                del self.instances[port]
                self.refresh_status()
                try:
                    self.update_tts_status_bar()
                except Exception:
                    pass
                self.show_message(f"端口 {port} 实例已停止")
            except Exception as e:
                self.log_message(f"停止端口 {port} 失败: {e}")
                self.show_message(f"停止端口 {port} 失败: {e}", is_error=True)
        
    def refresh_status(self, e=None):
        """刷新状态"""
        if not self.status_table:
            return
            
        rows = []
        for port, instance in self.instances.items():
            st = instance.get('status', '')
            if st in ('运行中', 'running'):
                status_color = ft.Colors.GREEN
            elif st in ('启动中', 'starting'):
                status_color = ft.Colors.AMBER
            elif st in ('连接失败', 'connection_failed', '启动失败', 'failed'):
                status_color = ft.Colors.RED_400
            else:
                status_color = ft.Colors.ORANGE
            
            # 创建停止按钮
            stop_button = ft.ElevatedButton(
                "停止",
                on_click=lambda e, p=port: self.stop_single_instance(p),
                bgcolor=ft.Colors.RED_400,
                color=ft.Colors.WHITE,
                height=30,
            )
            
            # 获取设备模式信息
            device_mode = instance.get('device_mode', 'auto')
            device_mode_text = {
                'auto': '自动检测',
                'gpu': 'GPU模式',
                'cpu': 'CPU模式'
            }.get(device_mode, device_mode)
            
            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(port))),
                        ft.DataCell(ft.Text(instance['status'], color=status_color)),
                        ft.DataCell(ft.Text(device_mode_text)),
                        ft.DataCell(ft.Text(str(instance['process'].pid))),
                        ft.DataCell(ft.Text(instance['start_time'].strftime("%H:%M:%S"))),
                        ft.DataCell(stop_button),
                    ]
                )
            )
            
        self.status_table.rows = rows
        
        # 同步更新底部TTS状态显示
        try:
            self.update_tts_status_bar()
        except Exception:
            pass
        
        self.page.update()

    def update_tts_status_bar(self):
        """根据实例状态动态更新底部TTS状态文案与颜色"""
        # 统计各类状态数量
        running_count = 0
        starting_count = 0
        failed_count = 0
        conn_failed_count = 0
        for info in self.instances.values():
            status = info.get('status')
            if status == '运行中' or status == 'running':
                running_count += 1
            elif status == '启动中' or status == 'starting':
                starting_count += 1
            elif status == '启动失败' or status == 'failed':
                failed_count += 1
            elif status == '连接失败' or status == 'connection_failed':
                conn_failed_count += 1

        # 选择显示状态：运行中 > 连接失败 > 启动中 > 启动失败/未启动
        if running_count > 0:
            text = f"TTS 运行中"
            color = ft.Colors.GREEN
        elif conn_failed_count > 0:
            text = f"TTS 连接失败"
            color = ft.Colors.RED_400
        elif starting_count > 0:
            text = f"TTS 启动中…"
            color = ft.Colors.AMBER
        elif failed_count > 0:
            text = f"TTS 启动失败 · 异常: {failed_count}"
            color = ft.Colors.RED_400
        else:
            text = "TTS 未启动"
            color = ft.Colors.RED_400

        # 更新控件
        if hasattr(self, 'tts_status_text') and hasattr(self, 'tts_status_icon'):
            self.tts_status_text.value = text
            self.tts_status_text.color = color
            self.tts_status_icon.color = color
            
        # 局部刷新
        if hasattr(self, 'page') and self.page:
            try:
                self.page.update()
            except Exception:
                pass
        
    def play_voice_sample(self, e=None):
        """播放音色样本"""
        if not self.voice_dropdown.value:
            self.show_message("请先选择音色文件", True)
            self.log_message("播放音色失败: 未选择音色文件")
            return
            
        try:
            voice_path = self.voice_dropdown.value
            self.log_message(f"开始播放音色样本: {voice_path}")
            
            # 检查文件是否存在
            if not os.path.exists(voice_path):
                error_msg = f"音色文件不存在: {voice_path}"
                self.log_message(error_msg)
                self.show_message(error_msg, True)
                
                # 尝试重新扫描音色文件
                self.log_message("尝试重新扫描音色文件...")
                self.scan_voice_files()
                return
            
            # 检查pygame音频系统状态
            if not pygame.mixer.get_init():
                self.log_message("pygame音频系统未初始化，尝试重新初始化...")
                pygame.mixer.init()
                
            # 停止当前播放的音频
            if pygame.mixer.music.get_busy():
                self.log_message("停止当前播放的音频")
                pygame.mixer.music.stop()
            
            # 加载并播放音频文件
            pygame.mixer.music.load(voice_path)
            pygame.mixer.music.play()
            
            self.log_message(f"音色样本播放成功: {os.path.basename(voice_path)}")
            self.show_message("正在播放音色样本")
            
            if self.debug_mode:
                self.log_message(f"音频文件详细信息 - 路径: {voice_path}, 大小: {os.path.getsize(voice_path)} bytes")
                
        except pygame.error as e:
            error_msg = f"pygame音频播放错误: {e}"
            self.log_message(error_msg)
            self.show_message(f"播放失败: {e}", True)
        except Exception as e:
            error_msg = f"播放音色样本时发生未知错误: {e}"
            self.log_message(error_msg)
            self.show_message(f"播放失败: {e}", True)

    def toggle_voice_sample_playback(self, e=None):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            if self.voice_sample_playing and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
                self.voice_sample_playing = False
                if self.voice_sample_button:
                    self.voice_sample_button.text = "试听音色"
                    self.voice_sample_button.icon = ft.Icons.PLAY_CIRCLE
                    self.voice_sample_button.style = ft.ButtonStyle(bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE)
                self.show_message("已停止试听")
                if hasattr(self, 'page') and self.page:
                    self.page.update()
                return
            if not self.voice_dropdown.value:
                self.show_message("请先选择音色文件", True)
                return
            voice_path = self.voice_dropdown.value
            if not os.path.exists(voice_path):
                self.show_message(f"音色文件不存在: {voice_path}", True)
                self.scan_voice_files()
                return
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
            pygame.mixer.music.load(voice_path)
            pygame.mixer.music.play()
            self.voice_sample_playing = True
            self.voice_sample_start_time = time.time()
            if self.voice_sample_button:
                self.voice_sample_button.text = "停止播放"
                self.voice_sample_button.icon = ft.Icons.STOP
                self.voice_sample_button.style = ft.ButtonStyle(bgcolor=ft.Colors.RED_400, color=ft.Colors.WHITE)
            self.show_message("正在播放音色样本")
            if hasattr(self, 'page') and self.page:
                self.page.update()
        except Exception as ex:
            self.show_message(f"播放失败: {ex}", True)
            try:
                self.voice_sample_playing = False
                if self.voice_sample_button:
                    self.voice_sample_button.text = "试听音色"
                    self.voice_sample_button.icon = ft.Icons.PLAY_CIRCLE
                    self.voice_sample_button.style = ft.ButtonStyle(bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE)
                if hasattr(self, 'page') and self.page:
                    self.page.update()
            except Exception:
                pass

    def stop_voice_sample(self, e=None):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
            self.voice_sample_playing = False
            if self.voice_sample_button:
                self.voice_sample_button.text = "试听音色"
                self.voice_sample_button.icon = ft.Icons.PLAY_CIRCLE
                self.voice_sample_button.style = ft.ButtonStyle(bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE)
            self.show_message("已停止试听")
            if hasattr(self, 'page') and self.page:
                self.page.update()
        except Exception as ex:
            self.show_message(f"停止失败: {ex}", True)
            
    def play_subtitle_voice_sample(self, e=None):
        """播放字幕音色样本"""
        if not self.subtitle_voice_dropdown.value:
            self.show_message("请先选择音色文件", True)
            self.log_message("播放字幕音色失败: 未选择音色文件")
            return
            
        try:
            voice_path = self.subtitle_voice_dropdown.value
            self.log_message(f"开始播放字幕音色样本: {voice_path}")
            
            # 检查文件是否存在
            if not os.path.exists(voice_path):
                error_msg = f"音色文件不存在: {voice_path}"
                self.log_message(error_msg)
                self.show_message(error_msg, True)
                
                # 尝试重新扫描音色文件
                self.log_message("尝试重新扫描音色文件...")
                self.scan_voice_files()
                return
            
            # 检查pygame音频系统状态
            if not pygame.mixer.get_init():
                self.log_message("pygame音频系统未初始化，尝试重新初始化...")
                pygame.mixer.init()
                
            # 停止当前播放的音频
            if pygame.mixer.music.get_busy():
                self.log_message("停止当前播放的音频")
                pygame.mixer.music.stop()
            
            # 加载并播放音频文件
            pygame.mixer.music.load(voice_path)
            pygame.mixer.music.play()
            
            self.log_message(f"字幕音色样本播放成功: {os.path.basename(voice_path)}")
            self.show_message("正在播放字幕音色样本")
            
            if self.debug_mode:
                self.log_message(f"音频文件详细信息 - 路径: {voice_path}, 大小: {os.path.getsize(voice_path)} bytes")
                
        except pygame.error as e:
            error_msg = f"pygame音频播放错误: {e}"
            self.log_message(error_msg)
            self.show_message(f"播放失败: {e}", True)
        except Exception as e:
            error_msg = f"播放字幕音色样本时发生未知错误: {e}"
            self.log_message(error_msg)
            self.show_message(f"播放失败: {e}", True)

    def toggle_subtitle_sample_playback(self, e=None):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            if self.subtitle_sample_playing and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
                self.subtitle_sample_playing = False
                if self.subtitle_sample_button:
                    self.subtitle_sample_button.text = "试听"
                    self.subtitle_sample_button.icon = ft.Icons.PLAY_CIRCLE
                    self.subtitle_sample_button.style = ft.ButtonStyle(color=ft.Colors.WHITE, bgcolor=ft.Colors.GREEN_600)
                self.show_message("已停止字幕音色试听")
                if hasattr(self, 'page') and self.page:
                    self.page.update()
                return
            if not self.subtitle_voice_dropdown.value:
                self.show_message("请先选择音色文件", True)
                return
            voice_path = self.subtitle_voice_dropdown.value
            if not os.path.exists(voice_path):
                self.show_message(f"音色文件不存在: {voice_path}", True)
                self.scan_voice_files()
                return
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
            pygame.mixer.music.load(voice_path)
            pygame.mixer.music.play()
            self.subtitle_sample_playing = True
            if self.subtitle_sample_button:
                self.subtitle_sample_button.text = "停止播放"
                self.subtitle_sample_button.icon = ft.Icons.STOP
                self.subtitle_sample_button.style = ft.ButtonStyle(color=ft.Colors.WHITE, bgcolor=ft.Colors.RED_400)
            self.show_message("正在播放字幕音色样本")
            if hasattr(self, 'page') and self.page:
                self.page.update()
        except Exception as ex:
            self.show_message(f"播放失败: {ex}", True)
            try:
                self.subtitle_sample_playing = False
                if self.subtitle_sample_button:
                    self.subtitle_sample_button.text = "试听"
                    self.subtitle_sample_button.icon = ft.Icons.PLAY_CIRCLE
                    self.subtitle_sample_button.style = ft.ButtonStyle(color=ft.Colors.WHITE, bgcolor=ft.Colors.GREEN_600)
                if hasattr(self, 'page') and self.page:
                    self.page.update()
            except Exception:
                pass
            
    def generate_speech(self, e=None):
        """生成语音"""
        if not self.text_input.value:
            self.show_message("请输入要合成的文本", True)
            return
            
        if not self.voice_dropdown.value:
            self.show_message("请选择音色文件", True)
            return
        
        self.tts_stop_flag = False
        self.tts_generating = True
        api_mode = self.config_manager.get("tts_api_mode", "local")
        if api_mode == "remote":
            remote_url = (self.config_manager.get("tts_remote_base_url", "") or "").strip()
            if not remote_url:
                self.show_message("请在设置中配置远程API地址", True)
                return
            try:
                # 启用verbose以在本地控制台显示更多连接状态信息
                client = Client(remote_url, verbose=True)
            except Exception as ex:
                self.show_message(f"连接远程API失败: {ex}", True)
                return
            self.show_message("正在调用远程API生成语音，请稍候...")
            self.update_synthesis_status("生成中")
            self.page.run_thread(
                lambda: self._generate_speech(
                    client,
                    self.voice_dropdown.value,
                    self.text_input.value,
                    remote_url,
                )
            )
            return

        # 本地模式：自动选择第一个可用的运行中实例
        running_instances = [port for port, instance in self.instances.items() 
                           if instance['status'] == '运行中']
        
        if not running_instances:
            self.show_message("没有运行中的实例，请先启动实例", True)
            return
            
        port = running_instances[0]  # 使用第一个运行中的实例
        self.show_message(f"正在生成语音请稍后...")
        
        # 更新状态为生成中
        self.update_synthesis_status("生成中")
        
        # 在后台线程中执行语音生成，避免UI冻结
        self.page.run_thread(
            lambda: self._generate_speech(
                self.instances[port]['client'], 
                self.voice_dropdown.value, 
                self.text_input.value, 
                port
            )
        )
        
    def _generate_speech(self, client, voice_path, text, port):
        """语音生成线程"""
        start_time = time.time()
        try:
            self.log_manager.info(f"开始语音生成 - 端口: {port}, 音色: {os.path.basename(voice_path)}, 文本长度: {len(text)}")
            self.log_manager.debug(f"语音生成详细参数 - 音色路径: {voice_path}, 文本内容: {text[:100]}...")
            
            # 检查客户端连接状态
            if not client:
                error_msg = f"端口 {port} 的客户端连接无效"
                self.log_manager.error(error_msg)
                self.show_message(error_msg, True)
                return
            
            # 检查音色文件是否存在
            if not os.path.exists(voice_path):
                error_msg = f"音色文件不存在: {voice_path}"
                self.log_manager.error(error_msg)
                self.show_message(error_msg, True)
                return
            
            # 记录音色文件信息
            voice_file_size = os.path.getsize(voice_path)
            self.log_manager.debug(f"音色文件信息 - 路径: {voice_path}, 大小: {voice_file_size} bytes")
            
            # 记录生成前outputs文件夹中的文件（本地模式使用）
            outputs_dir = os.path.join(os.getcwd(), "outputs")
            os.makedirs(outputs_dir, exist_ok=True)
            before_files = set(os.listdir(outputs_dir)) if os.path.exists(outputs_dir) else set()
            
            self.log_manager.info(f"调用端口 {port} API进行语音合成...")
            api_start_time = time.time()
            
            # 第一步：更新提示音频（选择音色，必须执行的第一步）
            try:
                update_result = client.predict(api_name="/update_prompt_audio")
                self.log_manager.debug(f"端口 {port} 提示音频更新成功")
            except Exception as update_error:
                # 如果更新失败，记录但继续进行
                self.log_manager.warning(f"端口 {port} 提示音频更新失败: {update_error}")
            
            # 第二步：生成语音（使用 /gen_single 端点，映射音色控制与高级参数）
            # 将本地UI标签映射到远端API的官方choices（Gradio要求Radio传入字符串choices）
            method_map = {
                "与音色参考音频相同": 0,
                "参考音频控制": 1,
                "向量控制": 2,
                "情绪控制": 2,
                "文本控制": 3,
            }
            local_label_map = {
                "与音色参考音频相同": "与音色参考音频相同",
                "参考音频控制": "使用情感参考音频",
                "向量控制": "使用情感向量控制",
                "情绪控制": "使用情感向量控制",
                "文本控制": "使用情感描述文本控制",
            }
            remote_label_map = {
                "与音色参考音频相同": "Same as the voice reference",
                "参考音频控制": "Use emotion reference audio",
                "向量控制": "Use emotion vectors",
                "情绪控制": "Use emotion vectors",
                "文本控制": "Use emotion description text control",
            }
            selected_method = getattr(self, 'emo_method_radio', None) and self.emo_method_radio.value or "与音色参考音频相同"
            emo_method_val = method_map.get(selected_method, 0)
            emo_method_label_local = local_label_map.get(selected_method, "与音色参考音频相同")
            emo_method_label_remote = remote_label_map.get(selected_method, "Same as the voice reference")
            # 远端若未开放“文本情感控制”，为避免Radio choices校验失败，这里回退为官方选项
            # if emo_method_val == 3:
            #    emo_method_label_local = "与音色参考音频相同"
            #    emo_method_label_remote = "Same as the voice reference"
            emo_random_val = bool(getattr(self, 'emo_random_checkbox', None) and self.emo_random_checkbox.value)
            emo_weight_val = float(getattr(self, 'emo_weight_slider', None) and self.emo_weight_slider.value or 0.65)
            emo_text_val = ""
            emo_ref_val = None
            if emo_method_val == 3 and getattr(self, 'emo_text_input', None):
                emo_text_val = (self.emo_text_input.value or "").strip()
            if emo_method_val == 1 and getattr(self, 'emo_ref_path_input', None):
                if self.emo_ref_path_input.value:
                    emo_ref_val = handle_file(self.emo_ref_path_input.value)
            # 语音合成场景使用全局向量滑条
            vec_vals = [0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]
            try:
                if getattr(self, 'vec_sliders', None):
                    for i in range(min(8, len(self.vec_sliders))):
                        vec_vals[i] = float(self.vec_sliders[i].value or 0.0)
            except Exception:
                pass

            # 若存在非零向量，则自动切换为向量控制，避免情感控制失效
            try:
                if sum(abs(float(v)) for v in vec_vals) > 0 and emo_method_label_local != "使用情感向量控制":
                    emo_method_label_local = "使用情感向量控制"
            except Exception:
                pass

            # 本地传索引，远程传choices字符串
            params = {
                "prompt": handle_file(voice_path),
                "text": text,
                "emo_ref_path": emo_ref_val,
                "emo_weight": emo_weight_val,
                "vec1": vec_vals[0],
                "vec2": vec_vals[1],
                "vec3": vec_vals[2],
                "vec4": vec_vals[3],
                "vec5": vec_vals[4],
                "vec6": vec_vals[5],
                "vec7": vec_vals[6],
                "vec8": vec_vals[7],
                "emo_text": emo_text_val,
                "emo_random": emo_random_val,
                "max_text_tokens_per_segment": 120,
                "api_name": "/gen_single",
            }
            result = self._predict_with_emo_choice(client, params, emo_method_label_remote, emo_method_label_local)
            
            api_duration = time.time() - api_start_time
            self.log_manager.debug(f"API调用耗时: {api_duration:.2f} 秒")
            
            # 解析远程/本地返回结果并保存音频；远程模式优先直接保存返回文件
            new_audio_file = None
            api_mode = self.config_manager.get("tts_api_mode", "local")
            if api_mode == "remote":
                try:
                    saved = self.save_audio_from_result(result, outputs_dir, dest_filename=f"spk_remote_{int(time.time())}.wav", base_url=(str(port) if self.config_manager.get("tts_api_mode", "local") == "remote" else None))
                    if saved and os.path.exists(saved):
                        new_audio_file = saved
                        self.log_manager.debug(f"远程API返回音频已保存: {saved}")
                except Exception as ex:
                    self.log_manager.warning(f"远程结果保存失败，回退检测: {ex}")
            
            if self.tts_stop_flag:
                self.tts_generating = False
                self.update_synthesis_status("生成已停止")
                self.show_message("已停止生成")
                return
            if not new_audio_file:
                # 本地模式：监控outputs文件夹，等待新文件生成
                self.log_manager.info("等待语音文件生成...")
                max_wait_time = 30  # 最大等待30秒
                wait_interval = 0.5  # 每0.5秒检查一次
                waited_time = 0
                while waited_time < max_wait_time:
                    time.sleep(wait_interval)
                    waited_time += wait_interval
                    if self.tts_stop_flag:
                        self.tts_generating = False
                        self.update_synthesis_status("生成已停止")
                        self.show_message("已停止生成")
                        return
                    if os.path.exists(outputs_dir):
                        after_files = set(os.listdir(outputs_dir))
                        new_files = after_files - before_files
                        for file in new_files:
                            if file.endswith('.wav') and file.startswith('spk_'):
                                new_audio_file = os.path.join(outputs_dir, file)
                                break
                        if new_audio_file:
                            break
            
            if self.tts_stop_flag:
                self.tts_generating = False
                self.update_synthesis_status("生成已停止")
                self.show_message("已停止生成")
                return
            if new_audio_file and os.path.exists(new_audio_file):
                try:
                    self.apply_speaking_speed(new_audio_file)
                    self.apply_volume(new_audio_file)
                except Exception:
                    pass
                try:
                    dest_dir = getattr(self, 'single_output_dir', None)
                    if dest_dir and os.path.isdir(dest_dir):
                        bn = os.path.basename(new_audio_file)
                        dest_path = os.path.join(dest_dir, bn)
                        if os.path.exists(dest_path):
                            base, ext = os.path.splitext(bn)
                            idx = int(time.time())
                            dest_path = os.path.join(dest_dir, f"{base}_{idx}{ext}")
                        shutil.copy2(new_audio_file, dest_path)
                        self.current_audio_file = dest_path
                    else:
                        self.current_audio_file = new_audio_file
                except Exception:
                    self.current_audio_file = new_audio_file
                total_duration = time.time() - start_time
                
                self.log_manager.info(f"语音生成成功 - 文件: {self.current_audio_file}, 总耗时: {total_duration:.2f}秒")
                
                # 验证生成的音频文件
                file_size = os.path.getsize(self.current_audio_file)
                self.log_manager.info(f"生成音频文件验证成功 - 大小: {file_size} bytes")
                
                # 尝试获取音频时长
                try:
                    audio_duration = self.get_audio_duration(self.current_audio_file)
                    if audio_duration:
                        self.log_manager.debug(f"音频时长: {audio_duration:.2f} 秒")
                except Exception as duration_error:
                    self.log_manager.warning(f"无法获取音频时长: {duration_error}")
                
                # 更新状态显示
                self.update_synthesis_status("生成成功", self.current_audio_file, total_duration)
                self.tts_generating = False
                
                self.show_message("语音生成完成！")
                try:
                    if self.config_manager.get('save_mp3', False) and os.path.isfile(self.current_audio_file):
                        from pydub import AudioSegment
                        seg = AudioSegment.from_file(self.current_audio_file)
                        base, _ext = os.path.splitext(self.current_audio_file)
                        mp3_path = base + ".mp3"
                        seg.export(mp3_path, format="mp3")
                        self.log_manager.info(f"已保存MP3: {mp3_path}")
                        try:
                            # 仅保留MP3：删除原WAV，更新记录为MP3路径
                            if os.path.exists(self.current_audio_file):
                                os.remove(self.current_audio_file)
                            self.current_audio_file = mp3_path
                            self.add_generation_record(mp3_path, text)
                        except Exception:
                            pass
                    else:
                        # 默认只保存WAV
                        try:
                            self.add_generation_record(self.current_audio_file, text)
                        except Exception:
                            pass
                except Exception as mp3err:
                    self.log_manager.warning(f"保存MP3失败: {mp3err}")
            else:
                error_msg = f"在{max_wait_time}秒内未检测到新的音频文件生成"
                self.log_manager.error(error_msg)
                self.update_synthesis_status("生成失败")
                self.show_message("语音生成失败：未检测到生成的音频文件", True)
                self.tts_generating = False
                
        except requests.exceptions.ConnectionError as e:
            error_msg = f"连接端口 {port} 失败: {e}"
            self.log_manager.error(error_msg)
            self.update_synthesis_status("连接失败")
            self.show_message(f"连接失败: 请检查端口 {port} 是否正常运行", True)
            self.tts_generating = False
        except requests.exceptions.Timeout as e:
            error_msg = f"端口 {port} 请求超时: {e}"
            self.log_manager.error(error_msg)
            self.update_synthesis_status("请求超时")
            self.show_message(f"请求超时: 端口 {port} 响应过慢", True)
            self.tts_generating = False
        except Exception as e:
            error_msg = f"语音生成失败 - 端口: {port}, 错误: {e}"
            self.log_manager.error(error_msg)
            self.log_manager.exception(f"语音生成异常详情 - 端口: {port}")
            self.update_synthesis_status("生成失败")
            self.show_message(f"语音生成失败: {e}", True)
            self.tts_generating = False

    def stop_speech_generation(self, e=None):
        try:
            self.tts_stop_flag = True
            self.show_message("正在停止生成...")
        except Exception:
            pass
            
    def play_generated_audio(self, e=None):
        """播放生成的音频"""
        if not getattr(self, 'current_audio_file', None):
            self.show_message("没有可播放的音频文件", True)
            return
            
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            
            # Toggle logic
            if pygame.mixer.music.get_busy():
                 pygame.mixer.music.stop()
                 if hasattr(self, 'play_result_button'):
                     self.play_result_button.icon = ft.Icons.PLAY_ARROW
                     self.play_result_button.text = "播放结果"
                     self.play_result_button.style = ft.ButtonStyle(bgcolor=ft.Colors.PURPLE, color=ft.Colors.WHITE)
                 if hasattr(self, 'page') and self.page:
                     self.page.update()
                 return

            pygame.mixer.music.load(self.current_audio_file)
            pygame.mixer.music.play()
            
            if hasattr(self, 'play_result_button'):
                 self.play_result_button.icon = ft.Icons.STOP
                 self.play_result_button.text = "停止播放"
                 self.play_result_button.style = ft.ButtonStyle(bgcolor=ft.Colors.RED_400, color=ft.Colors.WHITE)
            if hasattr(self, 'page') and self.page:
                 self.page.update()
                 
            self.show_message("正在播放生成的音频")
        except Exception as e:
            self.show_message(f"播放失败: {e}", True)
            # Reset button state on failure
            if hasattr(self, 'play_result_button'):
                 self.play_result_button.icon = ft.Icons.PLAY_ARROW
                 self.play_result_button.text = "播放结果"
                 self.play_result_button.style = ft.ButtonStyle(bgcolor=ft.Colors.PURPLE, color=ft.Colors.WHITE)
            if hasattr(self, 'page') and self.page:
                 self.page.update()

    def stop_playback(self, e=None):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
            self.show_message("已停止播放")
        except Exception as ex:
            self.show_message(f"停止失败: {ex}", True)

    def safe_open_batch_edit_dialog(self, e=None):
        try:
            self.open_batch_edit_dialog(e)
        except Exception as ex:
            self.show_message(f"打开批量编辑失败: {ex}", True)

    def safe_update(self, ctrl):
        try:
            if ctrl:
                ctrl.update()
        except Exception:
            pass

    def toggle_history_play(self, path: str, btn=None):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            if self.current_audio_file == path and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
                if btn:
                    btn.text = "播放"
                    btn.icon = ft.Icons.PLAY_ARROW
                if hasattr(self, 'page') and self.page:
                    self.page.update()
                return
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
                # Reset previous history button if exists
                if getattr(self, 'current_history_play_btn', None):
                    try:
                        self.current_history_play_btn.text = "播放"
                        self.current_history_play_btn.icon = ft.Icons.PLAY_ARROW
                        self.current_history_play_btn.update()
                    except:
                        pass
            if path and os.path.isfile(path):
                pygame.mixer.music.load(path)
                pygame.mixer.music.play()
                self.current_audio_file = path
                if btn:
                    btn.text = "停止"
                    btn.icon = ft.Icons.STOP
                    self.current_history_play_btn = btn
                if hasattr(self, 'page') and self.page:
                    self.page.update()
        except Exception as ex:
            self.show_message(f"播放失败: {ex}", True)

    def toggle_library_play(self, path: str, btn=None):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            if getattr(self, 'current_audio_file', None) == path and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
                if btn:
                    btn.icon = ft.Icons.PLAY_CIRCLE
                if hasattr(self, 'page') and self.page:
                    self.page.update()
                return
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
                # Reset previous button if exists
                if getattr(self, 'current_list_play_btn', None):
                    try:
                        self.current_list_play_btn.icon = ft.Icons.PLAY_CIRCLE
                        self.current_list_play_btn.update()
                    except:
                        pass

            if path and os.path.isfile(path):
                pygame.mixer.music.load(path)
                pygame.mixer.music.play()
                self.current_audio_file = path
                if btn:
                    btn.icon = ft.Icons.STOP
                    self.current_list_play_btn = btn
                if hasattr(self, 'page') and self.page:
                    self.page.update()
        except Exception as ex:
            self.show_message(f"播放失败: {ex}", True)

    def open_audio_location(self, e=None):
        try:
            path = getattr(self, 'current_audio_file', None)
            if not path or not os.path.isfile(path):
                self.show_message("没有可用的音频文件", True)
                return
            subprocess.run(['explorer', '/select,', path], capture_output=True, text=True)
            self.show_message("已打开文件位置")
        except Exception as ex:
            self.show_message(f"打开文件位置失败: {ex}", True)

    def delete_generated_audio(self, e=None):
        try:
            path = getattr(self, 'current_audio_file', None)
            if not path or not os.path.isfile(path):
                self.show_message("没有可删除的音频", True)
                return
            os.remove(path)
            self.current_audio_file = None
            self.show_message("已删除生成音频")
        except Exception as ex:
            self.show_message(f"删除失败: {ex}", True)
            
    def open_output_location(self, e=None):
        """打开音频文件所在位置"""
        if hasattr(self, 'current_audio_file') and self.current_audio_file and os.path.exists(self.current_audio_file):
            try:
                # 获取文件所在目录
                file_dir = os.path.dirname(self.current_audio_file)
                # 在Windows中打开文件夹并选中文件
                # 不使用check=True，因为explorer命令可能返回非零退出状态但仍然成功打开
                result = subprocess.run(['explorer', '/select,', self.current_audio_file], 
                                      capture_output=True, text=True)
                self.show_message(f"已打开文件位置: {file_dir}")
                self.log_manager.info(f"成功打开文件位置: {file_dir}")
            except Exception as ex:
                self.log_manager.error(f"打开文件位置失败: {ex}")
                self.show_message(f"打开文件位置失败: {ex}", True)
        else:
            self.show_message("没有可用的音频文件", True)

    def on_podcast_pick_output_dir_result(self, e: ft.FilePickerResultEvent):
        try:
            p = getattr(e, 'path', '') or ''
            if p:
                setattr(self, 'podcast_output_dir', p)
                if getattr(self, 'podcast_output_dir_field', None):
                    self.podcast_output_dir_field.value = p
            if hasattr(self, 'page') and self.page:
                self.page.update()
        except Exception as ex:
            self.show_message(f"选择输出目录失败: {ex}", True)

    def open_podcast_output_dir(self, e=None):
        try:
            d = getattr(self, 'podcast_output_dir', None)
            if not d:
                self.show_message("请先选择输出目录", True)
                return
            if not os.path.isdir(d):
                self.show_message("输出目录不存在", True)
                return
            subprocess.run(['explorer', str(d)], capture_output=True, text=True)
        except Exception as ex:
            self.show_message(f"打开输出目录失败: {ex}", True)
            
    def open_subtitle_folder(self, e=None):
        """打开字幕文件夹"""
        try:
            # 检查是否有生成的字幕文件
            outputs_folder = Path("outputs")
            if not outputs_folder.exists():
                self.show_message("outputs文件夹不存在，请先生成字幕", True)
                return
            
            # 检查是否有字幕文件
            subtitle_files = list(outputs_folder.glob("subtitle_merged_*.srt"))
            if not subtitle_files:
                self.show_message("没有找到生成的字幕文件，请先完成字幕生成", True)
                return
            
            # 在Windows中打开文件夹
            result = subprocess.run(['explorer', str(outputs_folder)], 
                                  capture_output=True, text=True)
            self.show_message(f"已打开输出文件夹: {outputs_folder}")
            self.log_manager.info(f"成功打开输出文件夹: {outputs_folder}")
        except Exception as e:
            self.log_manager.error(f"打开输出文件夹失败: {e}")
            self.show_message(f"打开输出文件夹失败: {e}", True)
            
    def play_subtitle_audio(self, e=None):
        """播放字幕音频并显示字幕"""
        try:
            # 检查是否有生成的字幕音频文件
            outputs_folder = Path("outputs")
            if not outputs_folder.exists():
                self.show_message("outputs文件夹不存在，请先生成字幕", True)
                return
                
            # 查找最新的合并音频文件
            audio_files = list(outputs_folder.glob("subtitle_merged_*.wav"))
            if not audio_files:
                self.show_message("没有找到合并的字幕音频文件，请先生成字幕", True)
                return
                
            # 选择最新的文件
            latest_audio = max(audio_files, key=lambda x: x.stat().st_mtime)
            
            # 初始化pygame mixer（如果还没有初始化）
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            
            # 停止当前播放的音频（如果有）
            pygame.mixer.music.stop()
            
            # 播放音频
            pygame.mixer.music.load(str(latest_audio))
            pygame.mixer.music.play()
            
            # 显示字幕同步播放
            self.start_subtitle_sync_display(latest_audio)
            
            self.show_message(f"正在播放字幕音频: {latest_audio.name}")
            self.log_manager.info(f"开始播放字幕音频: {latest_audio}")
            
        except Exception as e:
            self.log_manager.error(f"播放字幕音频失败: {e}")
            self.show_message(f"播放字幕音频失败: {e}", True)
            
    def start_subtitle_sync_display(self, audio_file):
        """开始同步显示字幕"""
        try:
            # 获取对应的字幕文件
            subtitle_file = audio_file.with_suffix('.srt')
            if not subtitle_file.exists():
                self.log_manager.warning(f"字幕文件不存在: {subtitle_file}")
                return
                
            # 解析字幕文件
            subtitles = self.parse_subtitle_file(subtitle_file)
            if not subtitles:
                self.log_manager.warning("字幕文件为空或解析失败")
                return
                
            # 创建字幕显示对话框
            self.create_subtitle_display_dialog(subtitles)
            
        except Exception as e:
            self.log_manager.error(f"启动字幕同步显示失败: {e}")
            
    def parse_subtitle_file(self, subtitle_file):
        """解析字幕文件"""
        try:
            subtitles = []
            with open(subtitle_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                
            # 分割字幕块
            blocks = content.split('\n\n')
            for block in blocks:
                lines = block.strip().split('\n')
                if len(lines) >= 3:
                    # 解析时间戳
                    time_line = lines[1]
                    if ' --> ' in time_line:
                        start_time, end_time = time_line.split(' --> ')
                        start_seconds = self.parse_time_to_seconds(start_time)
                        end_seconds = self.parse_time_to_seconds(end_time)
                        
                        # 获取字幕文本
                        text = '\n'.join(lines[2:])
                        
                        subtitles.append({
                            'start': start_seconds,
                            'end': end_seconds,
                            'text': text
                        })
                        
            return subtitles
        except Exception as e:
            self.log_manager.error(f"解析字幕文件失败: {e}")
            return []
            
    def parse_time_to_seconds(self, time_str):
        """将时间字符串转换为秒数"""
        try:
            # 格式: 00:00:01,000
            time_str = time_str.replace(',', '.')
            parts = time_str.split(':')
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
            return hours * 3600 + minutes * 60 + seconds
        except Exception as e:
            self.log_manager.error(f"解析时间失败: {e}")
            return 0
            
    def create_subtitle_display_dialog(self, subtitles):
        """创建字幕显示对话框"""
        try:
            # 创建字幕显示文本
            self.current_subtitle_text = ft.Text(
                "准备播放字幕...",
                size=24,
                weight=ft.FontWeight.BOLD,
                text_align=ft.TextAlign.CENTER,
                color=ft.Colors.WHITE
            )
            
            # 创建进度显示
            self.subtitle_progress_text = ft.Text(
                "00:00 / 00:00",
                size=14,
                color=ft.Colors.WHITE70,
                text_align=ft.TextAlign.CENTER
            )
            
            # 创建对话框内容
            dialog_content = ft.Column([
                self.current_subtitle_text,
                ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
                self.subtitle_progress_text
            ], 
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER)
            
            # 创建对话框
            self.subtitle_dialog = ft.AlertDialog(
                title=ft.Row([
                    ft.Icon(ft.Icons.PLAY_CIRCLE_FILLED, color=ft.Colors.BLUE),
                    ft.Text("字幕播放器", weight=ft.FontWeight.BOLD, size=18)
                ]),
                content=ft.Container(
                    content=dialog_content,
                    width=700,
                    height=250,
                    bgcolor=ft.Colors.BLACK87,
                    border_radius=15,
                    padding=30,
                    alignment=ft.alignment.center,
                    border=ft.border.all(2, ft.Colors.BLUE_400)
                ),
                actions=[
                    ft.ElevatedButton(
                        "停止播放", 
                        icon=ft.Icons.STOP,
                        on_click=self.stop_subtitle_playback,
                        bgcolor=ft.Colors.RED_400,
                        color=ft.Colors.WHITE
                    ),
                    ft.ElevatedButton(
                        "关闭", 
                        icon=ft.Icons.CLOSE,
                        on_click=self.close_subtitle_dialog,
                        bgcolor=ft.Colors.GREY_600,
                        color=ft.Colors.WHITE
                    ),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
                on_dismiss=lambda e: self.stop_subtitle_playback()
            )
            
            # 显示对话框
            self.page.overlay.append(self.subtitle_dialog)
            self.subtitle_dialog.open = True
            self.page.update()
            
            # 开始字幕同步线程
            self.subtitle_sync_thread = threading.Thread(
                target=self.subtitle_sync_worker,
                args=(subtitles,),
                daemon=True
            )
            self.subtitle_sync_running = True
            self.subtitle_sync_thread.start()
            
        except Exception as e:
            self.log_manager.error(f"创建字幕显示对话框失败: {e}")
            
    def subtitle_sync_worker(self, subtitles):
        """字幕同步工作线程"""
        try:
            start_time = time.time()
            total_duration = max([subtitle['end'] for subtitle in subtitles]) if subtitles else 0
            
            while self.subtitle_sync_running and pygame.mixer.music.get_busy():
                current_time = time.time() - start_time
                
                # 查找当前时间对应的字幕
                current_subtitle = ""
                for subtitle in subtitles:
                    if subtitle['start'] <= current_time <= subtitle['end']:
                        current_subtitle = subtitle['text']
                        break
                
                # 计算播放进度
                progress_percent = min(100, (current_time / total_duration * 100)) if total_duration > 0 else 0
                progress_text = f"播放进度: {self.format_timestamp(current_time)} / {self.format_timestamp(total_duration)} ({progress_percent:.1f}%)"
                
                # 更新字幕显示
                if hasattr(self, 'current_subtitle_text'):
                    self.current_subtitle_text.value = current_subtitle if current_subtitle else "..."
                    
                # 更新进度显示
                if hasattr(self, 'subtitle_progress_text'):
                    self.subtitle_progress_text.value = progress_text
                    
                try:
                    self.page.update()
                except:
                    break
                
                time.sleep(0.1)  # 100ms更新一次
                
            # 播放结束，关闭对话框
            if hasattr(self, 'subtitle_dialog') and self.subtitle_dialog.open:
                self.subtitle_dialog.open = False
                try:
                    self.page.update()
                except:
                    pass
                    
        except Exception as e:
            self.log_manager.error(f"字幕同步工作线程错误: {e}")
            
    def stop_subtitle_playback(self, e=None):
        """停止字幕播放"""
        try:
            self.subtitle_sync_running = False
            pygame.mixer.music.stop()
            if hasattr(self, 'subtitle_dialog') and self.subtitle_dialog.open:
                self.subtitle_dialog.open = False
                self.page.update()
            self.show_message("已停止字幕播放")
        except Exception as e:
            self.log_manager.error(f"停止字幕播放失败: {e}")
            
    def close_subtitle_dialog(self, e=None):
        """关闭字幕对话框"""
        try:
            self.subtitle_sync_running = False
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
            if hasattr(self, 'subtitle_dialog') and self.subtitle_dialog.open:
                self.subtitle_dialog.open = False
                self.page.update()
        except Exception as e:
            self.log_manager.error(f"关闭字幕对话框失败: {e}")
        
    def clear_console(self, e=None):
        """清空控制台"""
        if self.console_output:
            self.console_output.controls.clear()
            try:
                self.console_output.update()
            except Exception:
                pass
            
    def save_console_log(self, e=None):
        """保存控制台日志"""
        try:
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_dir = Path('logs')
            log_dir.mkdir(exist_ok=True)
            out_path = log_dir / f"console_{ts}.log"
            lines = []
            if self.console_output and hasattr(self.console_output, 'controls') and self.console_output.controls:
                for ctrl in self.console_output.controls:
                    try:
                        txt = getattr(ctrl, 'value', None)
                        if isinstance(txt, str):
                            lines.append(txt)
                        else:
                            # 兼容其他控件，尝试序列化
                            lines.append(str(ctrl))
                    except Exception:
                        continue
            else:
                # 回退：导出当前文件日志路径提示
                lines.append(f"当前文件日志: {self.log_manager.log_file_path}")
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            self.log_manager.info(f"控制台日志已保存到: {out_path}")
            self.show_message(f"日志已保存: {out_path}")
            try:
                import webbrowser
                webbrowser.open(str(out_path))
            except Exception:
                pass
        except Exception as ex:
            if hasattr(self, 'log_manager'):
                self.log_manager.error(f"保存控制台日志失败: {ex}")
            self.show_message(f"保存日志失败: {ex}", True)
        
    def open_webui(self, e=None):
        """打开WebUI"""
        self.log_message("打开WebUI按钮被点击")
        if self.instances:
            port = list(self.instances.keys())[0]
            url = f"http://127.0.0.1:{port}"
            self.log_message(f"尝试打开WebUI: {url}")
            try:
                import webbrowser
                webbrowser.open(url)
                self.show_message(f"已打开WebUI: {url}")
            except Exception as e:
                self.log_message(f"打开WebUI失败: {e}")
                self.show_message(f"打开WebUI失败: {e}", True)
        else:
            self.log_message("没有运行的实例，无法打开WebUI")
            self.show_message("没有运行的实例", True)
            
    def show_logs(self, e=None):
        """显示日志"""
        # 切换到控制台输出视图
        self.nav_rail.selected_index = 8
        self.on_nav_change(type('obj', (object,), {'control': self.nav_rail})())

    # ---------------------- 播客生成功能 ----------------------
    def create_podcast_view(self):
        """创建播客生成视图"""
        # 如果正在扫描且没有缓存的音色文件，显示加载中
        if getattr(self, '_is_scanning', False) and not getattr(self, 'voice_files', []):
            return ft.Container(
                content=ft.Column([
                    ft.ProgressRing(),
                    ft.Text("正在扫描音色库...", size=14, color=ft.Colors.GREY)
                ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                alignment=ft.alignment.center,
                expand=True
            )

        self.podcast_style_dropdown = ft.Dropdown(
            label="风格预设",
            value="亲切随和",
            options=[
                ft.dropdown.Option("无"),
                ft.dropdown.Option("亲切随和"),
                ft.dropdown.Option("专业播报"),
                ft.dropdown.Option("轻松聊天"),
                ft.dropdown.Option("温柔叙述"),
                ft.dropdown.Option("新闻播报"),
                ft.dropdown.Option("情感故事"),
                ft.dropdown.Option("悬疑惊悚"),
            ],
            width=160,
            text_size=12,
            content_padding=10
        )
        
        # 角色下拉框
        self.podcast_voice_a_dropdown = ft.Dropdown(label="说话人A音色", text_size=12, content_padding=ft.padding.symmetric(horizontal=8, vertical=6), expand=True)
        self.podcast_voice_b_dropdown = ft.Dropdown(label="说话人B音色", text_size=12, content_padding=ft.padding.symmetric(horizontal=8, vertical=6), expand=True)
        self.podcast_voice_c_dropdown = ft.Dropdown(label="说话人C音色", text_size=12, content_padding=ft.padding.symmetric(horizontal=8, vertical=6), expand=True)
        self.podcast_voice_d_dropdown = ft.Dropdown(label="说话人D音色", text_size=12, content_padding=ft.padding.symmetric(horizontal=8, vertical=6), expand=True)
        
        # 使用带筛选的选择器
        voice_a_selector = self.create_voice_selector_row(self.podcast_voice_a_dropdown, "podcast_voice_a_category_dropdown")
        voice_b_selector = self.create_voice_selector_row(self.podcast_voice_b_dropdown, "podcast_voice_b_category_dropdown")
        voice_c_selector = self.create_voice_selector_row(self.podcast_voice_c_dropdown, "podcast_voice_c_category_dropdown")
        voice_d_selector = self.create_voice_selector_row(self.podcast_voice_d_dropdown, "podcast_voice_d_category_dropdown")
        
        # 试听按钮 - 使用 IconButton 节省空间
        self.podcast_audition_a_btn = ft.IconButton(icon=ft.Icons.PLAY_CIRCLE, tooltip="试听A音色", on_click=lambda e: self.play_podcast_voice_sample('A'), icon_size=20)
        self.podcast_audition_b_btn = ft.IconButton(icon=ft.Icons.PLAY_CIRCLE, tooltip="试听B音色", on_click=lambda e: self.play_podcast_voice_sample('B'), icon_size=20)
        self.podcast_audition_c_btn = ft.IconButton(icon=ft.Icons.PLAY_CIRCLE, tooltip="试听C音色", on_click=lambda e: self.play_podcast_voice_sample('C'), icon_size=20)
        self.podcast_audition_d_btn = ft.IconButton(icon=ft.Icons.PLAY_CIRCLE, tooltip="试听D音色", on_click=lambda e: self.play_podcast_voice_sample('D'), icon_size=20)
        
        self.podcast_speed_label = ft.Text("语速: 1.0x", size=12)
        def _on_podcast_speed_change(e):
            try:
                v = float(e.control.value or 1.0)
                self.podcast_speed_label.value = f"语速: {v:.1f}x"
                if getattr(self, 'page', None):
                    self.page.update()
            except Exception:
                pass
        self.podcast_speed_slider = ft.Slider(min=0.7, max=1.3, divisions=12, value=1.0, on_change=_on_podcast_speed_change, expand=True)
        
        self.podcast_emo_weight_label = ft.Text("情感权重: 0.65", size=12)
        def _on_podcast_emo_change(e):
            try:
                v = float(e.control.value)
                self.podcast_emo_weight_label.value = f"情感权重: {v:.2f}"
                if getattr(self, 'page', None):
                    self.page.update()
            except Exception:
                pass
        self.podcast_emo_weight = ft.Slider(min=0.0, max=1.0, divisions=100, value=0.65, label="{value}", on_change=_on_podcast_emo_change, expand=True)
        
        self.podcast_volume_value_text = ft.Text(f"{int(self.config_manager.get('volume_percent', 100))}%", size=12)
        def _on_podcast_volume_change(e):
            try:
                v = int(e.control.value)
                setattr(self, 'runtime_volume_percent', v)
                self.podcast_volume_value_text.value = f"{v}%"
                if getattr(self, 'page', None):
                    self.page.update()
            except Exception:
                pass
        self.podcast_volume_slider = ft.Slider(min=0, max=200, divisions=200,
                                               value=float(self.config_manager.get('volume_percent', 100)),
                                               on_change=_on_podcast_volume_change, width=150)
        
        self.podcast_bgm_path = ft.TextField(label="背景音乐(可选)", read_only=True, expand=True, text_size=12, height=40, content_padding=10)
        self.podcast_bgm_percent_value_text = ft.Text("100%", size=12)
        def _on_bgm_percent_change(e):
            try:
                v = int(e.control.value)
                self.podcast_bgm_percent_value_text.value = f"{v}%"
                if getattr(self, 'page', None):
                    self.page.update()
            except Exception:
                pass
        self.podcast_bgm_percent_slider = ft.Slider(min=10, max=200, divisions=190, value=100, on_change=_on_bgm_percent_change, expand=True)
        
        self.podcast_bgm_picker = ft.FilePicker(on_result=lambda e: setattr(self.podcast_bgm_path, 'value', (e.files[0].path if e.files else '')) or self.page.update())
        self.podcast_bgm_audition_btn = ft.IconButton(icon=ft.Icons.PLAY_CIRCLE, tooltip="试听背景音", on_click=self.play_bgm_sample, icon_size=20)
        
        def pick_bgm_click(e):
            if self.page and self.podcast_bgm_picker not in self.page.overlay:
                self.page.overlay.append(self.podcast_bgm_picker)
                self.page.update()
            self.podcast_bgm_picker.pick_files(allow_multiple=False, file_type=ft.FilePickerFileType.AUDIO)
            
        pick_bgm_btn = ft.IconButton(icon=ft.Icons.FOLDER_OPEN, tooltip="选择音乐", on_click=pick_bgm_click)
        
        self.podcast_unlabeled_mode_dropdown = ft.Dropdown(
            label="未标注分配",
            value="默认A",
            options=[
                ft.dropdown.Option("默认A"),
                ft.dropdown.Option("默认B"),
                ft.dropdown.Option("默认C"),
                ft.dropdown.Option("默认D"),
                ft.dropdown.Option("交替AB"),
                ft.dropdown.Option("ABC交替"),
                ft.dropdown.Option("ABCD交替")
            ],
            width=160,
            text_size=12,
            content_padding=10
        )
        
        self.podcast_script_input = ft.TextField(
            label="播客脚本", 
            multiline=True, 
            min_lines=15, 
            max_lines=30, 
            hint_text="格式示例：\nA: 大家好\nB: 欢迎收听\n\n用 A:/B:/C:/D: 明确说话人；未标注内容将按设定模式分配",
            text_size=13,
            expand=True
        )
        self.podcast_segments_preview = ft.ListView(expand=True, auto_scroll=True, height=200, controls=[])
        parse_btn = ft.ElevatedButton("解析脚本", icon=ft.Icons.TEXT_SNIPPET, on_click=self.parse_podcast_script, style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE))
        self.podcast_gen_btn = ft.ElevatedButton("生成播客", icon=ft.Icons.PLAYLIST_ADD_CHECK, on_click=self.start_podcast_generation, style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_600, color=ft.Colors.WHITE))
        self.podcast_generating = False
        self.podcast_audition_playing = None
        self.podcast_progress = ft.ProgressBar(value=0, height=8, color=ft.Colors.PURPLE, bgcolor=ft.Colors.PURPLE_100)
        self.podcast_status = ft.Text("准备就绪", size=12, color=ft.Colors.GREY_700)
        self.podcast_output_file = None
        self.podcast_play_btn = ft.ElevatedButton("播放结果", icon=ft.Icons.VOLUME_UP, on_click=self.play_podcast_output)
        self.podcast_bgm_audition_playing = False
        self.open_output_location_btn = ft.ElevatedButton("打开位置", icon=ft.Icons.FOLDER_OPEN, on_click=self.open_output_location)
        self.podcast_playing_output = False

        # --- 布局构建 ---
        
        # 1. 角色配置卡片 - 2x2 网格布局优化
        def build_role_cell(label, icon, color, selector, btn):
            return ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(icon, size=16, color=color),
                        ft.Text(label, weight=ft.FontWeight.BOLD, size=13),
                        ft.Container(expand=True),
                        btn
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    selector
                ], spacing=5),
                bgcolor=ft.Colors.with_opacity(0.05, color) if not self.page or self.page.theme_mode == ft.ThemeMode.LIGHT else ft.Colors.with_opacity(0.1, ft.Colors.WHITE),
                padding=8, 
                border_radius=8,
                expand=True
            )

        role_a_cell = build_role_cell("角色 A", ft.Icons.PERSON, ft.Colors.BLUE_400, voice_a_selector, self.podcast_audition_a_btn)
        role_b_cell = build_role_cell("角色 B", ft.Icons.PERSON, ft.Colors.PINK_400, voice_b_selector, self.podcast_audition_b_btn)
        role_c_cell = build_role_cell("角色 C", ft.Icons.PERSON, ft.Colors.ORANGE_400, voice_c_selector, self.podcast_audition_c_btn)
        role_d_cell = build_role_cell("角色 D", ft.Icons.PERSON, ft.Colors.TEAL_400, voice_d_selector, self.podcast_audition_d_btn)

        role_config_card = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.PEOPLE, color=ft.Colors.BLUE),
                        title=ft.Text("角色配置", weight=ft.FontWeight.BOLD),
                        subtitle=ft.Text("设置各角色音色及分配模式"),
                        content_padding=0
                    ),
                    ft.Divider(height=1),
                    ft.Row([self.podcast_style_dropdown, self.podcast_unlabeled_mode_dropdown], spacing=20),
                    ft.Container(height=5),
                    ft.Row([role_a_cell, role_b_cell], spacing=10),
                    ft.Row([role_c_cell, role_d_cell], spacing=10),
                ], spacing=10),
                padding=15,
            ),
            elevation=2
        )

        # 2. 音频参数与背景音卡片
        audio_bgm_card = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.TUNE, color=ft.Colors.ORANGE),
                        title=ft.Text("音频与背景", weight=ft.FontWeight.BOLD),
                        subtitle=ft.Text("调整语速、情感、音量及背景音乐"),
                        content_padding=0
                    ),
                    ft.Divider(height=1),
                    
                    ft.Row([
                        ft.Icon(ft.Icons.SPEED, size=16, color=ft.Colors.GREY),
                        self.podcast_speed_label, 
                        self.podcast_speed_slider,
                        ft.VerticalDivider(width=10),
                        ft.Icon(ft.Icons.VOLUME_UP, size=16, color=ft.Colors.GREY),
                        ft.Text("音量:", size=12), 
                        self.podcast_volume_slider, 
                        self.podcast_volume_value_text
                    ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    
                    ft.Row([
                        ft.Icon(ft.Icons.EMOJI_EMOTIONS, size=16, color=ft.Colors.GREY),
                        self.podcast_emo_weight_label,
                        self.podcast_emo_weight
                    ], vertical_alignment=ft.CrossAxisAlignment.CENTER),

                    ft.Divider(height=5, color=ft.Colors.TRANSPARENT),

                    ft.Text("背景音乐:", weight=ft.FontWeight.BOLD, size=13),
                    ft.Row([self.podcast_bgm_path]),
                    ft.Row([
                        pick_bgm_btn,
                        self.podcast_bgm_audition_btn
                    ], spacing=10),
                    ft.Row([
                        ft.Text("BGM音量:", size=12), 
                        self.podcast_bgm_percent_slider, 
                        self.podcast_bgm_percent_value_text, 
                    ], spacing=5, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ], spacing=8),
                padding=15,
            ),
            elevation=2
        )

        # 3. 输出设置区域
        output_row = ft.Container(
            content=ft.Row([
                (lambda: (
                    setattr(self, 'podcast_output_dir_field', ft.TextField(label="输出目录", read_only=True, expand=True, height=40, text_size=12, content_padding=10)),
                    self.podcast_output_dir_field
                ))()[1],
                (lambda: (
                    setattr(self, 'podcast_dir_picker', getattr(self, 'podcast_dir_picker', None) or ft.FilePicker(on_result=self.on_podcast_pick_output_dir_result)),
                    ft.IconButton(icon=ft.Icons.FOLDER_OPEN, tooltip="选择输出目录", on_click=lambda e: (
                         (self.page.overlay.append(self.podcast_dir_picker) if self.page and self.podcast_dir_picker not in self.page.overlay else None),
                         self.page.update() if self.page else None,
                         self.podcast_dir_picker.get_directory_path()
                    ))
                ))()[1],
                ft.IconButton(icon=ft.Icons.OPEN_IN_NEW, tooltip="打开输出目录", on_click=self.open_podcast_output_dir),
            ], spacing=5),
            padding=ft.padding.symmetric(horizontal=5)
        )

        # 左侧列容器
        left_column = ft.Column([
            role_config_card,
            audio_bgm_card,
            ft.Card(content=ft.Container(content=output_row, padding=10), elevation=2)
        ], spacing=10, scroll=ft.ScrollMode.AUTO)

        # 右侧列容器（脚本与操作）
        right_column = ft.Column([
            ft.Card(
                content=ft.Container(
                    content=ft.Column([
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.DESCRIPTION, color=ft.Colors.PURPLE),
                            title=ft.Text("脚本与生成", weight=ft.FontWeight.BOLD),
                            trailing=ft.Row([parse_btn, self.podcast_gen_btn], spacing=10, alignment=ft.MainAxisAlignment.END, width=250),
                            content_padding=0
                        ),
                        ft.Divider(height=1),
                        self.podcast_script_input,
                        ft.Text("段落预览:", size=12, color=ft.Colors.GREY_600),
                        ft.Container(
                            content=self.podcast_segments_preview,
                            bgcolor=ft.Colors.BLACK12 if not self.page or self.page.theme_mode == ft.ThemeMode.LIGHT else ft.Colors.BLACK54,
                            border_radius=8,
                            padding=10,
                            expand=True
                        ),
                        ft.Divider(height=1),
                        ft.Row([self.podcast_progress, self.podcast_status], spacing=10, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Row([self.podcast_play_btn, self.open_output_location_btn], spacing=10, alignment=ft.MainAxisAlignment.END),
                    ], spacing=10, expand=True),
                    padding=15,
                    expand=True
                ),
                elevation=2,
                expand=True
            )
        ], expand=True)

        return ft.Container(
            content=ft.Row([
                ft.Container(content=left_column, width=550), # 固定左侧宽度
                ft.Container(content=right_column, expand=True) # 右侧自适应
            ], spacing=15, expand=True, vertical_alignment=ft.CrossAxisAlignment.START),
            padding=15,
            expand=True,
        )

    # ---------------------- 批量生成视图与逻辑 ----------------------
    def create_bulk_generation_view(self):
        """创建批量语音生成视图 - 重构版"""
        # 如果正在扫描且没有缓存的音色文件，显示加载中
        if getattr(self, '_is_scanning', False) and not getattr(self, 'voice_files', []):
            return ft.Container(
                content=ft.Column([
                    ft.ProgressRing(),
                    ft.Text("正在扫描音色库...", size=14, color=ft.Colors.GREY)
                ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                alignment=ft.alignment.center,
                expand=True
            )

        # --- 左侧：配置区域 ---

        # 1. 文件与目录选择
        if not hasattr(self, 'bulk_file_picker') or self.bulk_file_picker is None:
            self.bulk_file_picker = ft.FilePicker(on_result=self.on_bulk_pick_files_result)
            if self.page and self.bulk_file_picker not in self.page.overlay:
                self.page.overlay.append(self.bulk_file_picker)
        
        pick_files_btn = ft.ElevatedButton(
            "选择文稿文件",
            icon=ft.Icons.UPLOAD_FILE,
            on_click=lambda e: self.bulk_file_picker.pick_files(allow_multiple=True, file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["txt"], dialog_title="选择要批量合成的文稿文件"),
            style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_50, color=ft.Colors.BLUE_800)
        )

        if not hasattr(self, 'bulk_dir_picker') or self.bulk_dir_picker is None:
            self.bulk_dir_picker = ft.FilePicker(on_result=self.on_bulk_pick_output_dir_result)
            if self.page and self.bulk_dir_picker not in self.page.overlay:
                self.page.overlay.append(self.bulk_dir_picker)
        
        self.bulk_output_dir_field = ft.TextField(label="输出目录", read_only=True, text_size=12, height=40, content_padding=10, expand=True)
        pick_output_dir_btn = ft.IconButton(icon=ft.Icons.FOLDER_OPEN, tooltip="选择输出目录", on_click=lambda e: self.bulk_dir_picker.get_directory_path())
        open_output_dir_btn = ft.IconButton(icon=ft.Icons.OPEN_IN_NEW, tooltip="打开输出文件夹", on_click=self.open_bulk_output_dir)

        file_config_card = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.FOLDER_SPECIAL, color=ft.Colors.INDIGO),
                        title=ft.Text("文件与目录", weight=ft.FontWeight.BOLD),
                        subtitle=ft.Text("选择输入文稿 (.txt) 和输出位置"),
                        content_padding=0
                    ),
                    ft.Divider(height=1),
                    ft.Row([pick_files_btn, ft.Text("支持多选" , size=12, color=ft.Colors.GREY_600)], spacing=10),
                    ft.Row([self.bulk_output_dir_field, pick_output_dir_btn, open_output_dir_btn], spacing=5),
                ], spacing=15),
                padding=15,
            ),
            elevation=2
        )

        # 2. 音色与参数设置
        # 音色选择
        voice_dropdown = self.create_voice_dropdown()
        voice_selector = self.create_voice_selector_row(voice_dropdown, "voice_category_dropdown")
        
        # 音色试听按钮
        if not hasattr(self, 'voice_sample_button') or self.voice_sample_button is None:
            self.voice_sample_button = ft.ElevatedButton("试听", icon=ft.Icons.PLAY_CIRCLE, on_click=self.toggle_voice_sample_playback, style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_50, color=ft.Colors.GREEN_800))
        
        # 批量设置
        self.bulk_random_role_voices_checkbox = ft.Checkbox(label="随机匹配角色库音色", value=False)
        self.bulk_generate_srt_checkbox = ft.Checkbox(label="生成SRT字幕", value=True)

        # 音频参数滑块
        sp_val = float(self.config_manager.get("speaking_speed", 1.0))
        vp_val = int(self.config_manager.get("volume_percent", 100))
        
        self.bulk_speed_text = ft.Text(f"{sp_val:.1f}x", size=12, width=40)
        def _on_bulk_speed(e):
            try:
                v = float(e.control.value)
                self.bulk_speed_text.value = f"{v:.1f}x"
                self.runtime_speaking_speed = v
                if self.page: self.page.update()
            except Exception: pass
        self.bulk_speed_slider = ft.Slider(min=0.5, max=2.0, divisions=30, value=sp_val, on_change=_on_bulk_speed, expand=True)

        self.bulk_volume_text = ft.Text(f"{vp_val}%", size=12, width=40)
        def _on_bulk_volume(e):
            try:
                v = int(e.control.value)
                self.bulk_volume_text.value = f"{v}%"
                self.runtime_volume_percent = v
                if self.page: self.page.update()
            except Exception: pass
        self.bulk_volume_slider = ft.Slider(min=50, max=200, divisions=150, value=float(vp_val), on_change=_on_bulk_volume, expand=True)

        # 情感权重
        self.bulk_emo_weight_label = ft.Text("情感权重: 0.65", size=12)
        def _on_bulk_emo_change(e):
            try:
                v = float(e.control.value)
                self.bulk_emo_weight_label.value = f"情感权重: {v:.2f}"
                if getattr(self, 'page', None): self.page.update()
            except Exception: pass
        self.bulk_emo_weight_slider = ft.Slider(min=0.0, max=1.0, divisions=100, value=0.65, label="{value}", on_change=_on_bulk_emo_change, expand=True)

        # 情感向量 (紧凑布局)
        self.bulk_vec_sliders = []
        self.bulk_vec_value_fields = []
        bulk_vec_cells = []
        bulk_names = getattr(self, 'vec_names', ["喜","怒","哀","惧","厌恶","低落","惊喜","平静"]) 
        bulk_emojis = getattr(self, 'vec_emojis', {})
        
        for i, name in enumerate(bulk_names):
            val_text = ft.Text("0.00", size=10, text_align=ft.TextAlign.RIGHT, width=30)
            sld = ft.Slider(min=0.0, max=1.0, divisions=None, value=0.0, height=20, expand=True)
            def _on_bulk_vec_change(e, vt=val_text):
                try:
                    vv = float(e.control.value)
                except Exception:
                    vv = 0.0
                vt.value = f"{vv:.2f}"
                if self.page:
                    try: self.page.update()
                    except Exception: pass
            sld.on_change = _on_bulk_vec_change
            self.bulk_vec_sliders.append(sld)
            self.bulk_vec_value_fields.append(val_text)
            
            cell = ft.Container(
                content=ft.Row([
                    ft.Text(f"{bulk_emojis.get(name, '')}{name}", size=11, width=30),
                    sld,
                    val_text
                ], spacing=2, alignment=ft.MainAxisAlignment.START),
                padding=2,
                bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.BLUE_GREY),
                border_radius=4,
                expand=True
            )
            bulk_vec_cells.append(cell)

        bulk_vec_rows = []
        for j in range(0, len(bulk_vec_cells), 2):
            cells = [bulk_vec_cells[j]]
            if j + 1 < len(bulk_vec_cells):
                cells.append(bulk_vec_cells[j+1])
            bulk_vec_rows.append(ft.Row(cells, spacing=5))

        params_card = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.TUNE, color=ft.Colors.TEAL),
                        title=ft.Text("参数配置", weight=ft.FontWeight.BOLD),
                        subtitle=ft.Text("音色、语速、音量及情感设置"),
                        content_padding=0
                    ),
                    ft.Divider(height=1),
                    ft.Text("基础音色:", size=13, weight=ft.FontWeight.BOLD),
                    voice_selector,
                    ft.Row([self.voice_sample_button, ft.IconButton(icon=ft.Icons.REFRESH, tooltip="刷新", on_click=self.refresh_voices)], spacing=10),
                    ft.Divider(height=1),
                    ft.Row([self.bulk_random_role_voices_checkbox, self.bulk_generate_srt_checkbox], spacing=10),
                    ft.Divider(height=1),
                    ft.Row([ft.Icon(ft.Icons.SPEED, size=16), ft.Text("语速", size=12), self.bulk_speed_slider, self.bulk_speed_text], spacing=5),
                    ft.Row([ft.Icon(ft.Icons.VOLUME_UP, size=16), ft.Text("音量", size=12), self.bulk_volume_slider, self.bulk_volume_text], spacing=5),
                    ft.Row([ft.Icon(ft.Icons.EMOJI_EMOTIONS, size=16), self.bulk_emo_weight_label, self.bulk_emo_weight_slider], spacing=5),
                    ft.ExpansionTile(
                        title=ft.Text("情感向量微调", size=13),
                        subtitle=ft.Text("展开设置8维情感向量", size=11),
                        controls=[ft.Container(content=ft.Column(bulk_vec_rows, spacing=4), padding=10)],
                        initially_expanded=False,
                        dense=True
                    )
                ], spacing=10),
                padding=15,
            ),
            elevation=2
        )

        left_column = ft.Column([file_config_card, params_card], spacing=10, scroll=ft.ScrollMode.AUTO)

        # --- 右侧：任务与日志 ---

        # 文件列表
        self.bulk_files_list = ft.ListView(spacing=2, height=200, auto_scroll=False)
        self.update_bulk_files_list()

        # 进度与状态
        self.bulk_status = "准备就绪"
        self.bulk_status_text = ft.Text(self.bulk_status, size=12, color=ft.Colors.BLUE)
        self.bulk_progress_bar = ft.ProgressBar(value=0.0, height=6, color=ft.Colors.GREEN)
        self.bulk_progress_text = ft.Text("0%", size=12)
        self.bulk_wait_ring = ft.ProgressRing(visible=False, width=16, height=16)

        # 控制按钮
        self.bulk_start_btn = ft.ElevatedButton("开始生成", icon=ft.Icons.PLAY_ARROW, on_click=self.start_bulk_generation, style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE))
        self.bulk_stop_btn = ft.ElevatedButton("停止生成", icon=ft.Icons.STOP, on_click=self.stop_bulk_generation, disabled=True, style=ft.ButtonStyle(bgcolor=ft.Colors.RED_100, color=ft.Colors.RED))

        # 日志
        self.bulk_log_list = ft.ListView(spacing=2, expand=True, auto_scroll=True)

        task_card = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.PLAYLIST_PLAY, color=ft.Colors.ORANGE),
                        title=ft.Text("任务队列", weight=ft.FontWeight.BOLD),
                        subtitle=ft.Text("待处理文件列表"),
                        content_padding=0
                    ),
                    ft.Divider(height=1),
                    ft.Container(
                        content=self.bulk_files_list,
                        bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.BLACK),
                        border_radius=6,
                        padding=5,
                        height=200
                    ),
                    ft.Divider(height=1),
                    ft.Row([self.bulk_start_btn, self.bulk_stop_btn, ft.Container(expand=True), self.bulk_wait_ring, self.bulk_status_text], spacing=10, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Column([self.bulk_progress_bar, ft.Row([ft.Container(expand=True), self.bulk_progress_text])], spacing=2),
                ], spacing=10),
                padding=15,
            ),
            elevation=2
        )

        log_card = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.RECEIPT_LONG, color=ft.Colors.GREY),
                        title=ft.Text("执行日志", weight=ft.FontWeight.BOLD),
                        content_padding=0
                    ),
                    ft.Divider(height=1),
                    ft.Container(
                        content=self.bulk_log_list,
                        bgcolor=ft.Colors.BLACK12 if not self.page or self.page.theme_mode == ft.ThemeMode.LIGHT else ft.Colors.BLACK87,
                        border_radius=6,
                        padding=10,
                        expand=True
                    )
                ], spacing=10, expand=True),
                padding=15,
                expand=True
            ),
            elevation=2,
            expand=True
        )

        right_column = ft.Column([task_card, log_card], spacing=10, expand=True)

        return ft.Container(
            content=ft.Row([
                ft.Container(content=left_column, width=500), # 固定左侧宽度
                ft.Container(content=right_column, expand=True)
            ], spacing=15, expand=True, vertical_alignment=ft.CrossAxisAlignment.START),
            padding=15,
            expand=True,
        )

    def on_bulk_pick_files_result(self, e: ft.FilePickerResultEvent):
        try:
            files = e.files or []
            self.bulk_selected_files = [f.path for f in files]
            if self.bulk_selected_files:
                try:
                    import os as _os
                    self.bulk_common_base = _os.path.commonpath(self.bulk_selected_files)
                except Exception:
                    self.bulk_common_base = None
            self.update_bulk_files_list()
            self.page.update()
        except Exception as ex:
            self.show_message(f"选择文件失败: {ex}", True)

    def on_bulk_pick_output_dir_result(self, e: ft.FilePickerResultEvent):
        try:
            dir_path = e.path or ''
            if dir_path:
                self.bulk_output_dir = dir_path
                self.bulk_output_dir_field.value = dir_path
            self.page.update()
        except Exception as ex:
            self.show_message(f"选择输出目录失败: {ex}", True)

    def open_bulk_output_dir(self, e=None):
        try:
            if not getattr(self, 'bulk_output_dir', None):
                self.show_message("请先选择输出目录", True)
                return
            if not os.path.isdir(self.bulk_output_dir):
                self.show_message("输出目录不存在", True)
                return
            subprocess.run(['explorer', str(self.bulk_output_dir)], capture_output=True, text=True)
            self.show_message(f"已打开输出文件夹: {self.bulk_output_dir}")
        except Exception as ex:
            self.show_message(f"打开输出文件夹失败: {ex}", True)

    def update_bulk_files_list(self):
        try:
            items = []
            for p in (self.bulk_selected_files or []):
                try:
                    size = os.path.getsize(p)
                    items.append(ft.Row([ft.Icon(ft.Icons.INSERT_DRIVE_FILE, color=ft.Colors.BLUE_GREY, size=16), ft.Text(f"{os.path.basename(p)}", size=12), ft.Text(f"{size} bytes", size=12, color=ft.Colors.GREY_600)], spacing=8))
                except Exception:
                    items.append(ft.Row([ft.Icon(ft.Icons.INSERT_DRIVE_FILE, color=ft.Colors.BLUE_GREY, size=16), ft.Text(f"{os.path.basename(p)}", size=12)], spacing=8))
            if hasattr(self, 'bulk_files_list') and self.bulk_files_list:
                self.bulk_files_list.controls = items
        except Exception:
            pass

    def start_bulk_generation(self, e=None):
        try:
            if not self.bulk_selected_files:
                self.show_message("请先选择文稿文件", True); return
            if not self.bulk_output_dir:
                self.show_message("请先选择输出目录", True); return
            # 选定音色
            voice_path = None
            if hasattr(self, 'voice_dropdown') and self.voice_dropdown and self.voice_dropdown.value:
                voice_path = self.voice_dropdown.value
            if not voice_path:
                voice_path = self.config_manager.get('last_voice')
            if not voice_path:
                if getattr(self, 'voice_files', None):
                    voice_path = str(getattr(self, 'voice_files')[0].absolute())
            try:
                if getattr(self, 'bulk_random_role_voices_checkbox', None) and self.bulk_random_role_voices_checkbox.value:
                    roles_map = self.config_manager.get('subtitle_roles', {}) or {}
                    role_voices = [v for v in roles_map.values() if v]
                    if role_voices:
                        import random
                        rv = random.choice(role_voices)
                        rp = self.resolve_voice_path_any(rv)
                        if rp:
                            voice_path = rp
            except Exception:
                pass
            if not voice_path or not os.path.exists(voice_path):
                self.show_message("未选择音色文件或音色文件不存在", True); return

            # 构建客户端
            api_mode = self.config_manager.get('tts_api_mode', 'local')
            client = None; remote_url = None; port = None
            try:
                if api_mode == 'remote':
                    remote_url = (self.config_manager.get('tts_remote_base_url', '') or '').strip()
                    client = Client(remote_url)
                else:
                    if self.instances:
                        port = list(self.instances.keys())[0]
                        client = Client(f"http://127.0.0.1:{port}/")
            except Exception as ex:
                self.show_message(f"无法建立TTS实例: {ex}", True); return
            if not client:
                self.show_message("请先启动TTS实例", True); return

            # 状态与按钮
            self.bulk_stop_flag = False
            self.bulk_status = "生成中"
            self.bulk_status_text.value = self.bulk_status
            self.bulk_start_btn.disabled = True
            self.bulk_stop_btn.disabled = False
            self.bulk_wait_ring.visible = True
            self.bulk_progress_bar.value = 0.0
            self.bulk_progress_text.value = "0%"
            self.page.update()

            # 启动后台线程
            def worker():
                total = len(self.bulk_selected_files)
                done = 0
                common_base = self.bulk_common_base
                for fp in list(self.bulk_selected_files):
                    if self.bulk_stop_flag:
                        self.bulk_log_list.controls.append(ft.Text("已停止", size=12, color=ft.Colors.RED))
                        break
                    try:
                        # 读取文本
                        text = self._read_text_from_file(fp)
                        if not text:
                            self.bulk_log_list.controls.append(ft.Text(f"跳过空文件: {os.path.basename(fp)}", size=12, color=ft.Colors.GREY_600))
                            self.page.update(); continue
                        # 更新提示音频
                        try:
                            client.predict(api_name="/update_prompt_audio")
                        except Exception:
                            pass
                        # 生成单段
                        voice_path_current = voice_path
                        try:
                            if getattr(self, 'bulk_random_role_voices_checkbox', None) and self.bulk_random_role_voices_checkbox.value:
                                roles_map = self.config_manager.get('subtitle_roles', {}) or {}
                                candidates = []
                                import random
                                for v in roles_map.values():
                                    rp = self.resolve_voice_path_any(v)
                                    if rp:
                                        candidates.append(rp)
                                if not candidates:
                                    candidates = [str(p.absolute()) for p in getattr(self, 'voice_files', []) or []]
                                if candidates:
                                    voice_path_current = random.choice(candidates)
                        except Exception:
                            pass
                        params = {
                            "prompt": handle_file(voice_path_current),
                            "text": text,
                            "emo_ref_path": None,
                            "emo_weight": float((getattr(self, 'bulk_emo_weight_slider', None) and self.bulk_emo_weight_slider.value) or (getattr(self, 'emo_weight_slider', None) and self.emo_weight_slider.value) or 0.65),
                            "vec1": float((self.bulk_vec_sliders[0].value if getattr(self, 'bulk_vec_sliders', None) else (getattr(self, 'vec_sliders', None) and self.vec_sliders[0].value or 0.0)) or 0.0),
                            "vec2": float((self.bulk_vec_sliders[1].value if getattr(self, 'bulk_vec_sliders', None) else (getattr(self, 'vec_sliders', None) and self.vec_sliders[1].value or 0.0)) or 0.0),
                            "vec3": float((self.bulk_vec_sliders[2].value if getattr(self, 'bulk_vec_sliders', None) else (getattr(self, 'vec_sliders', None) and self.vec_sliders[2].value or 0.0)) or 0.0),
                            "vec4": float((self.bulk_vec_sliders[3].value if getattr(self, 'bulk_vec_sliders', None) else (getattr(self, 'vec_sliders', None) and self.vec_sliders[3].value or 0.0)) or 0.0),
                            "vec5": float((self.bulk_vec_sliders[4].value if getattr(self, 'bulk_vec_sliders', None) else (getattr(self, 'vec_sliders', None) and self.vec_sliders[4].value or 0.0)) or 0.0),
                            "vec6": float((self.bulk_vec_sliders[5].value if getattr(self, 'bulk_vec_sliders', None) else (getattr(self, 'vec_sliders', None) and self.vec_sliders[5].value or 0.0)) or 0.0),
                            "vec7": float((self.bulk_vec_sliders[6].value if getattr(self, 'bulk_vec_sliders', None) else (getattr(self, 'vec_sliders', None) and self.vec_sliders[6].value or 0.0)) or 0.0),
                            "vec8": float((self.bulk_vec_sliders[7].value if getattr(self, 'bulk_vec_sliders', None) else (getattr(self, 'vec_sliders', None) and self.vec_sliders[7].value or 0.0)) or 0.0),
                            "emo_text": "",
                            "emo_random": False,
                            "max_text_tokens_per_segment": int(self.config_manager.get("gui_seg_tokens", 120)),
                            "api_name": "/gen_single",
                        }
                        result = self._predict_with_emo_choice(client, params, "Same as the voice reference", "与音色参考音频相同")
                        # 保存到输出目录，保持结构与命名
                        rel = os.path.basename(fp)
                        try:
                            if common_base:
                                rel = os.path.relpath(fp, common_base)
                        except Exception:
                            rel = os.path.basename(fp)
                        rel_dir = os.path.dirname(rel)
                        dest_dir = os.path.join(self.bulk_output_dir, rel_dir)
                        os.makedirs(dest_dir, exist_ok=True)
                        stem = Path(fp).stem
                        origext = Path(fp).suffix.lstrip('.')
                        dest_name = f"{stem}.{origext}.wav"
                        saved = self.save_audio_from_result(result, dest_dir, dest_filename=dest_name, base_url=(remote_url if api_mode=='remote' else None))
                        if saved and os.path.isfile(saved):
                            try:
                                sp = float((getattr(self, 'bulk_speed_slider', None) and self.bulk_speed_slider.value) or (getattr(self, 'runtime_speaking_speed', None) or self.config_manager.get('speaking_speed', 1.0)))
                                self.apply_speaking_speed_value(saved, sp)
                                self.apply_volume(saved)
                            except Exception:
                                pass
                            try:
                                if getattr(self, 'bulk_generate_srt_checkbox', None) and self.bulk_generate_srt_checkbox.value:
                                    self.write_simple_srt_from_text(saved, text)
                                
                            except Exception:
                                pass
                            try:
                                self.add_generation_record(saved, os.path.basename(fp))
                            except Exception:
                                pass
                            self.bulk_log_list.controls.append(ft.Text(f"已生成: {saved}", size=12, color=ft.Colors.GREEN))
                        else:
                            self.bulk_log_list.controls.append(ft.Text(f"保存失败: {dest_name}", size=12, color=ft.Colors.RED))
                        done += 1
                        self.bulk_progress_bar.value = done/total
                        self.bulk_progress_text.value = f"{int((done/total)*100)}%"
                        self.page.update()

                        # 内存预警
                        try:
                            mem_mb = self._get_memory_usage_mb()
                            if mem_mb and mem_mb > 1500:
                                self.show_message(f"内存占用已超过阈值: {int(mem_mb)}MB", True)
                        except Exception:
                            pass
                    except Exception as ex:
                        self.bulk_log_list.controls.append(ft.Text(f"生成失败: {os.path.basename(fp)} - {ex}", size=12, color=ft.Colors.RED))
                        self.page.update()
                # 完成状态
                self.bulk_status = "空闲"
                self.bulk_status_text.value = self.bulk_status
                self.bulk_start_btn.disabled = False
                self.bulk_stop_btn.disabled = True
                # 恢复按钮状态
                self.bulk_wait_ring.visible = False
                self.page.update()

            self.page.run_thread(worker)
        except Exception as ex:
            self.show_message(f"启动批量生成失败: {ex}", True)

    def stop_bulk_generation(self, e=None):
        self.bulk_stop_flag = True
        self.bulk_status = "停止中"
        self.bulk_status_text.value = self.bulk_status
        self.bulk_stop_btn.disabled = True
        self.page.update()

    # 暂停/继续已移除：API调用不可中断，仅支持强制停止

    def _read_text_from_file(self, path: str) -> str:
        try:
            if path.lower().endswith('.txt'):
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            if path.lower().endswith('.docx'):
                return ""
            return ""
        except Exception:
            return ""

    def _get_memory_usage_mb(self):
        try:
            import psutil, os as _os
            p = psutil.Process(_os.getpid())
            return p.memory_info().rss / (1024*1024)
        except Exception:
            try:
                import tracemalloc
                tracemalloc.start()
                cur, _ = tracemalloc.get_traced_memory()
                return cur / (1024*1024)
            except Exception:
                return None

    def parse_podcast_script(self, e=None):
        try:
            text = (self.podcast_script_input.value or '').strip()
            if not text:
                self.show_message("请先输入播客脚本", True)
                return
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            segs = []
            mode = getattr(self.podcast_unlabeled_mode_dropdown, 'value', '默认A')
            toggle_a = True
            import re
            sp_map = {
                'A': ['A', '甲', '男', '主持人'],
                'B': ['B', '乙', '女', '嘉宾'],
                'C': ['C', '丙', '旁白'],
                'D': ['D', '丁', '其他']
            }
            labels_list = sorted(sum(sp_map.values(), []), key=len, reverse=True)
            labels = '|'.join(map(re.escape, labels_list))
            pat = re.compile(rf"^({labels})\s*[：:\-—\)）、]\s*(.*)$")
            
            # 循环交替计数器
            alt_idx = 0
            
            for i, ln in enumerate(lines):
                sp = None
                m = pat.match(ln)
                if m:
                    label = m.group(1)
                    ln = m.group(2).strip()
                    if label in sp_map['A']: sp = 'A'
                    elif label in sp_map['B']: sp = 'B'
                    elif label in sp_map['C']: sp = 'C'
                    elif label in sp_map['D']: sp = 'D'
                    else: sp = 'A'
                else:
                    if mode == '默认A':
                        sp = 'A'
                    elif mode == '默认B':
                        sp = 'B'
                    elif mode == '默认C':
                        sp = 'C'
                    elif mode == '默认D':
                        sp = 'D'
                    elif mode == '交替AB':
                        sp = ('A' if alt_idx % 2 == 0 else 'B')
                        alt_idx += 1
                    elif mode == 'ABC交替':
                        mod = alt_idx % 3
                        sp = 'A' if mod == 0 else ('B' if mod == 1 else 'C')
                        alt_idx += 1
                    elif mode == 'ABCD交替':
                        mod = alt_idx % 4
                        sp = 'A' if mod == 0 else ('B' if mod == 1 else ('C' if mod == 2 else 'D'))
                        alt_idx += 1
                    else:
                        sp = 'A'
                segs.append({'speaker': sp, 'text': ln})
            self.podcast_segments = segs
            self.podcast_segments_preview.controls.clear()
            for s in segs:
                self.podcast_segments_preview.controls.append(ft.Text(f"{s['speaker']}: {s['text']}", color=ft.Colors.BLUE_200, size=12))
            self.page.update()
            self.show_message(f"解析完成，共 {len(segs)} 段")
        except Exception as ex:
            self.show_message(f"解析脚本失败: {ex}", True)

    def start_podcast_generation(self, e=None):
        try:
            if getattr(self, 'podcast_generating', False):
                self.show_message("正在生成播客，请勿重复点击", True)
                return
            self.podcast_generating = True
            try:
                if getattr(self, 'podcast_gen_btn', None):
                    self.podcast_gen_btn.disabled = True
                if getattr(self, 'podcast_progress', None):
                    self.podcast_progress.value = 0
                if getattr(self, 'podcast_status', None):
                    self.podcast_status.value = "正在生成 0/0"
                if getattr(self, 'page', None):
                    self.page.update()
            except Exception:
                pass
            segs = getattr(self, 'podcast_segments', None)
            if not segs:
                self.show_message("请先解析脚本", True)
                self.podcast_generating = False
                if getattr(self, 'podcast_gen_btn', None):
                    self.podcast_gen_btn.disabled = False
                if getattr(self, 'page', None):
                    self.page.update()
                return
            voice_a = self.podcast_voice_a_dropdown.value
            voice_b = self.podcast_voice_b_dropdown.value
            voice_c = self.podcast_voice_c_dropdown.value
            voice_d = self.podcast_voice_d_dropdown.value
            
            if not voice_a:
                self.show_message("请选择说话人A音色", True)
                return
            if any(s['speaker'] == 'B' for s in segs) and not voice_b:
                self.show_message("请选择说话人B音色", True)
                return
            if any(s['speaker'] == 'C' for s in segs) and not voice_c:
                self.show_message("请选择说话人C音色", True)
                return
            if any(s['speaker'] == 'D' for s in segs) and not voice_d:
                self.show_message("请选择说话人D音色", True)
                return
            api_mode = self.config_manager.get('tts_api_mode', 'local')
            port = None
            remote_url = None
            if api_mode == 'remote':
                remote_url = self.config_manager.get('tts_remote_base_url', '').strip()
            else:
                if self.instances:
                    port = list(self.instances.keys())[0]
                else:
                    self.show_message("请先启动至少一个TTS实例", True)
                    return
            emo_weight = float(self.podcast_emo_weight.value or 0.65)
            style = self.podcast_style_dropdown.value
            style_text = {
                '无': '',
                '亲切随和': 'warm, friendly, intimate',
                '专业播报': 'professional, clear, steady',
                '轻松聊天': 'casual, lively, relaxed',
                '温柔叙述': 'soft, gentle, calm',
                '新闻播报': 'news, professional, objective',
                '情感故事': 'emotional, storytelling, deep',
                '悬疑惊悚': 'suspenseful, tense, mysterious',
            }.get(style, '')
            style_vecs = {
                '亲切随和': [0.3, 0.2, 0.0, 0.3, 0.0, 0.1, 0.2, 0.0],
                '专业播报': [0.0, -0.2, -0.1, 0.0, 0.1, -0.3, 0.0, 0.2],
                '轻松聊天': [0.4, 0.2, 0.1, 0.3, 0.1, 0.2, 0.3, 0.1],
                '温柔叙述': [0.1, 0.0, -0.1, 0.2, -0.2, 0.0, 0.1, 0.0],
            }
            timeline = AudioSegment.silent(duration=0)
            gap = AudioSegment.silent(duration=200)
            outputs_dir = os.path.join(os.getcwd(), 'outputs'); os.makedirs(outputs_dir, exist_ok=True)
            subtitles = []
            total = len(segs)
            done = 0
            for s in segs:
                text = s['text']
                if s['speaker'] == 'A': voice_path = voice_a
                elif s['speaker'] == 'B': voice_path = voice_b
                elif s['speaker'] == 'C': voice_path = voice_c
                elif s['speaker'] == 'D': voice_path = voice_d
                else: voice_path = voice_a
                
                client = None
                if api_mode == 'remote' and remote_url:
                    client = Client(remote_url)
                elif port:
                    client = Client(f"http://127.0.0.1:{port}/")
                if not client:
                    self.show_message("无法建立API客户端", True); return
                # 使用风格向量映射提升拟人化；否则回退同参考音色
                use_vec = style in style_vecs
                emo_method_label_local = ('使用情感向量控制' if use_vec else '与音色参考音频相同')
                emo_method_label_remote = ('Use emotion vectors' if use_vec else 'Same as the voice reference')
                try:
                    if use_vec:
                        v = style_vecs[style]
                        params = {
                            "prompt": handle_file(voice_path),
                            "text": text,
                            "emo_ref_path": None,
                            "emo_weight": emo_weight,
                            "vec1": v[0], "vec2": v[1], "vec3": v[2], "vec4": v[3], "vec5": v[4], "vec6": v[5], "vec7": v[6], "vec8": v[7],
                            "emo_text": '',
                            "emo_random": False,
                            "api_name": '/gen_single'
                        }
                        result = self._predict_with_emo_choice(client, params, emo_method_label_remote, emo_method_label_local)
                    else:
                        params = {
                            "prompt": handle_file(voice_path),
                            "text": text,
                            "emo_ref_path": None,
                            "emo_weight": emo_weight,
                            "vec1": 0, "vec2": 0, "vec3": 0, "vec4": 0, "vec5": 0, "vec6": 0, "vec7": 0, "vec8": 0,
                            "emo_text": style_text,
                            "emo_random": False,
                            "api_name": '/gen_single'
                        }
                        result = self._predict_with_emo_choice(client, params, emo_method_label_remote, emo_method_label_local)
                except Exception as gen_err:
                    self.log_manager.error(f"播客片段生成失败: {gen_err}")
                    continue
                saved = self.save_audio_from_result(result, outputs_dir, dest_filename=None, base_url=(remote_url if api_mode=='remote' else None))
                if saved and os.path.isfile(saved):
                    try:
                        start_ms = len(timeline)
                        seg_audio = AudioSegment.from_file(saved)
                        end = (text[-1] if text else '')
                        if end in ['。','！','？','.','!','?']:
                            gap_ms = 350; gap = AudioSegment.silent(duration=gap_ms)
                        elif end in ['，',',','；',';','…']:
                            gap_ms = 220; gap = AudioSegment.silent(duration=gap_ms)
                        else:
                            gap_ms = 150; gap = AudioSegment.silent(duration=gap_ms)
                        timeline = timeline + seg_audio + gap
                        end_ms = start_ms + len(seg_audio)
                        subtitles.append({"index": done + 1, "speaker": s['speaker'], "text": text, "start": start_ms, "end": end_ms})
                        done += 1
                        try:
                            if getattr(self, 'podcast_progress', None):
                                self.podcast_progress.value = done/total if total>0 else 0
                            if getattr(self, 'podcast_status', None):
                                self.podcast_status.value = f"已生成 {done}/{total}"
                            if getattr(self, 'page', None):
                                self.page.update()
                        except Exception:
                            pass
                    except Exception as lo_err:
                        self.log_manager.error(f"加载片段失败: {lo_err}")
            final = timeline
            try:
                bgm_path = (self.podcast_bgm_path.value or '').strip()
                if bgm_path and os.path.isfile(bgm_path):
                    bgm = AudioSegment.from_file(bgm_path)
                    try:
                        pct = int(getattr(self.podcast_bgm_percent_slider, 'value', 100))
                    except Exception:
                        pct = 100
                    scale = max(10, min(200, pct)) / 100.0
                    import math
                    gain_db = 20.0 * math.log10(scale)
                    bgm = bgm.apply_gain(gain_db)
                    bgm = bgm.fade_in(2000).fade_out(2000)
                    total_len = len(final)
                    bgm_base = AudioSegment.silent(duration=total_len)
                    offset = 0
                    while offset < total_len:
                        remain = total_len - offset
                        seg = bgm[:remain] if len(bgm) > remain else bgm
                        bgm_base = bgm_base.overlay(seg, position=offset)
                        offset += len(seg)
                    final = bgm_base.overlay(final)
            except Exception as bgm_err:
                self.log_manager.warning(f"背景音乐处理失败: {bgm_err}")
            out_ts = int(time.time())
            out_file = os.path.join(outputs_dir, f"podcast_{out_ts}.wav")
            try:
                final.export(out_file, format='wav')
                try:
                    self.apply_volume(out_file)
                except Exception:
                    pass
                try:
                    srt_path = os.path.join(outputs_dir, f"podcast_{out_ts}.srt")
                    def _fmt_ms(ms):
                        h = ms // 3600000; m = (ms % 3600000) // 60000; s = (ms % 60000) // 1000; t = ms % 1000
                        return f"{h:02d}:{m:02d}:{s:02d},{t:03d}"
                    with open(srt_path, 'w', encoding='utf-8') as f:
                        for entry in subtitles:
                            f.write(str(entry["index"]))
                            f.write("\n")
                            f.write(f"{_fmt_ms(entry['start'])} --> {_fmt_ms(entry['end'])}")
                            f.write("\n")
                            f.write(f"{entry['speaker']}: {entry['text']}")
                            f.write("\n\n")
                    self.podcast_subtitle_file = srt_path
                except Exception:
                    pass
                self.show_message(f"播客已生成: {out_file}")
                self.log_manager.info(f"播客生成完成: {out_file}")
                self.podcast_output_file = out_file
                try:
                    self.add_generation_record(out_file, "播客")
                except Exception:
                    pass
                try:
                    dest_dir = getattr(self, 'podcast_output_dir', None)
                    if dest_dir and os.path.isdir(dest_dir):
                        bn = os.path.basename(out_file)
                        dest_path = os.path.join(dest_dir, bn)
                        if os.path.exists(dest_path):
                            base, ext = os.path.splitext(bn)
                            idx = int(time.time())
                            dest_path = os.path.join(dest_dir, f"{base}_{idx}{ext}")
                        shutil.copy2(out_file, dest_path)
                except Exception:
                    pass
                try:
                    if getattr(self, 'podcast_progress', None):
                        self.podcast_progress.value = 1.0
                    if getattr(self, 'podcast_status', None):
                        self.podcast_status.value = "生成完成"
                    if getattr(self, 'page', None):
                        self.page.update()
                except Exception:
                    pass
            except Exception as exp_err:
                self.show_message(f"导出播客失败: {exp_err}", True)
        except Exception as ex:
            self.show_message(f"生成播客失败: {ex}", True)
        finally:
            try:
                self.podcast_generating = False
                if getattr(self, 'podcast_gen_btn', None):
                    self.podcast_gen_btn.disabled = False
                if getattr(self, 'page', None):
                    self.page.update()
            except Exception:
                pass

    def play_podcast_voice_sample(self, speaker):
        try:
            path = None
            if speaker == 'A': path = self.podcast_voice_a_dropdown.value
            elif speaker == 'B': path = self.podcast_voice_b_dropdown.value
            elif speaker == 'C': path = self.podcast_voice_c_dropdown.value
            elif speaker == 'D': path = self.podcast_voice_d_dropdown.value
            
            if not path or not os.path.isfile(path):
                self.show_message("请选择有效的音色文件", True)
                return
            
            if not pygame.mixer.get_init():
                pygame.mixer.init()

            # 切换停止
            if self.podcast_audition_playing == speaker and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
                self.podcast_audition_playing = None
                self._reset_audition_btn(speaker)
                return
            
            # 停止之前的播放
            old_speaker = self.podcast_audition_playing
            if old_speaker and old_speaker != speaker:
                 self._reset_audition_btn(old_speaker)
            
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()

            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            self.podcast_audition_playing = speaker
            
            btn = self._get_audition_btn(speaker)
            if btn:
                btn.icon = ft.Icons.STOP
                btn.update()
                
            import threading
            def _monitor(target):
                import time
                while True:
                    try:
                        if not pygame.mixer.get_init(): break
                        busy = pygame.mixer.music.get_busy()
                        current = getattr(self, 'podcast_audition_playing', None)
                        
                        if not busy:
                            break
                        if current != target:
                            break
                        time.sleep(0.1)
                    except Exception:
                        break
                
                try:
                    self._reset_audition_btn(target)
                    if getattr(self, 'podcast_audition_playing', None) == target:
                         self.podcast_audition_playing = None
                except Exception:
                    pass

            threading.Thread(target=_monitor, args=(speaker,), daemon=True).start()

        except Exception as e:
            self.show_message(f"试听失败: {e}", True)

    def _get_audition_btn(self, speaker):
        if speaker == 'A': return getattr(self, 'podcast_audition_a_btn', None)
        if speaker == 'B': return getattr(self, 'podcast_audition_b_btn', None)
        if speaker == 'C': return getattr(self, 'podcast_audition_c_btn', None)
        if speaker == 'D': return getattr(self, 'podcast_audition_d_btn', None)
        return None

    def _reset_audition_btn(self, speaker):
        try:
            btn = self._get_audition_btn(speaker)
            if btn:
                btn.icon = ft.Icons.PLAY_CIRCLE
                btn.update()
        except Exception:
            pass
        except Exception as e:
            self.show_message(f"试听失败: {e}", True)

    def play_podcast_output(self, e=None):
        try:
            if not self.podcast_output_file or not os.path.isfile(self.podcast_output_file):
                self.show_message("尚无生成结果可播放", True)
                return
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            # toggle: if currently playing, stop
            if self.podcast_playing_output and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
                self.podcast_playing_output = False
                try:
                    if getattr(self, 'podcast_play_btn', None):
                        self.podcast_play_btn.text = "播放生成结果"
                        self.podcast_play_btn.icon = ft.Icons.VOLUME_UP
                    if getattr(self, 'page', None):
                        self.page.update()
                except Exception:
                    pass
                return
            # start playing
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
            pygame.mixer.music.load(self.podcast_output_file)
            pygame.mixer.music.play()
            self.podcast_playing_output = True
            try:
                if getattr(self, 'podcast_play_btn', None):
                    self.podcast_play_btn.text = "停止播放结果"
                    self.podcast_play_btn.icon = ft.Icons.STOP
                if getattr(self, 'page', None):
                    self.page.update()

                # Start monitor thread
                import threading
                def _monitor_output():
                    import time
                    while True:
                        try:
                            if not pygame.mixer.get_init() or not pygame.mixer.music.get_busy():
                                break
                            time.sleep(0.5)
                        except Exception:
                            break
                    # reset UI
                    try:
                        self.podcast_playing_output = False
                        if getattr(self, 'podcast_play_btn', None):
                            self.podcast_play_btn.text = "播放结果"
                            self.podcast_play_btn.icon = ft.Icons.VOLUME_UP
                        if getattr(self, 'page', None):
                            self.page.update()
                    except Exception:
                        pass
                threading.Thread(target=_monitor_output, daemon=True).start()

            except Exception:
                pass
        except Exception as e:
            self.show_message(f"播放失败: {e}", True)

    def play_bgm_sample(self, e=None):
        try:
            path = (self.podcast_bgm_path.value or '').strip()
            if not path or not os.path.isfile(path):
                self.show_message("请选择背景音乐", True)
                return
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            
            # toggle logic
            if self.podcast_bgm_audition_playing and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
                self.podcast_bgm_audition_playing = False
                try:
                    if getattr(self, 'podcast_bgm_audition_btn', None):
                        self.podcast_bgm_audition_btn.text = "试听背景音"
                        self.podcast_bgm_audition_btn.icon = ft.Icons.PLAY_CIRCLE
                    if getattr(self, '_bgm_audition_temp', None):
                        try:
                            if os.path.isfile(self._bgm_audition_temp):
                                os.remove(self._bgm_audition_temp)
                        except Exception:
                            pass
                        self._bgm_audition_temp = None
                    if getattr(self, 'page', None):
                        self.page.update()
                except Exception:
                    pass
                return

            # Start new playback
            try:
                seg = AudioSegment.from_file(path)
                try:
                    pct = int(getattr(self.podcast_bgm_percent_slider, 'value', 100))
                except Exception:
                    pct = 100
                scale = max(10, min(200, pct)) / 100.0
                import math
                gain_db = 20.0 * math.log10(scale)
                seg = seg.apply_gain(gain_db).fade_in(300)
                sample_len = min(len(seg), 12000)
                seg = seg[:sample_len]
                import tempfile
                tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                tmp_path = tmp.name
                tmp.close()
                seg.export(tmp_path, format='wav')
                self._bgm_audition_temp = tmp_path
                
                if pygame.mixer.music.get_busy():
                    pygame.mixer.music.stop()
                pygame.mixer.music.load(tmp_path)
                pygame.mixer.music.play()
                self.podcast_bgm_audition_playing = True
                
                try:
                    if getattr(self, 'podcast_bgm_audition_btn', None):
                        self.podcast_bgm_audition_btn.text = "停止背景音试听"
                        self.podcast_bgm_audition_btn.icon = ft.Icons.STOP
                    if getattr(self, 'page', None):
                        self.page.update()
                    
                    # Start monitor thread
                    import threading
                    def _monitor_bgm():
                        import time
                        while True:
                            try:
                                if not pygame.mixer.get_init() or not pygame.mixer.music.get_busy():
                                    break
                                time.sleep(0.5)
                            except Exception:
                                break
                        # reset UI
                        try:
                            self.podcast_bgm_audition_playing = False
                            if getattr(self, 'podcast_bgm_audition_btn', None):
                                self.podcast_bgm_audition_btn.text = "试听背景音"
                                self.podcast_bgm_audition_btn.icon = ft.Icons.PLAY_CIRCLE
                            if getattr(self, '_bgm_audition_temp', None):
                                try:
                                    if os.path.isfile(self._bgm_audition_temp):
                                        os.remove(self._bgm_audition_temp)
                                except Exception:
                                    pass
                                self._bgm_audition_temp = None
                            if getattr(self, 'page', None):
                                self.page.update()
                        except Exception:
                            pass
                    threading.Thread(target=_monitor_bgm, daemon=True).start()

                except Exception:
                    pass
            except Exception as ex:
                self.show_message(f"试听失败: {ex}", True)
        except Exception as e:
            self.show_message(f"试听失败: {e}", True)

    def open_output_location(self, e=None):
        try:
            path = getattr(self, 'podcast_output_file', None)
            if not path or not os.path.isfile(path):
                self.show_message("尚无生成结果", True)
                return
            try:
                subprocess.Popen(["explorer", "/select,", path])
            except Exception:
                os.startfile(os.path.dirname(path))
        except Exception as ex:
            self.show_message(f"打开失败: {ex}", True)

    def _predict_with_emo_choice(self, client, params, label_en, label_zh):
        # Prefer Chinese choices; keep api_name if present
        try:
            p = dict(params)
            # p.pop("api_name", None)  # Don't remove api_name to avoid ambiguity error
            p["emo_control_method"] = label_zh
            return client.predict(**p)
        except Exception as e_zh:
            try:
                if hasattr(self, 'log_manager'):
                    self.log_manager.info("中文选项调用失败，已切换英文模式继续生成")
            except Exception:
                pass
            try:
                p = dict(params)
                # p.pop("api_name", None) # Don't remove api_name
                p["emo_control_method"] = label_en
                return client.predict(**p)
            except Exception:
                raise e_zh



    # 口语化已移除
    
    # 字幕生成相关事件处理函数
    def on_subtitle_text_change(self, e):
        """文章内容变化时的处理"""
        try:
            now = time.time()
            last = getattr(self, "_last_subtitle_update_time", 0.0)
            if now - last < 0.3:
                return
            self._last_subtitle_update_time = now
        except Exception:
            pass
        
        # 临时保存输入的文本，不写入配置
        if self.subtitle_text_input:
            self.temp_subtitle_text = self.subtitle_text_input.value

        if self.subtitle_text_input and self.subtitle_text_input.value:
            src = self.subtitle_text_input.value
            mode = (self.split_mode_dropdown.value if self.split_mode_dropdown else "智能分句")
            if mode == "按标点分割":
                segments = self.split_text_by_punctuation(src)
            elif mode == "不分割":
                segments = [src]
            else:
                segments = self.split_text_intelligently(src)
            self.subtitle_segments = segments
            # 初始化或对齐每行情感向量缓存
            if not hasattr(self, 'subtitle_line_emotions'):
                self.subtitle_line_emotions = {}
            new_emotions = {}
            for i in range(len(segments)):
                prev = self.subtitle_line_emotions.get(i)
                if isinstance(prev, list) and len(prev) >= 8:
                    new_emotions[i] = [float(prev[j]) if j < 8 else 0.0 for j in range(8)]
                else:
                    new_emotions[i] = [0.0] * 8
            self.subtitle_line_emotions = new_emotions
            async def _update_subtitles():
                self.update_subtitle_preview_simple()
            self.page.run_task(_update_subtitles)
    

    
    def calculate_character_length(self, text):
        return calculate_character_length(text)

    def split_text_by_20_chars(self, text, role=None):
        """
        按照配置的最多汉字进行二次分割
        保持同一音色，每行不超过配置的上限（默认25汉字）
        """
        if not text:
            return []
        
        # 清理文本，移除多余的空白字符
        text = text.strip()
        if not text:
            return []
        
        segments = []
        current_segment = ""
        
        # 定义自然分割点（优先级从高到低）
        sentence_endings = ['。', '！', '？', '；', '…', '.', '!', '?']
        natural_pauses = ['，', '、', '：', ',', ':']
        
        def find_best_split_position(segment):
            """在段落中找到最佳分割位置"""
            # 从后往前查找，优先在句子结束标点处分割
            for i in range(len(segment) - 1, -1, -1):
                if segment[i] in sentence_endings:
                    return i + 1
            
            # 如果没有句子结束标点，查找自然停顿标点
            for i in range(len(segment) - 1, -1, -1):
                if segment[i] in natural_pauses:
                    return i + 1
            
            # 如果都没有，返回-1表示没有找到合适的分割点
            return -1
        
        i = 0
        while i < len(text):
            char = text[i]
            current_segment += char
            current_length = self.calculate_character_length(current_segment)
            
            # 如果当前段落达到或超过上限汉字（上限*2字符）
            try:
                max_cn = int(self.config_manager.get("ai_seg_max_cn", 25))
            except Exception:
                max_cn = 25
            if current_length >= max_cn * 2:
                # 尝试找到最佳分割位置
                split_pos = find_best_split_position(current_segment)
                
                if split_pos > 0 and split_pos < len(current_segment):
                    # 在找到的位置分割
                    segments.append(current_segment[:split_pos].strip())
                    current_segment = current_segment[split_pos:].strip()
                else:
                    # 如果没有找到合适的分割点，强制在当前位置分割
                    segments.append(current_segment.strip())
                    current_segment = ""
            
            i += 1
        
        # 处理剩余内容
        if current_segment.strip():
            segments.append(current_segment.strip())
        
        # 过滤空段落并确保每个段落都不为空
        result = [seg for seg in segments if seg.strip()]
        
        # 如果没有分割结果，返回原文本
        if not result:
            result = [text]
        
        return result

    def split_text_intelligently(self, text):
        """智能分句功能"""
        if not text:
            return []
        
        # 清理文本，移除多余的空白字符
        text = re.sub(r'\s+', '', text.strip())
        
        # 定义句子结束标点（优先级最高）
        sentence_endings = ['。', '！', '？', '；', '…', '.', '!', '?']
        # 定义自然停顿标点（中等优先级）
        natural_pauses = ['，', '、', '：', ',', ':']
        # 定义引号结束标点（需要特殊处理）
        quote_endings = ['"', '"', ''', ''', ')', '）', '}', '】', '>', '》', ')', '}', ']', '>']
        # 定义引号开始标点
        quote_starts = ['"', '"', ''', ''', '(', '（', '{', '【', '<', '《', '"', "'", '(', '{', '[', '<']
        
        segments = []
        current_segment = ""
        quote_stack = []  # 用于跟踪引号配对
        
        def is_english_word_boundary(text, pos):
            """检查指定位置是否为英文单词边界"""
            if pos <= 0 or pos >= len(text):
                return True
            
            current_char = text[pos]
            prev_char = text[pos - 1]
            
            # 如果当前字符或前一个字符是字母或数字，则不是边界
            if (current_char.isalnum() and prev_char.isalnum()):
                return False
            
            return True
        
        def is_in_quotes():
            """检查当前是否在引号内"""
            return len(quote_stack) > 0
        
        def find_natural_split_position(segment):
            """找到最自然的分割位置"""
            # 如果在引号内，不分割
            if is_in_quotes():
                return -1
            
            # 优先寻找句子结束标点
            for i in range(len(segment) - 1, max(len(segment) - 15, -1), -1):
                if segment[i] in sentence_endings and is_english_word_boundary(segment, i + 1):
                    if segment[i] == '.' and i > 0 and i + 1 < len(segment) and segment[i - 1].isdigit() and segment[i + 1].isdigit():
                        continue
                    return i
            
            # 其次寻找自然停顿标点（逗号、顿号等）
            for i in range(len(segment) - 1, max(len(segment) - 12, -1), -1):  # 只在后12个字符中寻找
                if segment[i] in natural_pauses and is_english_word_boundary(segment, i + 1):
                    return i
            
            # 最后寻找引号结束标点
            for i in range(len(segment) - 1, max(len(segment) - 8, -1), -1):  # 只在后8个字符中寻找
                if segment[i] in quote_endings and is_english_word_boundary(segment, i + 1):
                    return i
            
            # 如果没有找到合适的标点，寻找空格或中英文边界
            for i in range(len(segment) - 1, max(len(segment) - 10, -1), -1):
                if segment[i] == ' ' or is_english_word_boundary(segment, i):
                    return i
            
            return -1
        
        for i, char in enumerate(text):
            current_segment += char
            current_length = self.calculate_character_length(current_segment)
            cpl_len = int((self.subtitle_cpl_chinese or 18) * 2)
            natural_min = int(cpl_len * 0.444)
            natural_max = int(cpl_len * 0.888)
            soft_threshold = cpl_len
            hard_threshold = int(cpl_len * 1.111)
            
            # 处理引号配对
            if char in quote_starts:
                quote_stack.append(char)
            elif char in quote_endings:
                if quote_stack:
                    quote_stack.pop()
            
            # 如果遇到句子结束标点，且不在引号内，直接分句
            if char in sentence_endings and not is_in_quotes():
                if not (char == '.' and i > 0 and i + 1 < len(text) and text[i - 1].isdigit() and text[i + 1].isdigit()):
                    if current_segment.strip():
                        segments.append(current_segment.strip())
                    current_segment = ""
                    quote_stack.clear()
            # 如果遇到自然停顿标点，且当前段落长度适中，且不在引号内，则分句
            elif char in natural_pauses and current_length >= natural_min and current_length <= natural_max and not is_in_quotes():
                if current_segment.strip():
                    segments.append(current_segment.strip())
                current_segment = ""
            # 如果当前段落超过设定字数，考虑分句
            elif current_length >= soft_threshold:
                # 寻找最自然的分割位置
                split_pos = find_natural_split_position(current_segment)
                
                if split_pos > 5:  # 如果找到合适的分割位置
                    segments.append(current_segment[:split_pos + 1].strip())
                    current_segment = current_segment[split_pos + 1:]
                    quote_stack.clear()  # 清空引号栈
                # 如果超过硬阈值还没找到合适分割点，强制分句
                elif current_length >= hard_threshold:
                    segments.append(current_segment.strip())
                    current_segment = ""
                    quote_stack.clear()  # 清空引号栈
        
        # 处理剩余内容
        if current_segment.strip():
            segments.append(current_segment.strip())
        r = [seg for seg in segments if seg]
        if getattr(self, 'quote_glue_enabled', True):
            r = self.apply_quote_glue(r)
        return r

    def parse_punctuation_set(self):
        try:
            raw = (self.punctuation_set_text.value or "").strip()
        except Exception:
            raw = ""
        if not raw:
            raw = "。 ！ ？ ； … ， 、 ： . ! ? , :"
        tokens = [t for t in raw.replace('\n',' ').split(' ') if t]
        # 去重但保留顺序
        seen = set()
        out = []
        for t in tokens:
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out

    def split_text_by_punctuation(self, text):
        if not text:
            return []
        text = text.strip()
        puncts = set(self.parse_punctuation_set())
        closing = set(["”", '"', "'", "）", ")", "】", "》", "]", "}", ">"])
        segments = []
        buf = ""
        i = 0
        n = len(text)
        while i < n:
            ch = text[i]
            buf += ch
            # 命中分割标点
            if ch in puncts:
                # 吸收连续同类或同属标点（如“……”或多标点串）
                j = i + 1
                while j < n and text[j] in puncts:
                    buf += text[j]
                    j += 1
                # 若启用引号粘合，再吸收右引号/括号链
                if getattr(self, 'quote_glue_enabled', True):
                    k = j
                    while k < n and text[k] in closing:
                        buf += text[k]
                        k += 1
                    i = k - 1
                else:
                    i = j - 1
                seg = buf.strip()
                if seg:
                    segments.append(seg)
                buf = ""
            i += 1
        if buf.strip():
            segments.append(buf.strip())
        # 清理：避免仅标点或仅右引号的孤立行
        cleaned = []
        for s in segments:
            if s and all((c in puncts or c in closing or c.isspace()) for c in s):
                if cleaned:
                    cleaned[-1] = cleaned[-1] + s
                else:
                    cleaned.append(s)
            else:
                cleaned.append(s)
        # 二次换行：按CPL进行软/硬阈值切分
        reflowed = []
        for s in cleaned:
            if self.calculate_character_length(s) <= int((self.subtitle_cpl_chinese or 18) * 2):
                reflowed.append(s)
            else:
                # 借用智能分句的后处理（利用自然分割优先与硬阈值）
                for part in self.split_text_intelligently(s):
                    if part:
                        reflowed.append(part)
        return reflowed

    def resegment_current_text(self, e=None):
        src = (self.subtitle_text_input.value or "").strip() if self.subtitle_text_input else ""
        if not src:
            return
        mode = (self.split_mode_dropdown.value if self.split_mode_dropdown else "智能分句")
        if mode == "按标点分割":
            segs = self.split_text_by_punctuation(src)
        elif mode == "不分割":
            segs = [src]
        else:
            segs = self.split_text_intelligently(src)
        self.subtitle_segments = segs
        try:
            self.update_subtitle_preview_simple()
        except Exception:
            self.update_subtitle_preview()

    def on_split_mode_change(self, e):
        self.resegment_current_text()

    def on_punctuation_set_change(self, e):
        mode = (self.split_mode_dropdown.value if self.split_mode_dropdown else "智能分句")
        if mode == "按标点分割":
            self.resegment_current_text()
        
    def apply_quote_glue(self, segments):
        closing = set(["”", '"', "’", "'", "）", ")", "】", "》", "]", "}", ">"])
        s = segments[:]
        for i in range(len(s) - 1):
            nxt = s[i + 1]
            if not nxt:
                continue
            j = 0
            while j < len(nxt) and nxt[j] in closing:
                s[i] = s[i] + nxt[j]
                j += 1
            s[i + 1] = nxt[j:].lstrip()
        return [x for x in s if x and x.strip()]
    
    def update_subtitle_preview_simple(self):
        """更新字幕预览（简洁版本，避免滚动问题）"""
        if not self.subtitle_preview:
            return
            
        self.subtitle_preview.controls.clear()
        
        for i, segment in enumerate(self.subtitle_segments):
            # 获取当前行的角色
            current_role = self.subtitle_line_roles.get(i, "未分配")
            
            # 根据角色设置背景色和边框
            bg_color = self.get_role_background_color(current_role, i)
            border_color = self.get_role_border_color(current_role)
            # 标签文字颜色统一使用“未分配”颜色
            chip_text_color = ft.Colors.WHITE
            
            # 创建简洁的显示行
            preview_text = segment[:50] + "..." if len(segment) > 50 else segment
            cn_count = self._cn_han_count(segment)
            danger = cn_count > int(self.subtitle_cpl_chinese or 18)
            warn = not danger and cn_count >= int((self.subtitle_cpl_chinese or 18) * 0.9)
            dark = self.is_dark_theme()
            count_color = (ft.Colors.RED_300 if dark else ft.Colors.RED_400) if danger else ((ft.Colors.ORANGE_300 if dark else ft.Colors.ORANGE_400) if warn else (ft.Colors.GREY_400 if dark else ft.Colors.GREY_600))
            count_text = ft.Text(f"({cn_count}字)", size=12, color=count_color)
            
            # 删除按钮
            delete_btn = ft.IconButton(
                icon=ft.Icons.DELETE,
                icon_color=ft.Colors.RED,
                tooltip="删除此行",
                on_click=lambda e, idx=i: self.delete_subtitle_line(e, idx)
            )
            
            role_options = [ft.dropdown.Option("未分配", "未分配")]
            try:
                role_options.extend([ft.dropdown.Option(r, r) for r in self.subtitle_roles.keys()])
                if current_role and current_role != "未分配" and current_role not in self.subtitle_roles:
                    role_options.append(ft.dropdown.Option(current_role, current_role))
            except Exception:
                pass
            role_dropdown = ft.Dropdown(
                value=current_role,
                options=role_options,
                width=120,
                text_size=12,
                dense=True,
                on_change=lambda e, idx=i: self.assign_role_to_line(idx, e.control.value),
            )
            
            # 创建文本显示区域（移除点击事件）
            text_container = ft.Container(
                content=ft.Text(preview_text, size=12, overflow=ft.TextOverflow.ELLIPSIS),
                expand=True,
            )
            
            # 创建行容器
            row_container = ft.Container(
                content=ft.Row([
                    ft.Text(
                        f"{i+1:02d}.",
                        width=40,
                        text_align=ft.TextAlign.RIGHT,
                        size=12,
                        color=ft.Colors.GREY_400 if self.is_dark_theme() else ft.Colors.GREY_700,
                    ),
                    text_container,
                    count_text,
                    role_dropdown,
                    delete_btn
                ], alignment=ft.MainAxisAlignment.START),
                bgcolor=(ft.Colors.with_opacity(0.06, ft.Colors.WHITE) if self.is_dark_theme() else ft.Colors.WHITE),
                border=ft.border.all(1, border_color),
                border_radius=5,
                padding=ft.padding.symmetric(horizontal=10, vertical=8),
                margin=ft.margin.only(bottom=2),
            )
            
            self.subtitle_preview.controls.append(row_container)
        
        # 操作按钮行
        self.batch_edit_button = ft.ElevatedButton(
            "批量编辑",
            icon=ft.Icons.EDIT_NOTE,
            on_click=self.safe_open_batch_edit_dialog,
            style=ft.ButtonStyle(
                color=ft.Colors.WHITE,
                bgcolor=ft.Colors.BLUE
            ),
            disabled=(not bool(self.subtitle_segments))
        )
        button_row = ft.Row([
            self.batch_edit_button,
            ft.ElevatedButton(
                "重新分割",
                icon=ft.Icons.SPLITSCREEN,
                on_click=self.resegment_current_text,
                style=ft.ButtonStyle(
                    color=ft.Colors.WHITE,
                    bgcolor=ft.Colors.INDIGO
                )
            ),
            ft.ElevatedButton(
                "添加新行",
                icon=ft.Icons.ADD,
                on_click=self.add_subtitle_line,
                style=ft.ButtonStyle(
                    color=ft.Colors.WHITE,
                    bgcolor=ft.Colors.GREEN
                )
            ),
        ], spacing=10, alignment=ft.MainAxisAlignment.CENTER)
        
        self.subtitle_preview.controls.append(button_row)
        
        try:
            if getattr(self.subtitle_preview, 'page', None):
                if getattr(self, 'batch_edit_button', None):
                    self.batch_edit_button.disabled = (not bool(self.subtitle_segments))
                self.subtitle_preview.update()
            elif getattr(self, 'page', None):
                # 控件尚未挂载到页面，跳过局部刷新
                pass
        except AssertionError:
            pass

    def update_subtitle_preview(self):
        """更新分句预览（可编辑，支持角色分配）"""
        if not self.subtitle_preview:
            return
        
        self.subtitle_preview.controls.clear()
        # 初始化编辑后的字幕列表
        self.edited_subtitles = self.subtitle_segments.copy()
        
        for i, segment in enumerate(self.subtitle_segments):
            dark = self.is_dark_theme()
            tf_border = ft.Colors.GREY_700 if dark else ft.Colors.GREY_300
            tf_focus_border = ft.Colors.BLUE_300 if dark else ft.Colors.BLUE_400
            # 创建可编辑的文本框
            text_field = ft.TextField(
                value=segment,
                multiline=True,
                min_lines=2,
                max_lines=4,
                text_size=14,
                border_color=tf_border,
                focused_border_color=tf_focus_border,
                on_change=lambda e, idx=i: self.on_subtitle_edit(e, idx),
                dense=True,
                expand=True,
            )
            
            # 创建角色分配下拉框
            current_role = self.subtitle_line_roles.get(i, "未分配")
            role_options = [ft.dropdown.Option("未分配", "未分配")]
            role_options.extend([ft.dropdown.Option(role, role) for role in self.subtitle_roles.keys()])
            
            role_dropdown = ft.Dropdown(
                label="角色",
                value=current_role,
                options=role_options,
                width=120,
                text_size=12,
                dense=True,
                on_change=lambda e, idx=i: self.assign_role_to_line(idx, e.control.value),
            )
            
            # 获取角色对应的音色信息
            role_voice_info = ""
            if current_role != "未分配" and current_role in self.subtitle_roles:
                voice_path = self.subtitle_roles[current_role]
                voice_name = os.path.basename(voice_path) if voice_path else "未选择"
                role_voice_info = f"音色: {voice_name}"
            
            # 创建角色信息显示
            role_info_text = ft.Text(
                role_voice_info,
                size=10,
                color=(ft.Colors.GREY_400 if dark else ft.Colors.GREY_600),
                italic=True,
            ) if role_voice_info else ft.Container()
            
            # 创建分句项容器
            segment_item = ft.Container(
                content=ft.Column([
                    # 头部信息行
                    ft.Row([
                        # 左侧信息
                        ft.Row([
                            ft.Text(f"{i+1:02d}.", size=12, color=(ft.Colors.GREY_400 if dark else ft.Colors.GREY_600), width=30),
                            self._build_char_count_text(segment, dark),
                        ], spacing=5),
                        # 中间角色选择
                        role_dropdown,
                        # 右侧操作按钮
                        ft.Row([
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE,
                                icon_size=16,
                                tooltip="删除此行",
                                on_click=lambda e, idx=i: self.delete_subtitle_line(e, idx),
                                icon_color=ft.Colors.RED_400,
                            ),
                        ], spacing=0),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    # 角色音色信息
                    role_info_text,
                    # 文本编辑框
                    text_field,
                ], spacing=5),
                padding=ft.padding.all(10),
                bgcolor=self.get_role_background_color(current_role, i),
                border_radius=5,
                border=ft.border.all(1, self.get_role_border_color(current_role)),
            )
            self.subtitle_preview.controls.append(segment_item)
        
        # 添加新增按钮
        add_button = ft.Container(
            content=ft.ElevatedButton(
                "添加新行",
                icon=ft.Icons.ADD,
                on_click=self.add_subtitle_line,
                style=ft.ButtonStyle(
                    color=ft.Colors.WHITE,
                    bgcolor=ft.Colors.GREEN_400
                )
            ),
            alignment=ft.alignment.center,
            padding=ft.padding.all(10),
        )
        self.subtitle_preview.controls.append(add_button)
        
        if hasattr(self, 'page') and self.page:
            self.page.update()
    
    def get_role_background_color(self, role_name, index):
        """根据角色获取背景颜色（适配浅/深色主题）"""
        dark = self.is_dark_theme()
        if role_name == "未分配":
            if dark:
                return ft.Colors.with_opacity(0.06, ft.Colors.WHITE) if index % 2 == 0 else ft.Colors.with_opacity(0.03, ft.Colors.WHITE)
            return ft.Colors.GREY_50 if index % 2 == 0 else ft.Colors.WHITE
        
        if dark:
            role_colors = {
                "旁白": ft.Colors.with_opacity(0.10, ft.Colors.BLUE),
                "男主": ft.Colors.with_opacity(0.10, ft.Colors.GREEN),
                "女主": ft.Colors.with_opacity(0.10, ft.Colors.PINK),
                "配角": ft.Colors.with_opacity(0.10, ft.Colors.ORANGE),
            }
            return role_colors.get(role_name, ft.Colors.with_opacity(0.10, ft.Colors.PURPLE))
        else:
            # 浅色主题的背景色
            role_colors = {
                "旁白": ft.Colors.BLUE_50,
                "男主": ft.Colors.GREEN_50,
                "女主": ft.Colors.PINK_50,
                "配角": ft.Colors.ORANGE_50,
            }
            return role_colors.get(role_name, ft.Colors.PURPLE_50)
    
    def get_role_border_color(self, role_name):
        """根据角色获取边框颜色（适配浅/深色主题）"""
        dark = self.is_dark_theme()
        if role_name == "未分配":
            return ft.Colors.GREY_700 if dark else ft.Colors.GREY_200
        
        if dark:
            role_colors = {
                "旁白": ft.Colors.BLUE_700,
                "男主": ft.Colors.GREEN_700,
                "女主": ft.Colors.PINK_700,
                "配角": ft.Colors.ORANGE_700,
            }
            return role_colors.get(role_name, ft.Colors.PURPLE_700)
        else:
            role_colors = {
                "旁白": ft.Colors.BLUE_200,
                "男主": ft.Colors.GREEN_200,
                "女主": ft.Colors.PINK_200,
                "配角": ft.Colors.ORANGE_200,
            }
            return role_colors.get(role_name, ft.Colors.PURPLE_200)

    def is_dark_theme(self):
        """判断当前页面是否处于深色模式"""
        try:
            if not hasattr(self, 'page') or not self.page:
                return False
            tm = self.page.theme_mode
            if tm == ft.ThemeMode.DARK:
                return True
            if tm == ft.ThemeMode.LIGHT:
                return False
            # system 模式下根据平台亮度判断
            return self.page.platform_brightness == ft.Brightness.DARK
        except Exception:
            return False
    
    def create_subtitle_edit_dialog(self, index, segment):
        """创建弹出式字幕编辑对话框"""
        # 创建编辑文本框
        edit_text_field = ft.TextField(
            value=segment,
            multiline=True,
            min_lines=5,
            max_lines=10,
            width=500,
            height=200,
            text_size=14,
            border_color=ft.Colors.BLUE_300,
            focused_border_color=ft.Colors.BLUE_600,
            hint_text="编辑字幕内容...",
        )
        
        # 字符数统计
        char_count_text = ft.Text(
            f"字符数: {len(segment)}",
            size=12,
            color=ft.Colors.GREY_600
        )
        
        def update_char_count(e):
            char_count_text.value = f"字符数: {len(e.control.value)}"
            char_count_text.update()
        
        edit_text_field.on_change = update_char_count
        
        # 角色选择区域
        current_role = self.subtitle_line_roles.get(index, "未分配")
        role_options = [ft.dropdown.Option("未分配", "未分配")]
        role_options.extend([ft.dropdown.Option(role, role) for role in self.subtitle_roles.keys()])
        
        role_dropdown = ft.Dropdown(
            label="选择角色",
            value=current_role,
            options=role_options,
            width=200,
            text_size=14,
        )
        
        # 角色音色信息显示
        role_voice_info = ft.Text(
            "",
            size=12,
            color=ft.Colors.GREY_600,
            italic=True,
        )
        
        def update_role_info(e):
            selected_role = e.control.value
            if selected_role != "未分配" and selected_role in self.subtitle_roles:
                voice_path = self.subtitle_roles[selected_role]
                voice_name = os.path.basename(voice_path) if voice_path else "未选择"
                role_voice_info.value = f"音色: {voice_name}"
            else:
                role_voice_info.value = ""
            role_voice_info.update()
        
        role_dropdown.on_change = update_role_info
        
        # 对话框内容
        dialog_content = ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.EDIT, color=ft.Colors.BLUE, size=24),
                ft.Text(f"编辑字幕 #{index + 1}", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE),
            ], spacing=10),
            
            ft.Divider(),
            
            ft.Text("字幕内容:", size=14, weight=ft.FontWeight.W_500),
            edit_text_field,
            char_count_text,
            
            ft.Container(height=10),
            
            ft.Row([
                ft.Text("角色分配:", size=14, weight=ft.FontWeight.W_500),
                role_dropdown,
            ], spacing=10),
            role_voice_info,
            
        ], spacing=10, width=550)
        
        # 创建对话框
        def close_dialog(e):
            dialog.open = False
            if hasattr(self, 'page') and self.page:
                self.page.update()
        
        def save_changes(e):
            # 保存文本更改
            new_text = edit_text_field.value.strip()
            if new_text:
                self.edited_subtitles[index] = new_text
                self.subtitle_segments[index] = new_text
            
            # 保存角色分配
            selected_role = role_dropdown.value
            if selected_role == "未分配":
                if index in self.subtitle_line_roles:
                    del self.subtitle_line_roles[index]
            else:
                self.subtitle_line_roles[index] = selected_role
            
            # 更新字幕预览（简洁版本，不会触发滚动）
            self.update_subtitle_preview_simple()
            
            # 关闭对话框
            close_dialog(e)
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("字幕编辑"),
            content=dialog_content,
            actions=[
                ft.TextButton("取消", on_click=close_dialog),
                ft.ElevatedButton(
                    "保存",
                    on_click=save_changes,
                    style=ft.ButtonStyle(
                        color=ft.Colors.WHITE,
                        bgcolor=ft.Colors.BLUE
                    )
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        # 添加初始化函数到对话框对象
        def initialize_role_info():
            if current_role != "未分配" and current_role in self.subtitle_roles:
                voice_path = self.subtitle_roles[current_role]
                voice_name = os.path.basename(voice_path) if voice_path else "未选择"
                role_voice_info.value = f"音色: {voice_name}"
            else:
                role_voice_info.value = ""
            # 通过页面更新而不是直接调用控件的update方法
            if hasattr(self, 'page') and self.page:
                self.page.update()
        
        dialog.initialize_role_info = initialize_role_info
        
        return dialog
    
    def open_subtitle_edit_dialog(self, index):
        """打开字幕编辑对话框"""
        self.log_manager.info(f"尝试打开字幕编辑对话框，索引: {index}")
        if index < len(self.subtitle_segments):
            segment = self.subtitle_segments[index]
            self.log_manager.info(f"打开字幕编辑对话框，内容: {segment[:50]}...")
            dialog = self.create_subtitle_edit_dialog(index, segment)
            if hasattr(self, 'page') and self.page:
                self.page.overlay.append(dialog)
                dialog.open = True
                self.page.update()
            
            # 在对话框显示后初始化角色信息
            if hasattr(dialog, 'initialize_role_info'):
                dialog.initialize_role_info()
        else:
            self.log_manager.error(f"索引 {index} 超出范围，字幕段数量: {len(self.subtitle_segments)}")
    
    def start_subtitle_generation(self, e):
        """开始字幕生成（支持角色分配）"""
        # 使用字幕行列表
        if not hasattr(self, 'subtitle_segments') or not self.subtitle_segments:
            self.show_message("请先输入文章内容", True)
            return
        
        # 根据设置选择接口模式（本地/远程）
        api_mode = 'local'
        remote_url = ''
        try:
            api_mode = self.config_manager.get('tts_api_mode', 'local')
            remote_url = self.config_manager.get('tts_remote_base_url', '')
        except Exception:
            api_mode = 'local'
            remote_url = ''

        # 本地模式需要检查是否有运行中的实例；远程模式跳过端口检查
        available_ports = [port for port, info in self.instances.items()
                           if info.get('status') in ('running', '运行中')]
        if api_mode == 'local' and not available_ports:
            self.show_message("请先启动至少一个TTS实例", True)
            return
        if api_mode == 'remote' and not remote_url:
            self.show_message("请在设置中配置远程 TTS 接口地址", True)
            return
        
        # 检查是否有角色分配或默认语音
        has_role_assignments = bool(self.subtitle_line_roles)
        has_default_voice = bool(self.selected_voice)
        
        if not has_role_assignments and not has_default_voice:
            self.show_message("请设置角色分配或选择默认语音", True)
            return
        
        # 使用第一个可用端口进行单线程处理（远程模式则不使用端口）
        self.current_port = available_ports[0] if api_mode == 'local' else None
        
        # 创建临时目录
        self.temp_audio_dir = tempfile.mkdtemp(prefix="subtitle_audio_")
        self.total_subtitles_to_generate = len(self.subtitle_segments)
        self.completed_subtitles = 0
        self.is_generating = True
        
        # 初始化音频时长存储
        self.subtitle_durations = {}
        
        # 更新状态
        self.subtitle_status.value = f"正在生成字幕... (共{len(self.subtitle_segments)}句，支持角色分配)"
        self.subtitle_progress.value = 0
        
        if hasattr(self, 'page') and self.page:
            self.page.update()
        
        # 在后台线程中执行字幕生成
        self.page.run_thread(self._subtitle_generation_thread)
    
    def _subtitle_generation_thread(self):
        """字幕生成后台线程"""
        try:
            # 单线程顺序处理每个字幕
            for i, text in enumerate(self.subtitle_segments):
                if not self.is_generating:  # 检查是否被停止
                    break
                    
                # 确定使用的语音
                voice_to_use = self.selected_voice  # 默认语音
                
                # 检查是否有角色分配
                if i in self.subtitle_line_roles:
                    role_name = self.subtitle_line_roles[i]
                    if role_name in self.subtitle_roles:
                        voice_filename = self.subtitle_roles[role_name]
                        # 如果存的是文件名（stem），根据扫描到的文件列表查找实际路径
                        if voice_filename and not os.path.isabs(voice_filename):
                            match_path = None
                            for vf in getattr(self, 'voice_files', []):
                                try:
                                    if vf.stem == voice_filename:
                                        match_path = str(vf.absolute())
                                        break
                                except Exception:
                                    continue
                            # 找到匹配则使用匹配路径，否则保留默认语音
                            voice_to_use = match_path or voice_to_use
                        else:
                            voice_to_use = voice_filename
                
                if not voice_to_use:
                    self.log_message(f"第{i+1}行没有分配语音，跳过", "WARNING")
                    continue
                    
                self.generate_single_subtitle_with_voice(i, text, self.current_port, voice_to_use)
                
                # 更新进度（直接更新，因为已经在后台线程中）
                self.completed_subtitles += 1
                progress = self.completed_subtitles / self.total_subtitles_to_generate
                self.subtitle_progress.value = progress
                self.subtitle_status.value = f"正在生成字幕... ({self.completed_subtitles}/{self.total_subtitles_to_generate})"
                if hasattr(self, 'page') and self.page:
                    self.page.update()
            
            # 生成完成
            if self.is_generating:
                self.subtitle_status.value = f"字幕生成完成！共生成 {self.completed_subtitles} 个音频文件，正在合并..."
                self.log_message(f"字幕生成完成，共生成 {self.completed_subtitles} 个音频文件")
                if hasattr(self, 'page') and self.page:
                    self.page.update()
                
                # 合并所有音频文件
                self.merge_subtitle_audio()
            else:
                self.subtitle_status.value = "字幕生成已停止"
                self.log_message("字幕生成被用户停止")
            
            self.is_generating = False
            if hasattr(self, 'page') and self.page:
                self.page.update()
                
        except Exception as e:
            # 错误处理
            self.log_message(f"字幕生成过程中发生错误: {e}", "ERROR")
            self.subtitle_status.value = f"字幕生成失败: {e}"
            self.is_generating = False
            if hasattr(self, 'page') and self.page:
                self.page.update()
    
    def stop_subtitle_generation(self, e):
        """停止字幕生成（单线程版本）"""
        if hasattr(self, 'is_generating'):
            self.is_generating = False
        
        # 清理临时文件
        self.cleanup_temp_files()
        
        self.subtitle_status.value = "生成已停止"
        if hasattr(self, 'page') and self.page:
            self.page.update()
    
    def clear_subtitle_content(self, e):
        """清空字幕内容"""
        if self.subtitle_text_input:
            self.subtitle_text_input.value = ""
            self.temp_subtitle_text = ""

        # 清空分句
        self.subtitle_segments = []
        # 同步清空角色分配映射，避免后续索引错位造成显示为“未分配”
        if hasattr(self, 'subtitle_line_roles'):
            self.subtitle_line_roles.clear()

        if self.subtitle_preview:
            self.subtitle_preview.controls.clear()

        if self.subtitle_progress:
            self.subtitle_progress.value = 0

        if self.subtitle_status:
            self.subtitle_status.value = "准备就绪"

        if self.thread_status_list:
            self.thread_status_list.controls.clear()

        if hasattr(self, 'page') and self.page:
            self.page.update()
    

    
    def generate_single_subtitle(self, index, text, port):
        """生成单个字幕音频"""
        try:
            # 更新状态显示
            self.subtitle_status.value = f"正在生成第 {index + 1} 条字幕: {text[:10]}..."
            if hasattr(self, 'page') and self.page:
                self.page.update()
            
            # 记录生成前outputs文件夹中的文件
            outputs_dir = "outputs"
            os.makedirs(outputs_dir, exist_ok=True)
            before_files = set(os.listdir(outputs_dir)) if os.path.exists(outputs_dir) else set()
            
            # 选择接口模式并创建客户端（本地或远程）
            api_mode = 'local'
            remote_url = ''
            try:
                api_mode = self.config_manager.get('tts_api_mode', 'local')
                remote_url = self.config_manager.get('tts_remote_base_url', '')
            except Exception:
                api_mode = 'local'
                remote_url = ''
            client = Client(remote_url) if (api_mode == 'remote' and remote_url) else Client(f"http://127.0.0.1:{port}")
            
            # 第一步：更新提示音频（选择音色，必须执行的第一步）
            try:
                update_result = client.predict(api_name="/update_prompt_audio")
            except Exception as update_error:
                # 如果更新失败，记录但继续进行
                self.log_message(f"提示音频更新失败 (端口 {port}): {update_error}")
            
            # 第二步：生成语音（使用 /gen_single 端点，映射当前情感控制参数与向量滑条）
            method_map = {
                "与音色参考音频相同": 0,
                "参考音频控制": 1,
                "向量控制": 2,
                "情绪控制": 2,
                "文本控制": 3,
            }
            local_label_map = {
                "与音色参考音频相同": "与音色参考音频相同",
                "参考音频控制": "使用情感参考音频",
                "向量控制": "使用情感向量控制",
                "情绪控制": "使用情感向量控制",
                "文本控制": "与音色参考音频相同",
            }
            remote_label_map = {
                "与音色参考音频相同": "Same as the voice reference",
                "参考音频控制": "Use emotion reference audio",
                "向量控制": "Use emotion vectors",
                "情绪控制": "Use emotion vectors",
                "文本控制": "Same as the voice reference",
            }
            selected_method = getattr(self, 'emo_method_radio', None) and self.emo_method_radio.value or "与音色参考音频相同"
            emo_method_val = method_map.get(selected_method, 0)
            emo_method_label_local = local_label_map.get(selected_method, "与音色参考音频相同")
            emo_method_label_remote = remote_label_map.get(selected_method, "Same as the voice reference")
            if emo_method_val == 3:
                emo_method_label_local = "与音色参考音频相同"
                emo_method_label_remote = "Same as the voice reference"

            emo_random_val = bool(getattr(self, 'emo_random_checkbox', None) and self.emo_random_checkbox.value)
            emo_weight_val = float(getattr(self, 'emo_weight_slider', None) and self.emo_weight_slider.value or 0.65)
            emo_text_val = ""
            emo_ref_val = None
            if emo_method_val == 3 and getattr(self, 'emo_text_input', None):
                emo_text_val = (self.emo_text_input.value or "").strip()
            if emo_method_val == 1 and getattr(self, 'emo_ref_path_input', None):
                if self.emo_ref_path_input.value:
                    emo_ref_val = handle_file(self.emo_ref_path_input.value)

            # 按行优先使用已设置的情感向量，其次回退到全局滑条
            vec_vals = [0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]
            try:
                use_ai_emotion = bool(self.config_manager.get("ai_adjust_emotion", True))
                if use_ai_emotion and hasattr(self, 'subtitle_line_emotions') and isinstance(self.subtitle_line_emotions, dict):
                    line_vec = self.subtitle_line_emotions.get(index)
                    if isinstance(line_vec, list) and len(line_vec) >= 8:
                        for i in range(8):
                            vec_vals[i] = float(line_vec[i] if i < len(line_vec) else 0.0)
                    else:
                        if getattr(self, 'vec_sliders', None):
                            for i in range(min(8, len(self.vec_sliders))):
                                vec_vals[i] = float(self.vec_sliders[i].value or 0.0)
                else:
                    if getattr(self, 'vec_sliders', None):
                        for i in range(min(8, len(self.vec_sliders))):
                            vec_vals[i] = float(self.vec_sliders[i].value or 0.0)
            except Exception:
                pass

            params = {
                "prompt": handle_file(self.selected_voice),
                "text": text,
                "emo_ref_path": emo_ref_val,
                "emo_weight": emo_weight_val,
                "vec1": vec_vals[0],
                "vec2": vec_vals[1],
                "vec3": vec_vals[2],
                "vec4": vec_vals[3],
                "vec5": vec_vals[4],
                "vec6": vec_vals[5],
                "vec7": vec_vals[6],
                "vec8": vec_vals[7],
                "emo_text": emo_text_val,
                "emo_random": emo_random_val,
                "api_name": "/gen_single",
            }
            result = self._predict_with_emo_choice(client, params, emo_method_label_remote, emo_method_label_local)
            
            # 优先尝试直接从接口结果保存音频（用于远程模式或接口直接返回）
            try:
                audio_filename = f"subtitle_{index:03d}.wav"
                saved_path = self.save_audio_from_result(result, self.temp_audio_dir, dest_filename=audio_filename, base_url=(remote_url if api_mode=='remote' else None))
            except Exception:
                saved_path = None
            if saved_path and os.path.exists(saved_path):
                try:
                    s = None
                    try:
                        if hasattr(self, 'subtitle_line_speeds') and isinstance(self.subtitle_line_speeds, dict):
                            s = self.subtitle_line_speeds.get(index)
                        if s is None and bool(self.config_manager.get("ai_adjust_speed", False)) and hasattr(self, 'ai_analysis_result'):
                            ls = self.ai_analysis_result.get("line_speeds", {})
                            s = ls.get(index)
                    except Exception:
                        s = None
                    if s is None:
                        s = float((getattr(self, "runtime_speaking_speed", None) or self.config_manager.get("speaking_speed", 1.0)))
                    self.apply_speaking_speed_value(saved_path, s)
                    if not bool(self.config_manager.get("ai_adjust_emotion", True)):
                        pass
                    self.apply_volume(saved_path)
                except Exception:
                    pass
                audio_duration = self.get_audio_duration(saved_path)
                if not hasattr(self, 'subtitle_durations'):
                    self.subtitle_durations = {}
                self.subtitle_durations[index] = audio_duration
                self.subtitle_status.value = f"第 {index + 1} 条字幕完成 ({audio_duration:.1f}s)"
                if hasattr(self, 'page') and self.page:
                    self.page.update()
                return
            
            # 监控outputs文件夹，等待新文件生成
            self.subtitle_status.value = f"等待第 {index + 1} 条字幕文件生成..."
            if hasattr(self, 'page') and self.page:
                self.page.update()
            
            new_audio_file = None
            max_wait_time = 30  # 最大等待30秒
            wait_interval = 0.5  # 每0.5秒检查一次
            waited_time = 0
            
            while waited_time < max_wait_time:
                time.sleep(wait_interval)
                waited_time += wait_interval
                
                if os.path.exists(outputs_dir):
                    after_files = set(os.listdir(outputs_dir))
                    new_files = after_files - before_files
                    
                    # 查找新生成的wav文件
                    for file in new_files:
                        if file.endswith('.wav') and file.startswith('spk_'):
                            new_audio_file = os.path.join(outputs_dir, file)
                            break
                    
                    if new_audio_file:
                        break
            
            if new_audio_file and os.path.exists(new_audio_file):
                # 移动并重命名文件到临时文件夹
                audio_filename = f"subtitle_{index:03d}.wav"
                audio_path = os.path.join(self.temp_audio_dir, audio_filename)
                
                # 确保临时文件夹存在
                os.makedirs(self.temp_audio_dir, exist_ok=True)
                
                # 移动文件
                shutil.move(new_audio_file, audio_path)
                
                try:
                    s = None
                    try:
                        if hasattr(self, 'subtitle_line_speeds') and isinstance(self.subtitle_line_speeds, dict):
                            s = self.subtitle_line_speeds.get(index)
                        if s is None and bool(self.config_manager.get("ai_adjust_speed", False)) and hasattr(self, 'ai_analysis_result'):
                            ls = self.ai_analysis_result.get("line_speeds", {})
                            s = ls.get(index)
                    except Exception:
                        s = None
                    if s is None:
                        s = float((getattr(self, "runtime_speaking_speed", None) or self.config_manager.get("speaking_speed", 1.0)))
                    self.apply_speaking_speed_value(audio_path, s)
                    if not bool(self.config_manager.get("ai_adjust_emotion", True)):
                        pass
                    self.apply_volume(audio_path)
                except Exception:
                    pass
                audio_duration = self.get_audio_duration(audio_path)
                
                # 存储音频时长信息，用于后续字幕时间戳计算
                if not hasattr(self, 'subtitle_durations'):
                    self.subtitle_durations = {}
                self.subtitle_durations[index] = audio_duration
                
                # 更新状态显示
                self.subtitle_status.value = f"第 {index + 1} 条字幕完成 ({audio_duration:.1f}s)"
                
                if hasattr(self, 'page') and self.page:
                    self.page.update()
            else:
                # 文件生成失败
                raise Exception(f"在{max_wait_time}秒内未检测到新的音频文件生成")
                        
        except Exception as e:
            self.log_message(f"生成字幕音频失败 (索引 {index}): {e}")
            # 更新失败状态
            self.subtitle_status.value = f"第 {index + 1} 条字幕生成失败"
            if hasattr(self, 'page') and self.page:
                self.page.update()
    
    def generate_single_subtitle_with_voice(self, index, text, port, voice_path):
        """生成单个字幕音频（指定语音）"""
        try:
            # 更新状态显示
            voice_name = os.path.basename(voice_path) if voice_path else "默认"
            self.subtitle_status.value = f"正在生成第 {index + 1} 条字幕: {text[:10]}... (语音: {voice_name})"
            if hasattr(self, 'page') and self.page:
                self.page.update()
            
            # 记录生成前outputs文件夹中的文件
            outputs_dir = "outputs"
            os.makedirs(outputs_dir, exist_ok=True)
            before_files = set(os.listdir(outputs_dir)) if os.path.exists(outputs_dir) else set()
            
            # 选择接口模式并创建客户端（本地或远程）
            api_mode = 'local'
            remote_url = ''
            try:
                api_mode = self.config_manager.get('tts_api_mode', 'local')
                remote_url = self.config_manager.get('tts_remote_base_url', '')
            except Exception:
                api_mode = 'local'
                remote_url = ''
            client = Client(remote_url) if (api_mode == 'remote' and remote_url) else Client(f"http://127.0.0.1:{port}")
            
            # 第一步：更新提示音频（选择音色，必须执行的第一步）
            try:
                update_result = client.predict(api_name="/update_prompt_audio")
            except Exception as update_error:
                # 如果更新失败，记录但继续进行
                self.log_message(f"提示音频更新失败 (端口 {port}): {update_error}")
            
            # 第二步：生成语音（使用 /gen_single 端点，映射当前情感控制参数与向量滑条）
            method_map = {
                "与音色参考音频相同": 0,
                "参考音频控制": 1,
                "向量控制": 2,
                "情绪控制": 2,
                "文本控制": 3,
            }
            local_label_map = {
                "与音色参考音频相同": "与音色参考音频相同",
                "参考音频控制": "使用情感参考音频",
                "向量控制": "使用情感向量控制",
                "情绪控制": "使用情感向量控制",
                "文本控制": "与音色参考音频相同",
            }
            remote_label_map = {
                "与音色参考音频相同": "Same as the voice reference",
                "参考音频控制": "Use emotion reference audio",
                "向量控制": "Use emotion vectors",
                "情绪控制": "Use emotion vectors",
                "文本控制": "Same as the voice reference",
            }
            selected_method = getattr(self, 'emo_method_radio', None) and self.emo_method_radio.value or "与音色参考音频相同"
            emo_method_val = method_map.get(selected_method, 0)
            emo_method_label_local = local_label_map.get(selected_method, "与音色参考音频相同")
            emo_method_label_remote = remote_label_map.get(selected_method, "Same as the voice reference")
            if emo_method_val == 3:
                emo_method_label_local = "与音色参考音频相同"
                emo_method_label_remote = "Same as the voice reference"

            emo_random_val = bool(getattr(self, 'emo_random_checkbox', None) and self.emo_random_checkbox.value)
            emo_weight_val = float(getattr(self, 'emo_weight_slider', None) and self.emo_weight_slider.value or 0.65)
            emo_text_val = ""
            emo_ref_val = None
            if emo_method_val == 3 and getattr(self, 'emo_text_input', None):
                emo_text_val = (self.emo_text_input.value or "").strip()
            if emo_method_val == 1 and getattr(self, 'emo_ref_path_input', None):
                if self.emo_ref_path_input.value:
                    emo_ref_val = handle_file(self.emo_ref_path_input.value)

            # 优先使用该行已设置的情感向量，其次回退到全局滑条
            vec_vals = [0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]
            try:
                use_ai_emotion = bool(self.config_manager.get("ai_adjust_emotion", True))
                if use_ai_emotion and hasattr(self, 'subtitle_line_emotions') and isinstance(self.subtitle_line_emotions, dict):
                    line_vec = self.subtitle_line_emotions.get(index)
                    if isinstance(line_vec, list) and len(line_vec) >= 8:
                        for i in range(8):
                            vec_vals[i] = float(line_vec[i] if i < len(line_vec) else 0.0)
                    else:
                        if getattr(self, 'vec_sliders', None):
                            for i in range(min(8, len(self.vec_sliders))):
                                vec_vals[i] = float(self.vec_sliders[i].value or 0.0)
                else:
                    if getattr(self, 'vec_sliders', None):
                        for i in range(min(8, len(self.vec_sliders))):
                            vec_vals[i] = float(self.vec_sliders[i].value or 0.0)
            except Exception:
                pass

            # 若该行存在非零向量，则自动切换为向量控制，避免情感控制失效
            try:
                if sum(abs(float(v)) for v in vec_vals) > 0 and emo_method_val != 2:
                    emo_method_label_local = "使用情感向量控制"
                    emo_method_label_remote = "Use emotion vectors"
            except Exception:
                pass

            params = {
                "prompt": handle_file(voice_path),
                "text": text,
                "emo_ref_path": emo_ref_val,
                "emo_weight": emo_weight_val,
                "vec1": vec_vals[0],
                "vec2": vec_vals[1],
                "vec3": vec_vals[2],
                "vec4": vec_vals[3],
                "vec5": vec_vals[4],
                "vec6": vec_vals[5],
                "vec7": vec_vals[6],
                "vec8": vec_vals[7],
                "emo_text": emo_text_val,
                "emo_random": emo_random_val,
                "api_name": "/gen_single",
            }
            result = self._predict_with_emo_choice(client, params, emo_method_label_remote, emo_method_label_local)
            
            # 优先尝试直接从接口结果保存音频（用于远程模式或接口直接返回）
            try:
                audio_filename = f"subtitle_{index:03d}.wav"
                saved_path = self.save_audio_from_result(result, self.temp_audio_dir, dest_filename=audio_filename, base_url=(remote_url if api_mode=='remote' else None))
            except Exception:
                saved_path = None
            if saved_path and os.path.exists(saved_path):
                try:
                    s = None
                    try:
                        if hasattr(self, 'subtitle_line_speeds') and isinstance(self.subtitle_line_speeds, dict):
                            s = self.subtitle_line_speeds.get(index)
                        if s is None and bool(self.config_manager.get("ai_adjust_speed", False)) and hasattr(self, 'ai_analysis_result'):
                            ls = self.ai_analysis_result.get("line_speeds", {})
                            s = ls.get(index)
                    except Exception:
                        s = None
                    s = float(s) if s is not None else float(self.config_manager.get("speaking_speed", 1.0))
                    self.apply_speaking_speed_value(saved_path, s)
                    self.apply_volume(saved_path)
                except Exception:
                    pass
                audio_duration = self.get_audio_duration(saved_path)
                if not hasattr(self, 'subtitle_durations'):
                    self.subtitle_durations = {}
                self.subtitle_durations[index] = audio_duration
                self.subtitle_status.value = f"第 {index + 1} 条字幕完成 ({audio_duration:.1f}s, 语音: {voice_name})"
                if hasattr(self, 'page') and self.page:
                    self.page.update()
                return
            
            # 监控outputs文件夹，等待新文件生成
            self.subtitle_status.value = f"等待第 {index + 1} 条字幕文件生成... (语音: {voice_name})"
            if hasattr(self, 'page') and self.page:
                self.page.update()
            
            new_audio_file = None
            max_wait_time = 30  # 最大等待30秒
            wait_interval = 0.5  # 每0.5秒检查一次
            waited_time = 0
            
            while waited_time < max_wait_time:
                time.sleep(wait_interval)
                waited_time += wait_interval
                
                if os.path.exists(outputs_dir):
                    after_files = set(os.listdir(outputs_dir))
                    new_files = after_files - before_files
                    
                    # 查找新生成的wav文件
                    for file in new_files:
                        if file.endswith('.wav') and file.startswith('spk_'):
                            new_audio_file = os.path.join(outputs_dir, file)
                            break
                    
                    if new_audio_file:
                        break
            
            if new_audio_file and os.path.exists(new_audio_file):
                # 移动并重命名文件到临时文件夹
                audio_filename = f"subtitle_{index:03d}.wav"
                audio_path = os.path.join(self.temp_audio_dir, audio_filename)
                
                # 确保临时文件夹存在
                os.makedirs(self.temp_audio_dir, exist_ok=True)
                
                # 移动文件
                shutil.move(new_audio_file, audio_path)
                
                try:
                    s = None
                    try:
                        if hasattr(self, 'subtitle_line_speeds') and isinstance(self.subtitle_line_speeds, dict):
                            s = self.subtitle_line_speeds.get(index)
                        if s is None and bool(self.config_manager.get("ai_adjust_speed", False)) and hasattr(self, 'ai_analysis_result'):
                            ls = self.ai_analysis_result.get("line_speeds", {})
                            s = ls.get(index)
                    except Exception:
                        s = None
                    s = float(s) if s is not None else float(self.config_manager.get("speaking_speed", 1.0))
                    self.apply_speaking_speed_value(audio_path, s)
                    self.apply_volume(audio_path)
                except Exception:
                    pass
                audio_duration = self.get_audio_duration(audio_path)
                
                # 存储音频时长信息，用于后续字幕时间戳计算
                if not hasattr(self, 'subtitle_durations'):
                    self.subtitle_durations = {}
                self.subtitle_durations[index] = audio_duration
                
                # 更新状态显示
                self.subtitle_status.value = f"第 {index + 1} 条字幕完成 ({audio_duration:.1f}s, 语音: {voice_name})"
                
                if hasattr(self, 'page') and self.page:
                    self.page.update()
            else:
                # 文件生成失败
                raise Exception(f"在{max_wait_time}秒内未检测到新的音频文件生成")
                        
        except Exception as e:
            voice_name = os.path.basename(voice_path) if voice_path else "默认"
            self.log_message(f"生成字幕音频失败 (索引 {index}, 语音: {voice_name}): {e}")
            # 更新失败状态
            self.subtitle_status.value = f"第 {index + 1} 条字幕生成失败 (语音: {voice_name})"
            if hasattr(self, 'page') and self.page:
                self.page.update()

    
    def on_subtitle_edit(self, e, index):
        """字幕编辑事件处理"""
        if index < len(self.edited_subtitles):
            self.edited_subtitles[index] = e.control.value
            # 更新字符数显示（使用正确的字符计算）
            char_count = self.calculate_character_length(e.control.value)
            self.update_character_count_display(index, char_count)
    
    def update_character_count_display(self, index, char_count):
        """更新字符数显示"""
        if hasattr(self, 'subtitle_preview') and self.subtitle_preview:
            try:
                # 找到对应的容器并更新字符数显示
                container = self.subtitle_preview.controls[index]
                if hasattr(container, 'content') and hasattr(container.content, 'controls'):
                    row = container.content.controls[0]  # 第一行是标题行
                    if hasattr(row, 'controls') and len(row.controls) >= 2:
                        segment = self.edited_subtitles[index] if index < len(self.edited_subtitles) else ""
                        cn_count = self._cn_han_count(segment)
                        danger = cn_count > int(self.subtitle_cpl_chinese or 18)
                        warn = not danger and cn_count >= int((self.subtitle_cpl_chinese or 18) * 0.9)
                        row.controls[1].value = f"({cn_count}字)"
                        dark = self.is_dark_theme()
                        row.controls[1].color = (ft.Colors.RED_300 if dark else ft.Colors.RED_400) if danger else ((ft.Colors.ORANGE_300 if dark else ft.Colors.ORANGE_400) if warn else (ft.Colors.GREY_400 if dark else ft.Colors.GREY_500))
                        if hasattr(self, 'page') and self.page:
                            self.page.update()
            except:
                pass  # 忽略更新错误

    def _build_char_count_text(self, segment, dark=False):
        cn_count = self._cn_han_count(segment)
        danger = cn_count > int(self.subtitle_cpl_chinese or 18)
        warn = not danger and cn_count >= int((self.subtitle_cpl_chinese or 18) * 0.9)
        color = (ft.Colors.RED_300 if dark else ft.Colors.RED_400) if danger else ((ft.Colors.ORANGE_300 if dark else ft.Colors.ORANGE_400) if warn else (ft.Colors.GREY_400 if dark else ft.Colors.GREY_500))
        return ft.Text(f"({cn_count}字)", size=12, color=color)

    def _cn_han_count(self, text):
        return cn_han_count(text)

    def on_subtitle_cpl_change(self, e):
        try:
            self.subtitle_cpl_chinese = int(float(e.control.value))
        except Exception:
            self.subtitle_cpl_chinese = 18
        self.resegment_current_text()
        try:
            if self.subtitle_cpl_value_text:
                self.subtitle_cpl_value_text.value = f"{int(self.subtitle_cpl_chinese)}字/行"
                if hasattr(self, 'page') and self.page:
                    self.page.update()
        except Exception:
            pass

    def on_quote_glue_change(self, e):
        try:
            self.quote_glue_enabled = bool(e.control.value)
        except Exception:
            self.quote_glue_enabled = True
        if self.subtitle_text_input and self.subtitle_text_input.value:
            segs = self.split_text_intelligently(self.subtitle_text_input.value)
            if self.quote_glue_enabled:
                segs = self.apply_quote_glue(segs)
            self.subtitle_segments = segs
        try:
            self.update_subtitle_preview_simple()
        except Exception:
            self.update_subtitle_preview()
    
    def delete_subtitle_line(self, e, index):
        """删除字幕行"""
        self.log_manager.info(f"尝试删除字幕行，索引: {index}")
        if index < len(self.subtitle_segments):
            self.log_manager.info(f"删除字幕行，内容: {self.subtitle_segments[index][:50]}...")
            # 确保两个列表都存在且索引有效
            if index < len(self.edited_subtitles):
                self.edited_subtitles.pop(index)
            self.subtitle_segments.pop(index)
            # 修正角色映射索引：删除后的行索引左移，去除被删除行对应映射
            if hasattr(self, 'subtitle_line_roles') and isinstance(self.subtitle_line_roles, dict):
                new_roles = {}
                for k, v in self.subtitle_line_roles.items():
                    if k < index:
                        new_roles[k] = v
                    elif k > index:
                        new_roles[k - 1] = v
                    # k == index 的映射随删除行被移除
                self.subtitle_line_roles = new_roles
            # 修正情感向量映射索引：同步左移并移除被删除行
            if hasattr(self, 'subtitle_line_emotions') and isinstance(self.subtitle_line_emotions, dict):
                new_emotions = {}
                for k, v in self.subtitle_line_emotions.items():
                    if k < index:
                        new_emotions[k] = v
                    elif k > index:
                        new_emotions[k - 1] = v
                    # k == index 的映射随删除行被移除
                self.subtitle_line_emotions = new_emotions
            self.update_subtitle_preview_simple()
        else:
            self.log_manager.error(f"索引 {index} 超出范围，字幕段数量: {len(self.subtitle_segments)}")
    
    def add_subtitle_line(self, e):
        """添加新的字幕行"""
        new_text = "新增字幕行"
        self.edited_subtitles.append(new_text)
        self.subtitle_segments.append(new_text)
        # 为新增的行初始化默认的情感向量（与全局滑条长度一致）
        try:
            vec_len = len(self.vec_names) if hasattr(self, 'vec_names') else 8
        except Exception:
            vec_len = 8
        default_vec = [0] * max(1, vec_len)
        if not hasattr(self, 'subtitle_line_emotions') or not isinstance(self.subtitle_line_emotions, dict):
            self.subtitle_line_emotions = {}
        new_index = len(self.subtitle_segments) - 1
        self.subtitle_line_emotions[new_index] = default_vec
        self.update_subtitle_preview_simple()
    
    def get_active_instances(self):
        """获取当前活跃的实例数量"""
        active_count = 0
        for port, info in self.instances.items():
            status = info.get('status')
            if status in ('running', '运行中'):
                active_count += 1
        return active_count
    
    def save_audio_from_result(self, result, dest_dir, dest_filename=None, base_url=None):
        return save_audio_from_result(result, dest_dir, dest_filename, base_url, logger=self.log_manager)

    def get_audio_duration(self, audio_path):
        return get_audio_duration(audio_path, logger=self.log_manager)

    def apply_speaking_speed(self, audio_path):
        try:
            s = float((getattr(self, "runtime_speaking_speed", None) or self.config_manager.get("speaking_speed", 1.0)))
            return apply_speaking_speed(audio_path, s, logger=self.log_manager)
        except Exception:
            return False

    def apply_speaking_speed_value(self, audio_path, s):
        return apply_speaking_speed_value(audio_path, s, logger=self.log_manager)

    def apply_volume(self, audio_path):
        try:
            vp = int((getattr(self, "runtime_volume_percent", None) or self.config_manager.get("volume_percent", 100)))
            return apply_volume(audio_path, vp, logger=self.log_manager)
        except Exception:
            return False

    def format_timestamp(self, seconds):
        return format_timestamp(seconds)

    def remove_punctuation_from_text(self, text):
        return remove_punctuation_from_text(text)

    def generate_subtitle_file(self, output_path):
        """生成SRT字幕文件"""
        try:
            if not hasattr(self, 'subtitle_durations') or not self.subtitle_durations:
                self.log_message("没有音频时长信息，无法生成字幕")
                return None
            
            # 按索引排序
            sorted_indices = sorted(self.subtitle_durations.keys())
            
            # 生成字幕内容
            subtitle_content = []
            current_time = 0.0
            
            for i, index in enumerate(sorted_indices):
                duration = self.subtitle_durations[index]
                start_time = current_time
                end_time = current_time + duration
                
                # 格式化时间戳
                start_timestamp = self.format_timestamp(start_time)
                end_timestamp = self.format_timestamp(end_time)
                
                # 获取对应的文本 - 优先使用编辑后的字幕
                text = ""
                # 首先尝试使用编辑后的字幕
                if hasattr(self, 'edited_subtitles') and self.edited_subtitles and index < len(self.edited_subtitles):
                    text = self.edited_subtitles[index]
                # 如果没有编辑后的字幕，使用原始分句
                elif hasattr(self, 'subtitle_segments') and index < len(self.subtitle_segments):
                    text = self.subtitle_segments[index]
                else:
                    text = f"字幕 {index + 1}"
                
                # 如果勾选了去除标点符号，则处理文本
                if hasattr(self, 'remove_punctuation_checkbox') and self.remove_punctuation_checkbox and self.remove_punctuation_checkbox.value:
                    text = self.remove_punctuation_from_text(text)
                
                # 添加字幕条目
                subtitle_content.append(f"{i + 1}")
                subtitle_content.append(f"{start_timestamp} --> {end_timestamp}")
                subtitle_content.append(text)
                subtitle_content.append("")  # 空行分隔
                
                # 使用可配置的音频间隔（转换为秒）
                audio_interval_seconds = self.config_manager.get('audio_interval', 100) / 1000.0
                current_time = end_time + audio_interval_seconds
            
            # 写入字幕文件
            subtitle_path = output_path.replace('.wav', '.srt')
            with open(subtitle_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(subtitle_content))
            
            self.log_message(f"字幕文件生成完成: {subtitle_path}")
            return subtitle_path
            
        except Exception as e:
            self.log_message(f"生成字幕文件失败: {e}")
            return None



    def cleanup_temp_files(self):
        """清理临时文件和目录"""
        try:
            if hasattr(self, 'temp_audio_dir') and self.temp_audio_dir and os.path.exists(self.temp_audio_dir):
                shutil.rmtree(self.temp_audio_dir, ignore_errors=True)
                self.log_manager.info("临时文件清理完成")
            else:
                self.log_manager.debug("没有临时文件需要清理")
        except Exception as e:
            self.log_manager.error(f"清理临时文件失败: {e}")
    
    def setup_exit_handlers(self):
        """设置程序退出时的处理器"""
        try:
            # 注册atexit处理器
            atexit.register(self.cleanup_on_exit)
            
            # 设置信号处理器（仅在支持的平台上）
            if hasattr(signal, 'SIGINT'):
                signal.signal(signal.SIGINT, self.signal_handler)
            if hasattr(signal, 'SIGTERM'):
                signal.signal(signal.SIGTERM, self.signal_handler)
            
            # Windows特有的信号
            if platform.system() == "Windows":
                if hasattr(signal, 'SIGBREAK'):
                    signal.signal(signal.SIGBREAK, self.signal_handler)
            
            self.log_manager.info("程序退出处理器设置完成")
            
        except Exception as e:
            self.log_manager.error(f"设置退出处理器失败: {e}")
    
    def signal_handler(self, signum, frame):
        """信号处理器"""
        self.log_manager.info(f"接收到信号 {signum}，开始清理...")
        self.cleanup_on_exit()
        sys.exit(0)
    
    def cleanup_on_exit(self):
        """程序退出时的清理操作"""
        # 设置退出标志，防止GUI回调继续执行
        self._is_exiting = True
        
        try:
            self.log_manager.info("程序退出，开始清理所有资源...")
            
            # 停止所有运行的实例
            if hasattr(self, 'instances') and self.instances:
                self.log_manager.info(f"正在停止 {len(self.instances)} 个运行中的实例...")
                for port, process_info in list(self.instances.items()):
                    try:
                        process = process_info.get('process')
                        if process and process.poll() is None:  # 进程仍在运行
                            self.log_manager.info(f"停止端口 {port} 上的实例...")
                            process.terminate()
                            
                            # 等待进程结束，最多等待3秒（减少等待时间）
                            try:
                                process.wait(timeout=3)
                                self.log_manager.info(f"端口 {port} 实例已正常停止")
                            except subprocess.TimeoutExpired:
                                # 如果3秒后还没结束，强制杀死
                                try:
                                    process.kill()
                                    self.log_manager.warning(f"端口 {port} 实例被强制终止")
                                except Exception:
                                    pass  # 忽略强制终止时的错误
                    except Exception as e:
                        # 使用print而不是log_manager，避免GUI回调错误
                        print(f"停止端口 {port} 实例时出错: {e}")
                
                # 清空实例字典
                self.instances.clear()
                self.log_manager.info("所有实例已停止")
            
            # 停止线程池
            if hasattr(self, 'generation_executor') and self.generation_executor:
                try:
                    self.generation_executor.shutdown(wait=False)
                    self.log_manager.info("线程池已关闭")
                except Exception as e:
                    print(f"关闭线程池时出错: {e}")
            
            # 清理临时文件
            try:
                self.cleanup_temp_files()
            except Exception as e:
                print(f"清理临时文件时出错: {e}")
            
            # 关闭pygame音频
            try:
                if pygame.mixer.get_init():  # 检查pygame是否已初始化
                    pygame.mixer.quit()
                    self.log_manager.info("pygame音频系统已关闭")
            except Exception as e:
                print(f"关闭pygame音频系统时出错: {e}")
            
            # 清理GUI日志回调
            try:
                if hasattr(self, 'log_manager') and self.log_manager:
                    self.log_manager.set_gui_callback(None)
            except Exception:
                pass
            
            self.log_manager.info("程序清理完成")
            
        except Exception as e:
            # 使用print而不是log_manager，避免GUI回调错误
            print(f"程序退出清理时出错: {e}")
            # 即使清理出错，也要确保能够记录
            try:
                self.log_manager.exception("清理异常详情")
            except Exception:
                print("无法记录清理异常详情")

    def merge_subtitle_audio(self):
        """合并字幕音频文件"""
        try:
            self.subtitle_status.value = "正在合并音频文件..."
            if hasattr(self, 'page') and self.page:
                self.page.update()
            
            # 获取所有音频文件
            audio_files = []
            for i in range(len(self.subtitle_segments)):
                audio_path = os.path.join(self.temp_audio_dir, f"subtitle_{i:03d}.wav")
                if os.path.exists(audio_path):
                    audio_files.append(audio_path)
            
            if not audio_files:
                self.show_message("没有找到生成的音频文件", True)
                return
            
            # 使用pydub合并音频
            combined = AudioSegment.empty()
            
            # 获取配置的音频间隔时间
            audio_interval = self.config_manager.get("audio_interval", 100)
            
            for audio_file in sorted(audio_files):
                audio = AudioSegment.from_wav(audio_file)
                combined += audio
                # 添加可配置的音频间隔
                combined += AudioSegment.silent(duration=audio_interval)
            
            # 保存合并后的音频
            output_dir = "outputs"
            os.makedirs(output_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"subtitle_merged_{timestamp}.wav"
            output_path = os.path.join(output_dir, output_filename)
            
            combined.export(output_path, format="wav")
            
            # 生成字幕文件
            subtitle_path = self.generate_subtitle_file(output_path)

            # 不再立即删除临时文件，改为提示用户确认

            if subtitle_path:
                self.subtitle_status.value = f"生成完成！音频: {output_path}\n字幕: {subtitle_path}"
                self.show_message(f"字幕音频生成完成！\n音频文件: {output_path}\n字幕文件: {subtitle_path}")
                try:
                    self.add_generation_record(output_path, "字幕合并音频")
                except Exception:
                    pass
                try:
                    self.add_generation_record(subtitle_path, "字幕文件")
                except Exception:
                    pass
            else:
                self.subtitle_status.value = f"音频生成完成！文件保存至: {output_path}"
                self.show_message(f"音频生成完成！\n文件保存至: {output_path}\n注意：字幕文件生成失败")
                try:
                    self.add_generation_record(output_path, "字幕合并音频")
                except Exception:
                    pass

            if hasattr(self, 'page') and self.page:
                self.page.update()

            # 弹出确认是否删除临时文件的提示
            self.prompt_delete_temp_audio()
            # 若设置了字幕输出目录，复制最终结果（音频与srt）
            try:
                dest_dir = getattr(self, 'subtitle_output_dir', None)
                if dest_dir and os.path.isdir(dest_dir):
                    try:
                        bn_audio = os.path.basename(output_path)
                        dest_audio = os.path.join(dest_dir, bn_audio)
                        if os.path.exists(dest_audio):
                            base, ext = os.path.splitext(bn_audio)
                            idx = int(time.time())
                            dest_audio = os.path.join(dest_dir, f"{base}_{idx}{ext}")
                        shutil.copy2(output_path, dest_audio)
                    except Exception:
                        pass
                    try:
                        if subtitle_path and os.path.isfile(subtitle_path):
                            bn_srt = os.path.basename(subtitle_path)
                            dest_srt = os.path.join(dest_dir, bn_srt)
                            if os.path.exists(dest_srt):
                                base, ext = os.path.splitext(bn_srt)
                                idx = int(time.time())
                                dest_srt = os.path.join(dest_dir, f"{base}_{idx}{ext}")
                            shutil.copy2(subtitle_path, dest_srt)
                    except Exception:
                        pass
            except Exception:
                pass
                
        except Exception as e:
            self.log_message(f"合并音频文件失败: {e}")
            self.show_message(f"合并音频文件失败: {e}", True)
            # 出错时也提示用户是否删除临时文件（便于调试可选择保留）
            try:
                self.prompt_delete_temp_audio()
            except Exception:
                pass

    def prompt_delete_temp_audio(self):
        """提示用户是否删除临时音频文件夹，仅在用户确认时才删除"""
        try:
            # 只有在临时目录存在时才提示
            if not (hasattr(self, 'temp_audio_dir') and self.temp_audio_dir and os.path.exists(self.temp_audio_dir)):
                return

            # 定义按钮回调
            def on_confirm(e=None):
                try:
                    self.cleanup_temp_files()
                    self.show_message("已删除临时音频文件夹")
                except Exception as ex:
                    self.show_message(f"删除临时文件失败: {ex}", True)
                finally:
                    dialog.open = False
                    if hasattr(self, 'page') and self.page:
                        self.page.update()

            def on_cancel(e=None):
                dialog.open = False
                # 用户选择保留临时文件
                self.show_message("已保留临时音频文件夹，便于复查或再次合并")
                if hasattr(self, 'page') and self.page:
                    self.page.update()

            def on_open_location(e=None):
                try:
                    # 在Windows中打开临时文件夹
                    subprocess.run(['explorer', str(self.temp_audio_dir)], capture_output=True, text=True)
                    self.show_message(f"已打开临时文件夹: {self.temp_audio_dir}")
                except Exception as ex:
                    self.show_message(f"打开临时文件夹失败: {ex}", True)
                # 保持弹窗打开，方便继续选择删除或保留

            # 精简弹窗内容，避免背景过长
            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("删除临时音频？"),
                content=ft.Text(
                    f"临时目录：{self.temp_audio_dir}",
                    selectable=True,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                actions=[
                    ft.TextButton("复制到文件夹", on_click=lambda e: self.pick_copy_destination(dialog)),
                    ft.TextButton("打开所在位置", on_click=on_open_location),
                    ft.TextButton("删除临时文件", on_click=on_confirm),
                    ft.TextButton("取消", on_click=on_cancel),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )

            if hasattr(self, 'page') and self.page:
                self.page.overlay.append(dialog)
                dialog.open = True
                self.page.update()
        except Exception as e:
            # 记录但不中断主流程
            try:
                self.log_manager.error(f"显示删除临时文件确认失败: {e}")
            except Exception:
                pass

    def pick_copy_destination(self, dialog=None):
        """打开文件夹选择器以复制临时音频到用户选择的位置"""
        try:
            if not (hasattr(self, 'temp_audio_dir') and self.temp_audio_dir and os.path.exists(self.temp_audio_dir)):
                self.show_message("没有临时音频可复制", True)
                return
            # 确保页面可用
            if not (hasattr(self, 'page') and self.page):
                self.show_message("页面未初始化，无法打开文件夹选择器", True)
                return
            # 创建或复用文件夹选择器，并确保已加入到页面overlay
            if not hasattr(self, 'dir_picker') or self.dir_picker is None:
                self.dir_picker = ft.FilePicker(on_result=self.on_pick_directory_result)
            try:
                if self.dir_picker not in self.page.overlay:
                    self.page.overlay.append(self.dir_picker)
            except Exception:
                # 某些情况下overlay不支持成员检查，直接尝试追加
                self.page.overlay.append(self.dir_picker)
            # 先更新页面，确保 FilePicker 已注册，再打开选择器
            self.page.update()
            # 保存当前对话框引用，复制完成后关闭
            self._temp_copy_dialog = dialog
            # 打开目录选择对话框
            self.dir_picker.get_directory_path(dialog_title="选择保存临时音频的文件夹")
        except Exception as e:
            try:
                self.log_manager.error(f"打开文件夹选择器失败: {e}")
            except Exception:
                pass
            self.show_message(f"打开文件夹选择器失败: {e}", True)

    def on_pick_directory_result(self, e):
        """处理目录选择结果，并执行复制"""
        try:
            dest_root = getattr(e, 'path', None)
            if not dest_root:
                self.show_message("未选择文件夹，已取消复制")
                return
            copied_path = self.copy_temp_audio_to_folder(dest_root)
            if copied_path:
                self.show_message(f"已复制临时音频到: {copied_path}")
            # 复制完成后关闭弹窗
            if hasattr(self, '_temp_copy_dialog') and self._temp_copy_dialog:
                try:
                    self._temp_copy_dialog.open = False
                    if hasattr(self, 'page') and self.page:
                        self.page.update()
                except Exception:
                    pass
                self._temp_copy_dialog = None
        except Exception as e:
            self.show_message(f"复制临时音频失败: {e}", True)

    def copy_temp_audio_to_folder(self, dest_root):
        """将临时音频目录复制到用户选择的目标根目录下的新子目录"""
        try:
            if not (hasattr(self, 'temp_audio_dir') and self.temp_audio_dir and os.path.exists(self.temp_audio_dir)):
                self.show_message("没有临时音频可复制", True)
                return None
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest_folder_name = f"临时音频_{timestamp}"
            dest_path = os.path.join(dest_root, dest_folder_name)
            shutil.copytree(self.temp_audio_dir, dest_path)
            return dest_path
        except Exception as e:
            self.show_message(f"复制临时音频失败: {e}", True)
            try:
                self.log_manager.error(f"复制临时音频失败: {e}")
            except Exception:
                pass
            return None

    # =========================
    # 音色上传功能
    # =========================
    def open_voice_file_picker(self, e=None):
        """打开文件选择器以添加音色文件（保存到 yinse 文件夹）"""
        try:
            if not (hasattr(self, 'page') and self.page):
                self.show_message("页面未初始化，无法选择文件", True)
                return
            # 确保控件存在并加入 overlay
            if not hasattr(self, 'file_picker') or self.file_picker is None:
                self.file_picker = ft.FilePicker(on_result=self.on_pick_voice_files)
                try:
                    self.page.overlay.append(self.file_picker)
                except Exception:
                    pass
            else:
                try:
                    if self.file_picker not in self.page.overlay:
                        self.page.overlay.append(self.file_picker)
                except Exception:
                    self.page.overlay.append(self.file_picker)
            self.page.update()
            # 允许多选，限制为常见音频扩展名
            allowed = ["wav","mp3","wma","flac","ogg","m4a","aac","opus"]
            self.file_picker.pick_files(
                allow_multiple=True,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=allowed,
                dialog_title="选择要添加的音色文件"
            )
        except Exception as ex:
            self.show_message(f"打开文件选择器失败: {ex}", True)

    def on_pick_voice_files(self, e):
        """处理选择的音色文件并复制到 yinse 文件夹"""
        try:
            files = getattr(e, 'files', None) or []
            if not files:
                self.show_message("未选择文件，已取消")
                return
            dest_dir = Path("yinse")
            dest_dir.mkdir(parents=True, exist_ok=True)
            allowed_exts = {".wav", ".mp3", ".wma", ".flac", ".ogg", ".m4a", ".aac", ".opus"}
            saved = []
            for f in files:
                src_path = getattr(f, 'path', None)
                if not src_path or not os.path.exists(src_path):
                    continue
                ext = Path(src_path).suffix.lower()
                if ext not in allowed_exts:
                    continue
                target_name = Path(src_path).name
                target_path = dest_dir / target_name
                # 如果重名，自动加序号避免覆盖
                if target_path.exists():
                    base = target_path.stem
                    ext2 = target_path.suffix
                    idx = 1
                    while True:
                        candidate = dest_dir / f"{base}_{idx}{ext2}"
                        if not candidate.exists():
                            target_path = candidate
                            break
                        idx += 1
                shutil.copy2(src_path, target_path)
                saved.append(str(target_path))
            if saved:
                self.show_message(f"已添加 {len(saved)} 个音色文件")
                # 刷新音色列表下拉框
                self.refresh_voices()
                try:
                    if hasattr(self, 'voice_library_list') and self.voice_library_list:
                        self.refresh_voice_library()
                except Exception:
                    pass
            else:
                self.show_message("没有符合条件的音色文件", True)
        except Exception as ex:
            self.show_message(f"添加音色文件失败: {ex}", True)

    def open_voice_folder_picker(self, e=None):
        """打开文件夹选择器以批量添加音色文件夹（复制到 yinse 目录）"""
        try:
            if not (hasattr(self, 'page') and self.page):
                self.show_message("页面未初始化，无法选择文件夹", True)
                return

            if not hasattr(self, 'voice_folder_picker') or self.voice_folder_picker is None:
                self.voice_folder_picker = ft.FilePicker(on_result=self.on_pick_voice_folder)
                try:
                    self.page.overlay.append(self.voice_folder_picker)
                except Exception:
                    pass
            else:
                try:
                    if self.voice_folder_picker not in self.page.overlay:
                        self.page.overlay.append(self.voice_folder_picker)
                except Exception:
                    self.page.overlay.append(self.voice_folder_picker)

            self.page.update()
            # 仅选择文件夹路径
            self.voice_folder_picker.get_directory_path()
        except Exception as ex:
            self.show_message(f"打开文件夹选择器失败: {ex}", True)

    def on_pick_voice_folder(self, e: ft.FilePickerResultEvent):
        """处理选择的音色文件夹：整体复制到项目 yinse 目录下"""
        try:
            path = getattr(e, 'path', None)
            if not path:
                self.show_message("未选择文件夹，已取消")
                return

            src_dir = Path(path)
            if not src_dir.exists() or not src_dir.is_dir():
                self.show_message("选择的路径不是有效文件夹", True)
                return

            dest_root = Path("yinse")
            dest_root.mkdir(parents=True, exist_ok=True)

            dest_dir = dest_root / src_dir.name
            if dest_dir.exists():
                base = dest_dir.name
                idx = 1
                while True:
                    candidate = dest_root / f"{base}_{idx}"
                    if not candidate.exists():
                        dest_dir = candidate
                        break
                    idx += 1

            # 仅复制音频文件，并保留原有子目录结构
            exts = {".wav", ".mp3", ".wma", ".flac", ".ogg", ".m4a", ".aac", ".opus"}
            count = 0
            try:
                for root, _dirs, files in os.walk(src_dir):
                    root_path = Path(root)
                    rel_root = root_path.relative_to(src_dir)
                    cur_dest = dest_dir / rel_root
                    cur_dest.mkdir(parents=True, exist_ok=True)
                    for f in files:
                        if Path(f).suffix.lower() not in exts:
                            continue
                        src_file = root_path / f
                        target_path = cur_dest / f
                        if target_path.exists():
                            base = target_path.stem
                            ext2 = target_path.suffix
                            idx = 1
                            while True:
                                candidate = cur_dest / f"{base}_{idx}{ext2}"
                                if not candidate.exists():
                                    target_path = candidate
                                    break
                                idx += 1
                        shutil.copy2(src_file, target_path)
                        count += 1
            except Exception as ex:
                # 出错时尽量清理已创建的目标目录，避免留下不完整结构
                try:
                    if dest_dir.exists():
                        shutil.rmtree(dest_dir)
                except Exception:
                    pass
                self.show_message(f"复制文件夹失败: {ex}", True)
                return

            # 如果没有任何音频文件被复制，删除空目录，避免污染音色库
            if count == 0:
                try:
                    if dest_dir.exists():
                        shutil.rmtree(dest_dir)
                except Exception:
                    pass
                self.show_message("所选文件夹中未找到音频文件", True)
                return

            self.show_message(f"已添加文件夹: {src_dir.name}（共 {count} 个音色文件）")

            try:
                self.refresh_voices()
                if hasattr(self, 'voice_library_list') and self.voice_library_list:
                    self.refresh_voice_library()
            except Exception:
                pass
        except Exception as ex:
            self.show_message(f"添加音色文件夹失败: {ex}", True)

    # =========================
    # 自动更新功能
    # =========================
    def check_for_updates(self, e=None, silent=False):
        """检查更新"""
        update_url = self.config_manager.get("update_url", "")
        if not update_url:
            if not silent:
                self.show_message("请先在设置中配置更新地址", is_error=True)
            return

        def check_thread():
            try:
                # 假设 version.json 格式: {"version": "3.5.0", "url": "http://...", "changelog": "..."}
                full_url = f"{update_url}/version.json" if not update_url.endswith("version.json") else update_url
                self.log_manager.info(f"正在检查更新: {full_url}")
                resp = requests.get(full_url, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    remote_ver = data.get("version")
                    if remote_ver and remote_ver > self.app_version:
                        self.log_manager.info(f"发现新版本: {remote_ver}")
                        # 在主线程显示对话框
                        if self.page:
                            self.show_update_dialog(data)
                    else:
                        self.log_manager.info("当前已是最新版本")
                        if not silent and self.page:
                            self.show_message("当前已是最新版本")
                else:
                    err_msg = f"检查更新失败: HTTP {resp.status_code}"
                    self.log_manager.error(err_msg)
                    if not silent and self.page:
                        self.show_message(err_msg, is_error=True)
            except Exception as ex:
                err_msg = f"检查更新出错: {ex}"
                self.log_manager.error(err_msg)
                if not silent and self.page:
                    self.show_message(err_msg, is_error=True)
        
        threading.Thread(target=check_thread, daemon=True).start()

    def show_update_dialog(self, data):
        """显示更新确认对话框"""
        ver = data.get("version", "未知版本")
        changelog = data.get("changelog", "无更新日志")
        url = data.get("url", "")
        
        def on_confirm(e):
            self.page.close(dlg)
            self.perform_update(url)
            
        def on_cancel(e):
            self.page.close(dlg)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"发现新版本 {ver}"),
            content=ft.Column([
                ft.Text("更新日志:", weight=ft.FontWeight.BOLD),
                ft.Text(changelog, size=13),
                ft.Text("\n是否立即更新？", weight=ft.FontWeight.BOLD),
            ], tight=True, width=400),
            actions=[
                ft.TextButton("稍后", on_click=on_cancel),
                ft.ElevatedButton("立即更新", on_click=on_confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.open(dlg)
        self.page.update()

    def perform_update(self, download_url):
        """执行更新下载和安装"""
        if not download_url:
            self.show_message("更新链接无效", is_error=True)
            return
            
        progress_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("正在更新"),
            content=ft.Column([
                ft.ProgressBar(width=400),
                ft.Text("正在下载更新包...", size=12),
            ], tight=True, alignment=ft.MainAxisAlignment.CENTER),
        )
        self.page.open(progress_dlg)
        self.page.update()
        
        def update_thread():
            try:
                # 1. 下载
                temp_dir = tempfile.mkdtemp()
                zip_path = os.path.join(temp_dir, "update.zip")
                
                self.log_manager.info(f"开始下载更新: {download_url}")
                resp = requests.get(download_url, stream=True, timeout=30)
                resp.raise_for_status()
                
                with open(zip_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                        
                self.log_manager.info("下载完成，正在准备安装...")
                
                # 2. 生成更新脚本
                updater_script = os.path.join(temp_dir, "updater.bat")
                current_pid = os.getpid()
                target_dir = os.getcwd()
                python_exe = sys.executable
                main_script = os.path.join(target_dir, "src", "main.py")
                
                # 解压命令 (powershell)
                extract_cmd = f'Expand-Archive -Path "{zip_path}" -DestinationPath "{temp_dir}\\extracted" -Force'
                
                # 批处理脚本内容
                bat_content = f"""@echo off
timeout /t 2 /nobreak
taskkill /F /PID {current_pid}
powershell -Command "{extract_cmd}"
xcopy /s /e /y "{temp_dir}\\extracted\\*" "{target_dir}"
start "" "{python_exe}" "{main_script}"
"""
                with open(updater_script, "w") as f:
                    f.write(bat_content)
                
                self.log_manager.info(f"启动更新脚本: {updater_script}")
                
                # 3. 运行脚本并退出
                subprocess.Popen([updater_script], shell=True)
                os._exit(0)
                
            except Exception as ex:
                self.log_manager.error(f"更新失败: {ex}")
                self.show_message(f"更新失败: {ex}", is_error=True)
                self.page.close(progress_dlg)

        threading.Thread(target=update_thread, daemon=True).start()

    def open_batch_edit_dialog(self, e):
        show_batch_edit_dialog(self, e)

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
