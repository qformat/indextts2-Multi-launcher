import re
from concurrent.futures import ThreadPoolExecutor, as_completed


def _is_probable_anchor_name(name):
    n = (name or "").strip()
    if not n:
        return False
    if len(n) < 2 or len(n) > 8:
        return False
    bad_tokens = (
        "一脸", "好言", "兴奋", "冷冷", "轻声", "低声", "怒", "笑", "问", "说", "道",
        "呵斥", "开口", "沉声", "淡淡", "皱眉", "挑眉", "点头", "叹气", "喃喃", "骂",
        "厉声", "柔声", "声音", "看着", "看向", "立刻", "慌忙", "迷迷糊糊", "没来得及",
        "发呆", "衬衫", "低头", "转头", "抬头", "抿唇", "眯了眯", "朝着"
    )
    if any(tok in n for tok in bad_tokens):
        return False
    if not re.match(r"^[\u4e00-\u9fffA-Za-z0-9]{2,8}$", n):
        return False
    return True


def split_text_with_offsets(text, max_chars=4000):
    if not text:
        return []
    n = len(text)
    chunks = []
    pos = 0
    idx = 0
    while pos < n:
        end = min(pos + max_chars, n)
        cut = end
        if end < n:
            window = text[pos:end]
            search_start = max(0, len(window) - 1200)
            candidates = []
            for sep in ("\n\n", "\n", "。", "！", "？", "；", "…", "”", "\""):
                k = window.rfind(sep, search_start)
                if k >= 0:
                    candidates.append(k + len(sep))
            if candidates:
                cut = pos + max(candidates)
            else:
                forward_limit = min(n, end + min(1600, max_chars))
                forward = text[end:forward_limit]
                next_points = []
                for sep in ("\n\n", "\n", "。", "！", "？", "；", "…", "”", "\""):
                    k = forward.find(sep)
                    if k >= 0:
                        next_points.append(k + len(sep))
                if next_points:
                    cut = end + min(next_points)
            if cut <= pos:
                cut = end
            chunk_try = text[pos:cut]
            if chunk_try.count("“") > chunk_try.count("”"):
                close_q = text.find("”", cut, min(n, cut + 220))
                if close_q != -1:
                    cut = close_q + 1
        if cut <= pos:
            cut = min(pos + max_chars, n)
        chunks.append({
            "index": idx,
            "start": pos,
            "end": cut,
            "text": text[pos:cut],
        })
        idx += 1
        pos = cut
    return chunks


def extract_role_anchors(text, max_roles=128):
    anchors = {"旁白": 0}
    if not text:
        return anchors
    pattern = re.compile(r"([^\s：:\n“”\"'（）()]{1,16})[：:]")
    for m in pattern.finditer(text):
        name = (m.group(1) or "").strip(" \t\r\n\"'“”‘’（）()[]【】")
        if not name:
            continue
        if len(name) > 12:
            continue
        if not _is_probable_anchor_name(name):
            continue
        if name not in anchors:
            anchors[name] = m.start()
        if len(anchors) >= max_roles:
            break
    cue_patterns = [
        re.compile(r"([\u4e00-\u9fffA-Za-z]{2,6}?)(?=(?:轻声|低声|冷冷|淡淡|忽然|突然)?(?:开口|说道|问道|喊道|尖叫道|回应道|答道|怒道|笑道|轻声说|低声说|冷冷说))(?:轻声|低声|冷冷|淡淡|忽然|突然)?(?:开口|说道|问道|喊道|尖叫道|回应道|答道|怒道|笑道|轻声说|低声说|冷冷说)"),
    ]
    for p in cue_patterns:
        for m in p.finditer(text):
            name = (m.group(1) or "").strip()
            if not name:
                continue
            if len(name) > 8:
                continue
            if name in ("我们", "你们", "他们", "她们", "旁白"):
                continue
            if not _is_probable_anchor_name(name):
                continue
            if name not in anchors:
                anchors[name] = m.start()
            if len(anchors) >= max_roles:
                return anchors
    return anchors


def build_anchor_summary(anchors, limit=24):
    items = sorted(anchors.items(), key=lambda x: x[1])[:limit]
    return [{"name": k, "first_pos": v} for k, v in items]


def build_chunk_tasks(chunks, anchors, overlap_chars=200):
    tasks = []
    anchor_summary = build_anchor_summary(anchors)
    for i, ch in enumerate(chunks):
        prev_tail = ""
        if i > 0:
            prev_tail = chunks[i - 1]["text"][-overlap_chars:]
        tasks.append({
            "chunk_index": i,
            "start": ch["start"],
            "end": ch["end"],
            "chunk_text": ch["text"],
            "prev_tail": prev_tail,
            "anchors": anchor_summary,
        })
    return tasks


def run_tasks_concurrent(tasks, worker, max_workers=3):
    if not tasks:
        return []
    results = []
    pool_size = max(1, min(int(max_workers), len(tasks)))
    with ThreadPoolExecutor(max_workers=pool_size) as ex:
        futs = {ex.submit(worker, t): t for t in tasks}
        for fut in as_completed(futs):
            t = futs[fut]
            try:
                r = fut.result()
                if isinstance(r, dict):
                    r.setdefault("chunk_index", t.get("chunk_index"))
                    r.setdefault("start", t.get("start"))
                    r.setdefault("end", t.get("end"))
                    results.append(r)
                else:
                    results.append({
                        "chunk_index": t.get("chunk_index"),
                        "start": t.get("start"),
                        "end": t.get("end"),
                        "error": "invalid_result",
                    })
            except Exception as e:
                results.append({
                    "chunk_index": t.get("chunk_index"),
                    "start": t.get("start"),
                    "end": t.get("end"),
                    "error": str(e),
                })
    results.sort(key=lambda x: x.get("chunk_index", 0))
    return results


def enforce_role_consistency(assignments, anchors):
    if not isinstance(assignments, list):
        return []
    fixed = []
    speaker_role_map = {}
    speaker_pat = re.compile(r"^\s*([^\s：:\n“”\"'（）()]{1,16})[：:]")
    for a in assignments:
        if not isinstance(a, dict):
            continue
        b = dict(a)
        text = (b.get("text") or "").strip()
        role = b.get("role") or "旁白"
        m = speaker_pat.match(text)
        if m:
            spk = (m.group(1) or "").strip()
            if spk in anchors:
                speaker_role_map.setdefault(spk, spk)
                role = speaker_role_map[spk]
        if role in speaker_role_map:
            role = speaker_role_map[role]
        b["role"] = role
        fixed.append(b)
    return fixed


def build_role_continuity_map(assignments):
    continuity = {}
    for a in assignments:
        if not isinstance(a, dict):
            continue
        role = a.get("role", "旁白")
        line = int(a.get("line", 0))
        continuity.setdefault(role, []).append(line)
    merged = {}
    for role, lines in continuity.items():
        if not lines:
            continue
        lines = sorted(set(lines))
        ranges = []
        s = lines[0]
        e = lines[0]
        for x in lines[1:]:
            if x == e + 1:
                e = x
            else:
                ranges.append((s, e))
                s = x
                e = x
        ranges.append((s, e))
        merged[role] = ranges
    return merged
