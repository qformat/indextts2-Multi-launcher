import os
import shutil
import subprocess
import math
import uuid
import urllib.request
import urllib.parse
from pydub import AudioSegment

def save_audio_from_result(result, dest_dir, dest_filename=None, base_url=None, logger=None):
    """从接口返回的 result 中解析音频并保存到指定目录。
    支持返回本地文件路径、URL、列表/字典嵌套等常见形式。
    返回保存后的完整路径，若无法解析则返回 None。
    """
    try:
        os.makedirs(dest_dir, exist_ok=True)

        def iter_candidates(obj):
            # 递归提取可能的路径/URL字符串
            if obj is None:
                return
            if isinstance(obj, str):
                yield obj
            elif isinstance(obj, (list, tuple, set)):
                for item in obj:
                    yield from iter_candidates(item)
            elif isinstance(obj, dict):
                for v in obj.values():
                    yield from iter_candidates(v)
            else:
                # 处理常见的文件对象属性
                p = getattr(obj, 'path', None)
                if isinstance(p, str):
                    yield p

        def make_alt_dest_path(dest_path: str):
            base, ext = os.path.splitext(dest_path)
            return f"{base}_{uuid.uuid4().hex}{ext or '.wav'}"

        # 构造目标文件名
        def make_dest_path(src_path=None):
            base = dest_filename or (os.path.basename(src_path) if src_path else f"audio_{uuid.uuid4().hex}.wav")
            return os.path.join(dest_dir, base)

        def log_msg(msg):
            if logger:
                logger.warning(msg)
            else:
                print(msg)

        for cand in iter_candidates(result):
            if not isinstance(cand, str):
                continue
            # 本地文件路径
            if os.path.isfile(cand):
                dest_path = make_dest_path(cand)
                try:
                    shutil.copy2(cand, dest_path)
                    return dest_path
                except Exception as copy_err:
                    log_msg(f"保存音频失败：复制 {cand} -> {dest_path} 出错: {copy_err}")
                    try:
                        alt_path = make_alt_dest_path(dest_path)
                        shutil.copy2(cand, alt_path)
                        return alt_path
                    except Exception as copy_err2:
                        log_msg(f"保存音频失败：复制 {cand} -> {alt_path} 出错: {copy_err2}")
                    continue
            # URL 下载
            if cand.startswith('http://') or cand.startswith('https://'):
                dest_path = make_dest_path()
                try:
                    urllib.request.urlretrieve(cand, dest_path)
                    if os.path.isfile(dest_path):
                        return dest_path
                except Exception as dl_err:
                    log_msg(f"下载音频失败：{cand} -> {dest_path}: {dl_err}")
                    try:
                        alt_path = make_alt_dest_path(dest_path)
                        urllib.request.urlretrieve(cand, alt_path)
                        if os.path.isfile(alt_path):
                            return alt_path
                    except Exception as dl_err2:
                        log_msg(f"下载音频失败：{cand} -> {alt_path}: {dl_err2}")
                    continue
            if base_url and cand.startswith('/'):
                url = urllib.parse.urljoin(base_url.rstrip('/')+'/', cand.lstrip('/'))
                dest_path = make_dest_path()
                try:
                    urllib.request.urlretrieve(url, dest_path)
                    if os.path.isfile(dest_path):
                        return dest_path
                except Exception as dl_err2:
                    log_msg(f"下载音频失败：{url} -> {dest_path}: {dl_err2}")
                    try:
                        alt_path = make_alt_dest_path(dest_path)
                        urllib.request.urlretrieve(url, alt_path)
                        if os.path.isfile(alt_path):
                            return alt_path
                    except Exception as dl_err3:
                        log_msg(f"下载音频失败：{url} -> {alt_path}: {dl_err3}")
                    continue

        return None
    except Exception as e:
        if logger:
            logger.error(f"解析并保存接口返回音频失败: {e}")
        return None


def get_audio_duration(audio_path, logger=None):
    """获取音频文件时长（秒）"""
    try:
        audio = AudioSegment.from_wav(audio_path)
        return len(audio) / 1000.0  # 转换为秒
    except Exception as e:
        if logger:
            logger.error(f"获取音频时长失败 {audio_path}: {e}")
        return 0.0

def apply_speaking_speed(audio_path, speed, logger=None):
    """应用语速调整"""
    return apply_speaking_speed_value(audio_path, speed, logger)

def apply_speaking_speed_value(audio_path, s, logger=None):
    try:
        s = float(s)
        if abs(s - 1.0) < 1e-6:
            return False
        
        ff = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
        if ff:
            factors = []
            target = s
            while target > 2.0:
                factors.append(2.0)
                target /= 2.0
            while target < 0.5:
                factors.append(0.5)
                target /= 0.5
            if target > 1e-6 and abs(target - 1.0) > 1e-6:
                factors.append(target)
            filter_str = ",".join([f"atempo={f:.6f}" for f in factors]) if factors else ""
            if filter_str:
                tmp = audio_path + ".tmp.wav"
                cmd = [ff, "-y", "-i", audio_path, "-filter:a", filter_str, "-vn", tmp]
                cf = 0
                si = None
                if os.name == 'nt':
                    try:
                        cf = subprocess.CREATE_NO_WINDOW
                        si = subprocess.STARTUPINFO()
                        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        si.wShowWindow = 0
                    except Exception:
                        cf = 0
                        si = None
                r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=cf, startupinfo=si)
                if r.returncode == 0 and os.path.exists(tmp):
                    os.replace(tmp, audio_path)
                    return True
        
        # Fallback to pydub if ffmpeg fails or not found (though pydub might degrade quality for speed change)
        audio = AudioSegment.from_wav(audio_path)
        altered = audio._spawn(audio.raw_data, overrides={"frame_rate": int(audio.frame_rate * s)})
        out = altered.set_frame_rate(audio.frame_rate)
        out.export(audio_path, format="wav")
        return True
    except Exception as e:
        if logger:
            logger.warning(f"调整语速失败: {e}")
        return False

def apply_volume(audio_path, volume_percent, logger=None):
    try:
        vp = int(volume_percent)
        if vp == 100:
            return False
        
        ff = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
        if ff:
            factor = max(0.01, vp / 100.0)
            tmp = audio_path + ".vol.wav"
            cmd = [ff, "-y", "-i", audio_path, "-filter:a", f"volume={factor:.6f}", "-vn", tmp]
            cf = 0
            si = None
            if os.name == 'nt':
                try:
                    cf = subprocess.CREATE_NO_WINDOW
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    si.wShowWindow = 0
                except Exception:
                    cf = 0
                    si = None
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=cf, startupinfo=si)
            if r.returncode == 0 and os.path.exists(tmp):
                os.replace(tmp, audio_path)
                return True
        
        audio = AudioSegment.from_wav(audio_path)
        gain_db = 20.0 * math.log10(max(0.01, vp / 100.0))
        out = audio.apply_gain(gain_db)
        out.export(audio_path, format="wav")
        return True
    except Exception as e:
        if logger:
            logger.warning(f"调整音量失败: {e}")
        return False
