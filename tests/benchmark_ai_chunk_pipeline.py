import json
import time
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.ai_chunk_pipeline import (
    split_text_with_offsets,
    extract_role_anchors,
    build_chunk_tasks,
    run_tasks_concurrent,
    enforce_role_consistency,
)


def _build_long_text(char_count=28000):
    unit = "旁白：这是一段测试文本。小明：你好。小红：收到。"
    text = []
    total = 0
    while total < char_count:
        text.append(unit)
        total += len(unit)
    return "".join(text)[:char_count]


def main():
    text = _build_long_text(28000)
    t0 = time.perf_counter()
    chunks = split_text_with_offsets(text, max_chars=4000)
    t1 = time.perf_counter()
    anchors = extract_role_anchors(text)
    t2 = time.perf_counter()
    tasks = build_chunk_tasks(chunks, anchors, overlap_chars=200)
    t3 = time.perf_counter()

    def worker(task):
        payload = {
            "roles": [{"name": "旁白"}, {"name": "小明"}, {"name": "小红"}],
            "segments": [{"text": task["chunk_text"][:120], "role": "旁白", "type": "narration", "emotion": "中性", "emotion_vector": [0.0] * 8, "speaking_speed": 1.0}],
            "assignments": [{"line": 0, "role": "旁白", "text": task["chunk_text"][:120], "emotion": "中性", "emotion_vector": [0.0] * 8, "speaking_speed": 1.0}],
        }
        return {"parsed": payload}

    results = run_tasks_concurrent(tasks, worker, max_workers=3)
    t4 = time.perf_counter()
    merged = []
    line = 0
    for r in results:
        parsed = r.get("parsed", {})
        for seg in parsed.get("segments", []):
            merged.append({"line": line, "role": seg.get("role", "旁白"), "text": seg.get("text", "")})
            line += 1
    fixed = enforce_role_consistency(merged, anchors)
    t5 = time.perf_counter()

    report = {
        "input_chars": len(text),
        "chunk_count": len(chunks),
        "anchor_count": len(anchors),
        "split_seconds": round(t1 - t0, 4),
        "anchor_seconds": round(t2 - t1, 4),
        "task_build_seconds": round(t3 - t2, 4),
        "concurrent_seconds": round(t4 - t3, 4),
        "merge_seconds": round(t5 - t4, 4),
        "total_seconds": round(t5 - t0, 4),
        "consistency_items": len(fixed),
        "target_total_seconds": 6.0,
        "target_role_error_rate": 0.001,
    }
    report["total_seconds_pass"] = report["total_seconds"] <= report["target_total_seconds"]
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
