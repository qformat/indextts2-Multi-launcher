import flet as ft
import os
from src.core.utils import calculate_character_length, cn_han_count

def show_batch_edit_dialog(app, e=None):
    """打开批量编辑对话框（按行编辑布局）"""
    if not hasattr(app, 'subtitle_segments') or not app.subtitle_segments:
        app.show_message("没有字幕内容可编辑", True)
        return

    if not hasattr(app, 'subtitle_line_roles'):
        app.subtitle_line_roles = {}

    # 角色选项（含“未分配”）
    def build_role_options():
        # 合并当前角色列表与已分配角色，避免打开时丢失已配置角色
        # 使用 Option(key, text) 确保下拉项显示文本与值一致
        opts = [ft.dropdown.Option("未分配", "未分配")]
        seen = set(["未分配"])  # 预先加入“未分配”
        # 来自角色列表的角色
        if hasattr(app, 'subtitle_roles') and app.subtitle_roles:
            for r in app.subtitle_roles.keys():
                if r and r not in seen:
                    opts.append(ft.dropdown.Option(r, r))
                    seen.add(r)
        # 来自已分配映射的角色（可能不在角色列表中）
        if hasattr(app, 'subtitle_line_roles') and app.subtitle_line_roles:
            for r in app.subtitle_line_roles.values():
                if r and r != "未分配" and r not in seen:
                    opts.append(ft.dropdown.Option(r, r))
                    seen.add(r)
        return opts

    role_options = build_role_options()

    # 初始化阶段标记：避免在构建对话框控件过程中触发实时同步导致主预览临时清空或重置
    initializing_dialog = True

    # 深色模式配色变量（提高对比度与可读性）
    is_dark = bool(getattr(app, "page", None) and app.page.theme_mode == ft.ThemeMode.DARK)
    primary_text = ft.Colors.WHITE if is_dark else ft.Colors.BLACK87
    secondary_text = ft.Colors.GREY_300 if is_dark else ft.Colors.GREY_600
    panel_bg = ft.Colors.BLUE_GREY_900 if is_dark else ft.Colors.GREY_100
    panel_border = ft.Colors.GREY_700 if is_dark else ft.Colors.GREY_200
    control_button_bg = ft.Colors.BLUE_GREY_800 if is_dark else ft.Colors.GREY_100
    control_button_text = ft.Colors.WHITE if is_dark else ft.Colors.BLACK87
    slider_active = ft.Colors.BLUE_400
    slider_inactive = ft.Colors.GREY_700 if is_dark else ft.Colors.GREY_300
    lines_container_bg = ft.Colors.BLACK87 if is_dark else ft.Colors.WHITE

    # 辅助：根据角色获取音色显示名
    def voice_name_for_role(role_name: str | None):
        if not role_name or role_name == "未分配":
            return ""
        if hasattr(app, 'subtitle_roles') and role_name in app.subtitle_roles:
            vp = app.subtitle_roles[role_name]
            return os.path.basename(vp) if vp else "未选择"
        return ""

    # 统计文本
    def compute_stats(text_fields):
        line_count = len(text_fields)
        char_count = sum(len(tf.value or "") for tf in text_fields)
        return f"总行数: {line_count} | 总字符数: {char_count}"

    stats_text = ft.Text(size=12, color=secondary_text)

    # 批量情感设置（统一向量调节并批量应用）
    batch_vec_names = getattr(app, 'vec_names', ["喜", "怒", "哀", "惧", "厌恶", "低落", "惊喜", "平静"])
    batch_emotion_values: list[float] = [0.0] * 8
    batch_emotion_labels: list[ft.Text] = []
    batch_emotion_sliders: list[ft.Slider] = []

    def format_batch_label(idx: int, val: float) -> str:
        name = batch_vec_names[idx] if idx < len(batch_vec_names) else f"E{idx+1}"
        return f"{name}: {val:.2f}"

    def on_batch_slider_change(e, idx: int):
        try:
            v = float(e.control.value or 0.0)
        except Exception:
            v = 0.0
        batch_emotion_values[idx] = v
        if 0 <= idx < len(batch_emotion_labels):
            batch_emotion_labels[idx].value = format_batch_label(idx, v)
            try:
                batch_emotion_labels[idx].update()
            except AssertionError:
                pass

    batch_vec_rows = []
    for i in range(8):
        lbl = ft.Text(format_batch_label(i, batch_emotion_values[i]), size=11, color=secondary_text)
        sld = ft.Slider(
            min=0.0,
            max=1.0,
            divisions=100,
            value=batch_emotion_values[i],
            width=240,
            active_color=slider_active,
            inactive_color=slider_inactive,
            on_change=lambda e, ii=i: on_batch_slider_change(e, ii)
        )
        batch_emotion_labels.append(lbl)
        batch_emotion_sliders.append(sld)
    # 两行展示（4+4）
    batch_controls_row1 = ft.Row([ft.Column([batch_emotion_labels[i], batch_emotion_sliders[i]], spacing=4) for i in range(0,4)], spacing=12)
    batch_controls_row2 = ft.Row([ft.Column([batch_emotion_labels[i], batch_emotion_sliders[i]], spacing=4) for i in range(4,8)], spacing=12)

    def apply_batch_emotions_all(_e=None):
        # 将批量向量应用到所有行
        for i in range(len(line_emotion_values)):
            line_emotion_values[i] = [float(v) for v in batch_emotion_values[:8]]
            if 0 <= i < len(line_emotions_labels):
                line_emotions_labels[i].value = format_emotion_summary(line_emotion_values[i])
                try:
                    line_emotions_labels[i].update()
                except AssertionError:
                    pass
        # 重建行，刷新各行面板以展示新值
        rebuild_rows()
        try:
            lines_column.update()
        except AssertionError:
            pass

    def apply_batch_emotions_empty(_e=None):
        # 将批量向量应用到尚未设置（全零）的行
        for i in range(len(line_emotion_values)):
            cur = line_emotion_values[i] if isinstance(line_emotion_values[i], list) else [0.0]*8
            s = 0.0
            try:
                s = sum(abs(float(x)) for x in cur[:8])
            except Exception:
                s = 0.0
            if s <= 1e-6:
                line_emotion_values[i] = [float(v) for v in batch_emotion_values[:8]]
                if 0 <= i < len(line_emotions_labels):
                    line_emotions_labels[i].value = format_emotion_summary(line_emotion_values[i])
                    try:
                        line_emotions_labels[i].update()
                    except AssertionError:
                        pass
        rebuild_rows()
        try:
            lines_column.update()
        except AssertionError:
            pass

    def clear_all_emotions(_e=None):
        for i in range(len(line_emotion_values)):
            line_emotion_values[i] = [0.0]*8
            if 0 <= i < len(line_emotions_labels):
                line_emotions_labels[i].value = format_emotion_summary(line_emotion_values[i])
                try:
                    line_emotions_labels[i].update()
                except AssertionError:
                    pass
        rebuild_rows()
        try:
            lines_column.update()
        except AssertionError:
            pass

    def toggle_all_emotions(_e=None):
        # 展开/折叠所有行的情感面板
        vis = None
        for i in range(len(line_emotion_panels)):
            if vis is None:
                vis = not bool(line_emotion_panels[i].visible)
            line_emotion_panels[i].visible = vis
        try:
            lines_column.update()
        except AssertionError:
            pass

    def copy_global_to_batch(_e=None):
        # 从全局情感滑条复制当前值到批量向量
        if getattr(app, 'vec_sliders', None):
            for i in range(min(8, len(app.vec_sliders))):
                try:
                    val = float(app.vec_sliders[i].value or 0.0)
                except Exception:
                    val = 0.0
                batch_emotion_values[i] = val
                batch_emotion_sliders[i].value = val
                batch_emotion_labels[i].value = format_batch_label(i, val)
            try:
                batch_controls_container.update()
            except AssertionError:
                pass
        else:
            app.show_message("未找到全局情感滑条，已保持默认", True)

    # 行编辑控件集合
    line_text_fields: list[ft.TextField] = []
    line_role_dropdowns: list[ft.Dropdown] = []
    line_role_voice_labels: list[ft.Text] = []
    line_emotion_values: list[list[float]] = []
    line_emotions_labels: list[ft.Text] = []
    line_speed_values: list[float] = []
    line_speed_labels: list[ft.Text] = []
    line_emotion_panels: list[ft.Container] = []
    lines_column = ft.Column(spacing=4, scroll=ft.ScrollMode.ALWAYS)

    def create_emotion_panel(idx: int) -> ft.Container:
        panel = ft.Container(
            content=None,
            padding=8,
            bgcolor=panel_bg,
            border=ft.border.all(1, panel_border),
            border_radius=8,
            visible=False,
        )
        return panel

    def ensure_emotion_panel_content(idx: int):
        if 0 <= idx < len(line_emotion_panels):
            panel = line_emotion_panels[idx]
            if panel.content is None:
                init_vals = line_emotion_values[idx] if 0 <= idx < len(line_emotion_values) else [0.0] * 8
                vec_names = getattr(app, 'vec_names', ["喜", "怒", "哀", "惧", "厌恶", "低落", "惊喜", "平静"])
                labels = []
                sliders = []
                for i in range(8):
                    val = float(init_vals[i] if i < len(init_vals) else 0.0)
                    name = vec_names[i] if i < len(vec_names) else f"E{i+1}"
                    t = ft.Text(f"{name}: {val:.2f}", size=10, color=secondary_text)
                    s = ft.Slider(
                        min=0.0,
                        max=1.0,
                        divisions=100,
                        value=val,
                        width=160,
                        active_color=slider_active,
                        inactive_color=slider_inactive,
                    )
                    def _on_change(e, ii=i, tt=t, nm=name):
                        vv = float(e.control.value or 0.0)
                        tt.value = f"{nm}: {vv:.2f}"
                        if 0 <= idx < len(line_emotion_values):
                            cur = line_emotion_values[idx]
                            if not isinstance(cur, list):
                                cur = [0.0] * 8
                            while len(cur) < 8:
                                cur.append(0.0)
                            cur[ii] = vv
                            line_emotion_values[idx] = cur
                            if 0 <= idx < len(line_emotions_labels):
                                line_emotions_labels[idx].value = format_emotion_summary(line_emotion_values[idx])
                                try:
                                    line_emotions_labels[idx].update()
                                except AssertionError:
                                    pass
                        try:
                            tt.update()
                        except AssertionError:
                            pass
                    s.on_change = _on_change
                    labels.append(t)
                    sliders.append(s)
                content = ft.Column([
                    ft.Row([ft.Column([labels[i], sliders[i]], spacing=4) for i in range(0, 4)], alignment=ft.MainAxisAlignment.START, spacing=8),
                    ft.Row([ft.Column([labels[i], sliders[i]], spacing=4) for i in range(4, 8)], alignment=ft.MainAxisAlignment.START, spacing=8),
                ], spacing=10)
                panel.content = content

    def toggle_emotions(idx: int):
        if 0 <= idx < len(line_emotion_panels):
            ensure_emotion_panel_content(idx)
            line_emotion_panels[idx].visible = not bool(line_emotion_panels[idx].visible)
            try:
                lines_column.update()
            except AssertionError:
                pass

    # 行操作函数
    cursor_pos_map = {}
    cursor_pos_map_idx = {}
    mutating_flag = False
    batch_edit_active = True
    active_line_index = -1
    prev_keyboard_handler = getattr(app.page, 'on_keyboard_event', None)

    def request_merge_up(idx: int):
        try:
            if 0 <= idx < len(line_text_fields):
                pos = cursor_pos_map_idx.get(idx)
                if isinstance(pos, int) and 0 <= pos <= len(line_text_fields[idx].value or ""):
                    merge_up(idx)
                else:
                    app.show_message("未记录光标位置：请在该行点击一次以记录光标后再按 Alt+↑", True)
        except Exception:
            pass
    def merge_up(idx: int):
        try:
            if idx > 0:
                prev = line_text_fields[idx-1]
                cur = line_text_fields[idx]
                txt = cur.value or ""
                pos = cursor_pos_map_idx.get(idx)
                if not isinstance(pos, int) or not (0 <= pos <= len(txt)):
                    return
                left = txt[:pos]
                right = txt[pos:]
                prev.value = (prev.value or "") + left
                cur.value = right
                if not (right or "").strip():
                    remove_line(idx)
                app.safe_update(lines_column)
            else:
                app.show_message("首行无法向上合并", True)
        except Exception:
            pass

    def merge_up_by_caret(idx: int):
        try:
            if 0 <= idx < len(line_text_fields):
                if idx == 0:
                    app.show_message("首行无法向上合并", True)
                    return
                cur = line_text_fields[idx]
                prev = line_text_fields[idx-1]
                txt = cur.value or ""
                pos = cursor_pos_map_idx.get(idx)
                if not isinstance(pos, int):
                    try:
                        pos = cursor_pos_map.get(cur)
                    except Exception:
                        pos = None
                if not isinstance(pos, int):
                    pos = getattr(cur, 'cursor_position', None)
                if not isinstance(pos, int) or not (0 <= pos <= len(txt)):
                    app.show_message("未记录光标位置：请在该行点击一次以记录光标", True)
                    return
                left = txt[:pos]
                right = txt[pos:]
                prev.value = (prev.value or "") + left
                cur.value = right
                if not (right or "").strip():
                    remove_line(idx)
                else:
                    try:
                        if idx - 1 < len(lines_column.controls):
                            lines_column.controls[idx - 1] = build_row(idx - 1)
                        if idx < len(lines_column.controls):
                            lines_column.controls[idx] = build_row(idx)
                    except Exception:
                        pass
                update_stats_only()
                app.safe_update(lines_column)
        except Exception:
            pass

    def build_row(i: int) -> ft.Column:
        tf = line_text_fields[i]
        dd = line_role_dropdowns[i]
        voice_label = line_role_voice_labels[i]
        emo_label = line_emotions_labels[i]
        def _on_focus(e=None, local_tf=tf):
            nonlocal active_line_index
            try:
                active_line_index = line_text_fields.index(local_tf)
            except Exception:
                active_line_index = i
        tf.on_focus = _on_focus
        def _on_dd_change(e, idx=i):
            val = e.control.value
            vn = voice_name_for_role(val)
            voice_label.value = f"音色: {vn}" if vn else ""
            app.safe_update(voice_label)
        dd.on_change = _on_dd_change
        speed_col = ft.Column([
            line_speed_labels[i],
            ft.Slider(
                min=0.1,
                max=2.0,
                divisions=38,
                value=float(line_speed_values[i] if i < len(line_speed_values) else 1.0),
                label="",
                on_change=lambda e, idx=i: (
                    line_speed_values.__setitem__(idx, float(e.control.value or 1.0)),
                    setattr(line_speed_labels[idx], "value", f"语速: {float(e.control.value or 1.0):.2f}x"),
                    app.safe_update(line_speed_labels[idx])
                ),
                width=160
            )
        ], spacing=4)
        row = ft.Row([
            ft.Text(f"{i+1:02d}.", width=32, text_align=ft.TextAlign.RIGHT, size=11, color=secondary_text),
            tf,
            dd,
            voice_label,
            speed_col,
            emo_label,
            ft.TextButton(
                "情感向量",
                on_click=lambda _e, idx=i: toggle_emotions(idx),
                style=ft.ButtonStyle(
                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                    bgcolor=control_button_bg,
                    color=control_button_text,
                ),
            ),
            ft.IconButton(icon=ft.Icons.ARROW_UPWARD, tooltip="上移", icon_size=18, icon_color=ft.Colors.BLUE, on_click=lambda _e, idx=i: move_up(idx)),
            ft.IconButton(icon=ft.Icons.ARROW_DOWNWARD, tooltip="下移", icon_size=18, icon_color=ft.Colors.BLUE, on_click=lambda _e, idx=i: move_down(idx)),
            ft.IconButton(icon=ft.Icons.DELETE, tooltip="删除", icon_size=18, icon_color=ft.Colors.RED, on_click=lambda _e, idx=i: remove_line(idx)),
        ], alignment=ft.MainAxisAlignment.START, spacing=6)
        if i >= len(line_emotion_panels):
            line_emotion_panels.append(create_emotion_panel(i))
        panel = line_emotion_panels[i] if i < len(line_emotion_panels) else create_emotion_panel(i)
        return ft.Column([row, panel], spacing=6)

    def rebuild_rows():
        nonlocal mutating_flag
        mutating_flag = True
        # 对齐各列表长度，避免索引错误
        max_n = len(line_text_fields)
        while len(line_role_dropdowns) < max_n:
            line_role_dropdowns.append(ft.Dropdown(width=150, options=role_options, value="未分配", hint_text="选择角色", dense=True, text_size=12, content_padding=ft.padding.symmetric(vertical=4, horizontal=8)))
        while len(line_role_voice_labels) < max_n:
            line_role_voice_labels.append(ft.Text("", size=10, color=secondary_text))
        while len(line_emotion_values) < max_n:
            line_emotion_values.append([0.0]*8)
        while len(line_emotions_labels) < max_n:
            line_emotions_labels.append(ft.Text("情感向量未设", size=10, color=secondary_text))
        while len(line_speed_labels) < max_n:
            line_speed_labels.append(ft.Text("语速: 1.00x", size=10, color=secondary_text))
        while len(line_speed_values) < max_n:
            line_speed_values.append(1.0)
        while len(line_emotion_panels) < max_n:
            line_emotion_panels.append(create_emotion_panel(len(line_emotion_panels)))
        lines_column.controls = [build_row(i) for i in range(max_n)]
        stats_text.value = compute_stats(line_text_fields)
        mutating_flag = False

    def format_emotion_summary(vals: list[float] | None):
        try:
            if not vals:
                return "情感向量未设"
            s = sum(abs(float(v)) for v in vals[:8])
            return f"情感向量Σ={s:.2f}" if s > 0 else "情感向量未设"
        except Exception:
            return "情感向量未设"

    # 旧的弹窗情感向量编辑已替换为行内面板

    def add_line(_e=None, content: str = "", role: str | None = None, emo_vals: list[float] | None = None):
        tf = ft.TextField(value=content, expand=True, multiline=True, min_lines=1, max_lines=2, text_size=12, height=44, content_padding=ft.padding.symmetric(vertical=6, horizontal=8))
        def _on_focus(e=None, local_tf=tf):
            nonlocal active_line_index
            try:
                active_line_index = line_text_fields.index(local_tf)
            except Exception:
                active_line_index = -1
        tf.on_focus = _on_focus
        def _on_selection_change(e, local_tf=tf):
            try:
                sel = getattr(e, 'selection', None)
                if sel is not None:
                    pos = int(getattr(sel, 'start', 0))
                    setattr(local_tf, 'cursor_position', pos)
                    cursor_pos_map[local_tf] = pos
                    try:
                        cur_i = line_text_fields.index(local_tf)
                        cursor_pos_map_idx[cur_i] = pos
                    except Exception:
                        pass
                    try:
                        active_line_index = line_text_fields.index(local_tf)
                    except Exception:
                        pass
            except Exception:
                pass
        tf.on_selection_change = _on_selection_change
        def _on_tf_change(_e, local_tf=tf):
            try:
                val = local_tf.value or ""
                if "\n" in val:
                    idx = val.find("\n")
                    left = val[:idx]
                    right = val[idx+1:]
                    try:
                        cur_i = line_text_fields.index(local_tf)
                    except Exception:
                        cur_i = -1
                    if bool(getattr(app, 'enter_merge_up', False)) and cur_i > 0:
                        prev_tf = line_text_fields[cur_i - 1]
                        prev_tf.value = (prev_tf.value or "") + left
                        local_tf.value = right
                        if not (right or "").strip():
                            remove_line(cur_i)
                        else:
                            try:
                                if cur_i - 1 < len(lines_column.controls):
                                    lines_column.controls[cur_i - 1] = build_row(cur_i - 1)
                                if cur_i < len(lines_column.controls):
                                    lines_column.controls[cur_i] = build_row(cur_i)
                            except Exception:
                                pass
                        update_stats_only()
                        app.safe_update(lines_column)
                    else:
                        local_tf.value = left
                        if right and cur_i >= 0:
                            insert_line_at(cur_i + 1, right)
                        app.safe_update(lines_column)
            except Exception:
                pass
            update_stats_only()
            if not initializing_dialog and not batch_edit_active:
                sync_to_preview()
        tf.on_change = _on_tf_change
        def _on_tf_submit(_e, local_tf=tf):
            try:
                txt = local_tf.value or ""
                pos = None
                try:
                    sel = getattr(local_tf, 'selection', None)
                    pos = int(getattr(sel, 'start', 0)) if sel is not None else None
                except Exception:
                    pos = getattr(local_tf, 'cursor_position', None)
                if isinstance(pos, int) and 0 <= pos <= len(txt):
                    left = txt[:pos]
                    right = txt[pos:]
                else:
                    left = txt
                    right = ""

                if bool(getattr(app, 'enter_merge_up', False)):
                    try:
                        cur_i = line_text_fields.index(local_tf)
                    except Exception:
                        cur_i = -1
                    if cur_i > 0:
                        prev_tf = line_text_fields[cur_i - 1]
                        prev_tf.value = (prev_tf.value or "") + left
                        local_tf.value = right
                        try:
                            # 重建受影响的两行
                            if cur_i - 1 < len(lines_column.controls):
                                lines_column.controls[cur_i - 1] = build_row(cur_i - 1)
                            if cur_i < len(lines_column.controls):
                                lines_column.controls[cur_i] = build_row(cur_i)
                        except Exception:
                            pass
                        if not (right or "").strip():
                            remove_line(cur_i)
                        update_stats_only()
                        app.safe_update(lines_column)
                    return

                # 默认：按回车分行（向下插入）
                local_tf.value = left
                if right:
                    try:
                        cur_i = line_text_fields.index(local_tf)
                    except Exception:
                        cur_i = -1
                    if cur_i >= 0:
                        insert_line_at(cur_i + 1, right)
                update_stats_only()
                app.safe_update(lines_column)
            except Exception:
                pass
        tf.on_submit = _on_tf_submit
        # 改进角色初始化逻辑：如果传入的角色存在于当前角色列表中，则使用它；否则使用"未分配"
        role_option_texts = [opt.text for opt in role_options]
        if role and role in role_option_texts:
            init_role = role
        else:
            init_role = "未分配"
        dd = ft.Dropdown(
            width=150,
            options=role_options,
            value=init_role,
            hint_text="选择角色",
            dense=True,
            text_size=12,
            content_padding=ft.padding.symmetric(vertical=4, horizontal=8),
        )
        vn = voice_name_for_role(init_role)
        voice_label = ft.Text(f"音色: {vn}" if vn else "", size=10, color=secondary_text)
        ev = emo_vals if isinstance(emo_vals, list) and len(emo_vals) >= 8 else [0.0] * 8
        emo_label = ft.Text(format_emotion_summary(ev), size=10, color=secondary_text)
        line_text_fields.append(tf)
        line_role_dropdowns.append(dd)
        line_role_voice_labels.append(voice_label)
        line_emotion_values.append(ev)
        line_emotions_labels.append(emo_label)
        idx = len(line_text_fields) - 1
        line_emotion_panels.append(create_emotion_panel(idx))
        try:
            default_speed = 1.0
            if hasattr(app, 'subtitle_line_speeds') and isinstance(app.subtitle_line_speeds, dict):
                s = app.subtitle_line_speeds.get(idx)
                if s is not None:
                    default_speed = float(s)
            lbl = ft.Text(f"语速: {default_speed:.2f}x", size=10, color=secondary_text)
            line_speed_labels.append(lbl)
            line_speed_values.append(default_speed)
        except Exception:
            lbl = ft.Text(f"语速: 1.00x", size=10, color=secondary_text)
            line_speed_labels.append(lbl)
            line_speed_values.append(1.0)
        block = build_row(idx)
        lines_column.controls.append(block)
        stats_text.value = compute_stats(line_text_fields)
        if not initializing_dialog:
            app.safe_update(lines_column)

    def insert_line_at(pos: int, content: str, role: str | None = None, emo_vals: list[float] | None = None):
        try:
            tf = ft.TextField(value=content, expand=True, multiline=True, min_lines=1, max_lines=2, text_size=12, height=44, content_padding=ft.padding.symmetric(vertical=6, horizontal=8))
            def _on_selection_change(e, local_tf=tf):
                try:
                    sel = getattr(e, 'selection', None)
                    if sel is not None:
                        pos2 = int(getattr(sel, 'start', 0))
                        setattr(local_tf, 'cursor_position', pos2)
                        cursor_pos_map[local_tf] = pos2
                        try:
                            cur_i2 = line_text_fields.index(local_tf)
                            cursor_pos_map_idx[cur_i2] = pos2
                        except Exception:
                            pass
                        try:
                            active_line_index = line_text_fields.index(local_tf)
                        except Exception:
                            pass
                except Exception:
                    pass
            tf.on_selection_change = _on_selection_change
            def _on_focus_ins(e=None, local_tf=tf):
                nonlocal active_line_index
                try:
                    active_line_index = line_text_fields.index(local_tf)
                except Exception:
                    active_line_index = -1
            tf.on_focus = _on_focus_ins
            def _on_tf_change(_e, local_tf=tf):
                try:
                    val = local_tf.value or ""
                    if "\n" in val:
                        idx2 = val.find("\n")
                        left2 = val[:idx2]
                        right2 = val[idx2+1:]
                        try:
                            cur_i2 = line_text_fields.index(local_tf)
                        except Exception:
                            cur_i2 = -1
                        if bool(getattr(app, 'enter_merge_up', False)) and cur_i2 > 0:
                            prev_tf2 = line_text_fields[cur_i2 - 1]
                            prev_tf2.value = (prev_tf2.value or "") + left2
                            local_tf.value = right2
                            if not (right2 or "").strip():
                                remove_line(cur_i2)
                            else:
                                try:
                                    if cur_i2 - 1 < len(lines_column.controls):
                                        lines_column.controls[cur_i2 - 1] = build_row(cur_i2 - 1)
                                    if cur_i2 < len(lines_column.controls):
                                        lines_column.controls[cur_i2] = build_row(cur_i2)
                                except Exception:
                                    pass
                            update_stats_only()
                            app.safe_update(lines_column)
                        else:
                            local_tf.value = left2
                            if right2 and cur_i2 >= 0:
                                insert_line_at(cur_i2 + 1, right2)
                            app.safe_update(lines_column)
                except Exception:
                    pass
                update_stats_only()
                if not initializing_dialog and not batch_edit_active:
                    sync_to_preview()
            tf.on_change = _on_tf_change
            def _on_tf_submit(_e, local_tf=tf):
                try:
                    txt2 = local_tf.value or ""
                    pos2 = None
                    try:
                        sel2 = getattr(local_tf, 'selection', None)
                        pos2 = int(getattr(sel2, 'start', 0)) if sel2 is not None else None
                    except Exception:
                        pos2 = getattr(local_tf, 'cursor_position', None)
                    if isinstance(pos2, int) and 0 <= pos2 <= len(txt2):
                        left2 = txt2[:pos2].strip()
                        right2 = txt2[pos2:].strip()
                    else:
                        left2 = txt2.strip()
                        right2 = ""
                    local_tf.value = left2
                    try:
                        cur_i2 = line_text_fields.index(local_tf)
                    except Exception:
                        cur_i2 = -1
                    if right2 and cur_i2 >= 0:
                        insert_line_at(cur_i2 + 1, right2)
                    update_stats_only()
                    app.safe_update(lines_column)
                except Exception:
                    pass
            tf.on_submit = _on_tf_submit

            role_option_texts2 = [opt.text for opt in role_options]
            init_role2 = role if (role and role in role_option_texts2) else "未分配"
            dd2 = ft.Dropdown(width=150, options=role_options, value=init_role2, hint_text="选择角色", dense=True, text_size=12, content_padding=ft.padding.symmetric(vertical=4, horizontal=8))
            vn2 = voice_name_for_role(init_role2)
            voice_label2 = ft.Text(f"音色: {vn2}" if vn2 else "", size=10, color=secondary_text)
            ev2 = emo_vals if isinstance(emo_vals, list) and len(emo_vals) >= 8 else [0.0] * 8
            emo_label2 = ft.Text(format_emotion_summary(ev2), size=10, color=secondary_text)

            default_speed2 = 1.0
            lbl2 = ft.Text(f"语速: {default_speed2:.2f}x", size=10, color=secondary_text)

            line_text_fields.insert(pos, tf)
            line_role_dropdowns.insert(pos, dd2)
            line_role_voice_labels.insert(pos, voice_label2)
            line_emotion_values.insert(pos, ev2)
            line_emotions_labels.insert(pos, emo_label2)
            line_speed_labels.insert(pos, lbl2)
            line_speed_values.insert(pos, default_speed2)
            line_emotion_panels.insert(pos, create_emotion_panel(pos))

            rebuild_rows()
            app.safe_update(lines_column)
        except Exception:
            pass

    def remove_line(idx: int):
        nonlocal mutating_flag
        if mutating_flag:
            return
        if 0 <= idx < len(line_text_fields):
            try:
                mutating_flag = True
                for arr in [line_text_fields, line_role_dropdowns, line_role_voice_labels, line_emotion_values, line_emotions_labels, line_speed_labels, line_speed_values, line_emotion_panels]:
                    if idx < len(arr):
                        del arr[idx]
                # 增量重建受影响的行
                for j in range(idx, len(line_text_fields)):
                    if j < len(lines_column.controls):
                        lines_column.controls[j] = build_row(j)
                # 删除最后一个控件块
                if len(lines_column.controls) > len(line_text_fields):
                    try:
                        lines_column.controls.pop()
                    except Exception:
                        pass
                stats_text.value = compute_stats(line_text_fields)
                app.safe_update(lines_column)
            except Exception:
                pass
            finally:
                mutating_flag = False
            # 删除后不进行主预览实时同步，保留到保存时统一更新

    def move_up(idx: int):
        if 1 <= idx < len(line_text_fields):
            line_text_fields[idx-1], line_text_fields[idx] = line_text_fields[idx], line_text_fields[idx-1]
            line_role_dropdowns[idx-1], line_role_dropdowns[idx] = line_role_dropdowns[idx], line_role_dropdowns[idx-1]
            line_role_voice_labels[idx-1], line_role_voice_labels[idx] = line_role_voice_labels[idx], line_role_voice_labels[idx-1]
            line_emotion_values[idx-1], line_emotion_values[idx] = line_emotion_values[idx], line_emotion_values[idx-1]
            line_emotions_labels[idx-1], line_emotions_labels[idx] = line_emotions_labels[idx], line_emotions_labels[idx-1]
            line_emotion_panels[idx-1], line_emotion_panels[idx] = line_emotion_panels[idx], line_emotion_panels[idx-1]
            # 增量更新受影响的两行
            lines_column.controls[idx-1] = build_row(idx-1)
            lines_column.controls[idx] = build_row(idx)
            app.safe_update(lines_column)
            # 上移后不进行主预览实时同步，保留到保存时统一更新

    def move_down(idx: int):
        if 0 <= idx < len(line_text_fields)-1:
            line_text_fields[idx+1], line_text_fields[idx] = line_text_fields[idx], line_text_fields[idx+1]
            line_role_dropdowns[idx+1], line_role_dropdowns[idx] = line_role_dropdowns[idx], line_role_dropdowns[idx+1]
            line_role_voice_labels[idx+1], line_role_voice_labels[idx] = line_role_voice_labels[idx], line_role_voice_labels[idx+1]
            line_emotion_values[idx+1], line_emotion_values[idx] = line_emotion_values[idx], line_emotion_values[idx+1]
            line_emotions_labels[idx+1], line_emotions_labels[idx] = line_emotions_labels[idx], line_emotions_labels[idx+1]
            line_emotion_panels[idx+1], line_emotion_panels[idx] = line_emotion_panels[idx], line_emotion_panels[idx+1]
            # 增量更新受影响的两行
            lines_column.controls[idx] = build_row(idx)
            lines_column.controls[idx+1] = build_row(idx+1)
            app.safe_update(lines_column)
            # 下移后不进行主预览实时同步，保留到保存时统一更新

    def update_stats_only():
        stats_text.value = compute_stats(line_text_fields)
        try:
            stats_text.update()
        except AssertionError:
            pass

    # 实时同步到主预览：收集当前行内容和角色并刷新预览
    def sync_to_preview():
        # 收集行内容，过滤空行
        new_segments = []
        for tf in line_text_fields:
            val = (tf.value or "").strip()
            if val:
                new_segments.append(val)

        # 更新主数据
        app.subtitle_segments = new_segments
        app.edited_subtitles = new_segments.copy()

        # 更新角色映射
        app.subtitle_line_roles = {}
        for i in range(min(len(line_role_dropdowns), len(new_segments))):
            v = line_role_dropdowns[i].value
            if v and v != "未分配":
                app.subtitle_line_roles[i] = v

        # 刷新主预览
        # 同步情感向量到预览数据（不持久化到配置，仅临时用于生成预览）
        if not hasattr(app, 'subtitle_line_emotions'):
            app.subtitle_line_emotions = {}
        temp_emotions = {}
        for i in range(len(new_segments)):
            if i < len(line_emotion_values):
                temp_emotions[i] = line_emotion_values[i]
            else:
                temp_emotions[i] = [0.0] * 8
        app.subtitle_line_emotions = temp_emotions

        app.update_subtitle_preview_simple()
        if hasattr(app, 'page') and app.page:
            try:
                app.page.update()
            except AssertionError:
                pass

    # 初始化行控件
    for i, seg in enumerate(app.subtitle_segments):
        current_role = app.subtitle_line_roles.get(i, "未分配")
        emo_vals = None
        if hasattr(app, 'subtitle_line_emotions') and isinstance(app.subtitle_line_emotions, dict):
            emo_vals = app.subtitle_line_emotions.get(i)
        add_line(content=seg, role=current_role, emo_vals=emo_vals)

    # 初始化完成后再允许实时同步
    rebuild_rows()
    initializing_dialog = False

    # 默认角色与批量操作
    default_role_dropdown = ft.Dropdown(
        label="默认角色",
        width=180,
        options=role_options,
        dense=True,
        text_size=12,
        content_padding=ft.padding.symmetric(vertical=4, horizontal=8),
    )

    def refresh_role_options(_e=None):
        nonlocal role_options
        role_options = build_role_options()
        default_role_dropdown.options = role_options
        try:
            default_role_dropdown.update()
        except Exception:
            pass
        # 获取新角色选项的文本列表
        role_option_texts = [opt.text for opt in role_options]
        for i, dd in enumerate(line_role_dropdowns):
            # 保存当前选中的角色
            current_value = dd.value
            # 更新选项列表
            dd.options = role_options
            # 只有当前选中的角色不在新选项中时才重置为"未分配"
            # 这样可以保留用户已配置的有效角色
            if current_value and current_value in role_option_texts:
                dd.value = current_value
            else:
                dd.value = "未分配"
            # 更新音色显示
            vn = voice_name_for_role(dd.value)
            line_role_voice_labels[i].value = f"音色: {vn}" if vn else ""
        try:
            lines_column.update()
        except Exception:
            pass

    def apply_default_role_all(_e):
        v = default_role_dropdown.value
        for i, dd in enumerate(line_role_dropdowns):
            dd.value = v
            vn = voice_name_for_role(v)
            line_role_voice_labels[i].value = f"音色: {vn}" if vn else ""
        app.safe_update(lines_column)
        # 默认角色应用后仅更新对话框，不触发主状态同步

    def apply_default_role_empty(_e):
        v = default_role_dropdown.value
        for i, dd in enumerate(line_role_dropdowns):
            if not dd.value or dd.value == "未分配":
                dd.value = v
                vn = voice_name_for_role(v)
                line_role_voice_labels[i].value = f"音色: {vn}" if vn else ""
        app.safe_update(lines_column)
        # 仅更新对话框，不触发主状态同步

    def clear_all_roles(_e):
        for i, dd in enumerate(line_role_dropdowns):
            dd.value = "未分配"
            line_role_voice_labels[i].value = ""
        app.safe_update(lines_column)
        # 仅更新对话框，不触发主状态同步

    def close_dialog(_e):
        try:
            dialog.open = False
            batch_edit_active = False
            if hasattr(app, 'page') and app.page:
                if getattr(app.page, 'dialog', None) is dialog:
                    app.page.dialog = dialog
                try:
                    app.page.on_keyboard_event = prev_keyboard_handler
                except Exception:
                    pass
                app.page.update()
        except Exception:
            pass

    def save_changes(_e):
        # 收集行内容，过滤空行
        new_segments = []
        for tf in line_text_fields:
            val = (tf.value or "").strip()
            if val:
                new_segments.append(val)

        if not new_segments:
            app.show_message("没有有效的字幕内容", True)
            return

        # 更新字幕与角色
        app.subtitle_segments = new_segments
        app.edited_subtitles = new_segments.copy()

        # 智能保留和更新角色分配
        # 1. 备份原有的角色分配
        old_line_roles = app.subtitle_line_roles.copy()
        
        # 2. 收集批量编辑对话框中的新分配
        new_line_roles = {}
        for i in range(min(len(line_role_dropdowns), len(new_segments))):
            v = line_role_dropdowns[i].value
            if v and v != "未分配":
                new_line_roles[i] = v
        
        # 3. 合并角色分配：优先使用新分配，保留未修改的原有分配
        final_line_roles = {}
        for i in range(len(new_segments)):
            if i in new_line_roles:
                # 使用批量编辑中的新分配
                final_line_roles[i] = new_line_roles[i]
            elif i in old_line_roles:
                # 保留原有分配
                final_line_roles[i] = old_line_roles[i]
        
        # 4. 更新角色分配
        app.subtitle_line_roles = final_line_roles

        # 4b. 更新情感向量分配
        final_line_emotions = {}
        for i in range(len(new_segments)):
            vals = line_emotion_values[i] if i < len(line_emotion_values) else [0.0] * 8
            final_line_emotions[i] = [float(vals[j] if j < len(vals) else 0.0) for j in range(8)]
        app.subtitle_line_emotions = final_line_emotions

        try:
            speeds_map = {}
            for i in range(len(new_segments)):
                sv = line_speed_values[i] if i < len(line_speed_values) else 1.0
                speeds_map[i] = float(sv)
            app.subtitle_line_speeds = speeds_map
        except Exception:
            pass

        # 持久化行情感向量到配置文件
        try:
            app.config_manager.set("subtitle_line_emotions", app.subtitle_line_emotions)
        except Exception:
            pass

        # 刷新预览
        app.update_subtitle_preview_simple()

        # 关闭对话框
        dialog.open = False
        batch_edit_active = False
        if hasattr(app, 'page') and app.page:
            try:
                app.page.on_keyboard_event = prev_keyboard_handler
            except Exception:
                pass
            app.page.update()

        app.show_message(f"批量编辑完成，共 {len(new_segments)} 行字幕")

    # 批量情感设置操作按钮
    batch_buttons_row = ft.Row([
        ft.TextButton("应用到全部行", on_click=apply_batch_emotions_all),
        ft.TextButton("应用到未设行", on_click=apply_batch_emotions_empty),
        ft.TextButton("清空所有行情感", on_click=clear_all_emotions),
        ft.TextButton("全部展开/折叠情感面板", on_click=toggle_all_emotions),
        ft.TextButton("从全局复制当前向量", on_click=copy_global_to_batch),
    ], alignment=ft.MainAxisAlignment.START)

    # 批量情感区域折叠/展开
    batch_controls_collapsed = True
    batch_controls_inner = ft.Column([
        batch_controls_row1,
        batch_controls_row2,
        batch_buttons_row,
    ], spacing=8, visible=False)
    batch_toggle_btn = ft.IconButton(icon=ft.Icons.KEYBOARD_ARROW_DOWN, tooltip="展开/折叠", icon_color=ft.Colors.DEEP_ORANGE)
    def toggle_batch_controls(_e=None):
        nonlocal batch_controls_collapsed
        batch_controls_collapsed = not batch_controls_collapsed
        batch_controls_inner.visible = not batch_controls_collapsed
        batch_toggle_btn.icon = ft.Icons.KEYBOARD_ARROW_UP if not batch_controls_collapsed else ft.Icons.KEYBOARD_ARROW_DOWN
        app.safe_update(batch_controls_container)
    batch_toggle_btn.on_click = toggle_batch_controls

    batch_controls_container = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.EMOJI_EMOTIONS, color=ft.Colors.DEEP_ORANGE),
                ft.Text("批量情感设置", weight=ft.FontWeight.BOLD, size=14, color=ft.Colors.DEEP_ORANGE),
                ft.Container(expand=True),
                batch_toggle_btn,
            ], spacing=8),
            batch_controls_inner,
        ], spacing=8),
        padding=10,
        bgcolor=panel_bg,
        border=ft.border.all(1, panel_border),
        border_radius=8,
    )

    ops_help = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.HELP, color=ft.Colors.BLUE),
                ft.Text("操作方法", weight=ft.FontWeight.BOLD, size=14, color=ft.Colors.BLUE),
            ], spacing=6),
            ft.Text("回车：在光标处分行（默认）", size=12, color=secondary_text),
            ft.Text("启用‘回车向上合并’后：回车在光标处向上合并", size=12, color=secondary_text),
        ], spacing=4),
        padding=8,
        bgcolor=panel_bg,
        border=ft.border.all(1, panel_border),
        border_radius=8,
    )

    # 对话框布局
    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Row([
            ft.Icon(ft.Icons.EDIT_NOTE, color=ft.Colors.BLUE, size=24),
            ft.Text("批量编辑字幕（按行）", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE),
        ], spacing=10),
        content=ft.Container(
            content=ft.Column([
                stats_text,
                ops_help,
                ft.Row([
                    ft.Checkbox(label="回车向上合并", value=bool(getattr(app, 'enter_merge_up', False)), on_change=lambda e: setattr(app, 'enter_merge_up', bool(e.control.value))),
                ], alignment=ft.MainAxisAlignment.START),
                ft.Row([
                    ft.TextButton("添加角色", icon=ft.Icons.PERSON_ADD, on_click=app.add_role),
                    ft.TextButton("刷新角色列表", icon=ft.Icons.REFRESH, on_click=refresh_role_options),
                ], alignment=ft.MainAxisAlignment.START),
                batch_controls_container,
                ft.Row([
                    default_role_dropdown,
                    ft.PopupMenuButton(
                        icon=ft.Icons.MORE_HORIZ,
                        items=[
                            ft.PopupMenuItem(text="应用默认角色到全部行", on_click=apply_default_role_all),
                            ft.PopupMenuItem(text="应用默认角色到空行", on_click=apply_default_role_empty),
                            ft.PopupMenuItem(text="清空所有角色", on_click=clear_all_roles),
                        ]
                    ),
                    ft.IconButton(icon=ft.Icons.ADD, tooltip="添加一行", on_click=add_line),
                ], alignment=ft.MainAxisAlignment.START),
                ft.Container(
                    content=lines_column,
                    expand=True,
                    padding=8,
                    bgcolor=lines_container_bg,
                    border=ft.border.all(1, panel_border),
                    border_radius=10,
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                ),
            ], spacing=10, expand=True, scroll=ft.ScrollMode.AUTO),
            width=1000,
            padding=12,
            clip_behavior=ft.ClipBehavior.NONE
        ),
        actions=[
            ft.TextButton("取消", on_click=close_dialog),
            ft.ElevatedButton("保存更改", on_click=save_changes, style=ft.ButtonStyle(color=ft.Colors.WHITE, bgcolor=ft.Colors.BLUE)),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    try:
        if hasattr(app, 'page') and app.page:
            app.page.dialog = dialog
            dialog.open = True
            app.page.update()
            def _kbd_handler(e):
                try:
                    key = (getattr(e, 'key', '') or '')
                    alt = bool(getattr(e, 'alt', False))
                    if alt and key in ('ArrowUp', 'Arrow Up', 'Up'):
                        if active_line_index is not None and active_line_index >= 0:
                            request_merge_up(active_line_index)
                except Exception:
                    pass
            try:
                app.page.on_keyboard_event = _kbd_handler
            except Exception:
                pass
    except Exception:
        pass

    if hasattr(app, 'page') and app.page:
        try:
            # 优先使用 overlay 追加，兼容更多老版本环境
            if dialog not in app.page.overlay:
                app.page.overlay.append(dialog)
            dialog.open = True
            app.page.update()
            def _kbd_handler(e):
                try:
                    key = (getattr(e, 'key', '') or '')
                    alt = bool(getattr(e, 'alt', False))
                    if alt and key in ('ArrowUp', 'Arrow Up', 'Up'):
                        if 'active_line_index' in locals() and active_line_index is not None and active_line_index >= 0:
                            request_merge_up(active_line_index)
                except Exception:
                    pass
            try:
                app.page.on_keyboard_event = _kbd_handler
            except Exception:
                pass
        except Exception:
            # 回退到 page.dialog
            try:
                app.page.dialog = dialog
                dialog.open = True
                app.page.update()
            except Exception:
                try:
                    # 最后兜底：重建 overlay 并再次尝试
                    app.page.overlay = []
                    app.page.overlay.append(dialog)
                    dialog.open = True
                    app.page.update()
                except Exception:
                    pass
