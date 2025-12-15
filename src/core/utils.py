import math
import re

def format_timestamp(seconds):
    """将秒数格式化为SRT时间戳格式 (HH:MM:SS,mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

def remove_punctuation_from_text(text):
    """去除文本中的标点符号"""
    # 定义需要去除的标点符号
    punctuation_marks = [
        # 中文标点符号
        '。', '！', '？', '；', '：', '，', '、', '…', '—', '–', '·', '～',
        '"', '"', ''', ''', '「', '」', '『', '』', '（', '）', '【', '】',
        '《', '》', '〈', '〉', '〔', '〕', '〖', '〗', '〘', '〙', '〚', '〛',
        # 英文标点符号
        '.', '!', '?', ';', ':', ',', '-', '"', "'", '(', ')', '[', ']', '{', '}',
        '`', '~', '*', '&', '%', '$', '#', '@', '^', '+', '=', '|', '\\', '/', '<', '>',
        # 其他常见符号
        '°', '′', '″', '‰', '‱', '§', '¶', '†', '‡', '•', '‧', '‹', '›', '«', '»',
        # 省略号的各种形式
        '···', '......', '......'
    ]
    
    # 去除标点符号
    cleaned_text = text
    for punct in punctuation_marks:
        cleaned_text = cleaned_text.replace(punct, '')
    
    # 使用正则表达式去除其他可能的标点符号和特殊字符
    # 去除所有Unicode标点符号类别的字符
    cleaned_text = re.sub(r'[^\w\s\u4e00-\u9fff]', '', cleaned_text)
    
    # 去除多余的空格
    cleaned_text = ' '.join(cleaned_text.split())
    
    return cleaned_text

def calculate_character_length(text):
    """计算字符长度（中文算2个，其他算1个）"""
    length = 0
    for char in text:
        # 简单判断是否为中文字符（基本范围）
        if '\u4e00' <= char <= '\u9fff':
            length += 2
        else:
            length += 1
    return length

def cn_han_count(text):
    """计算汉字数量（估算）"""
    try:
        n = calculate_character_length(text or "")
        return int(math.ceil(n / 2.0))
    except Exception:
        return 0
