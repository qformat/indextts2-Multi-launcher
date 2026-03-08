import unittest
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
    build_role_continuity_map,
)


class TestAIChunkPipeline(unittest.TestCase):
    def test_split_text_with_offsets_lossless(self):
        text = ("旁白：开始。\n\n" + "小明：你好。小红：你好！" * 500) + "\n\n旁白：结束。"
        chunks = split_text_with_offsets(text, max_chars=4000)
        self.assertTrue(len(chunks) > 1)
        rebuilt = "".join([c["text"] for c in chunks])
        self.assertEqual(rebuilt, text)
        for i, c in enumerate(chunks):
            self.assertEqual(text[c["start"]:c["end"]], c["text"])
            if i > 0:
                self.assertEqual(chunks[i - 1]["end"], c["start"])

    def test_split_text_quote_boundary(self):
        text = "旁白：他说“你好，世界。这里很长很长很长很长很长很长。”然后离开。"
        chunks = split_text_with_offsets(text, max_chars=20)
        self.assertTrue(len(chunks) >= 2)
        self.assertEqual("".join(c["text"] for c in chunks), text)

    def test_extract_role_anchors(self):
        text = "小明：你好。\n旁白：描述。\n小红：回答。"
        anchors = extract_role_anchors(text)
        self.assertIn("小明", anchors)
        self.assertIn("小红", anchors)
        self.assertIn("旁白", anchors)

    def test_extract_role_anchors_from_speech_cue(self):
        text = "万念山低声说道这件事可以谈。战彦寒问道你想怎么做。"
        anchors = extract_role_anchors(text)
        self.assertIn("万念山", anchors)
        self.assertIn("战彦寒", anchors)

    def test_run_tasks_concurrent_with_exception(self):
        tasks = [{"chunk_index": 0}, {"chunk_index": 1}, {"chunk_index": 2}]

        def worker(task):
            if task["chunk_index"] == 1:
                raise RuntimeError("boom")
            return {"ok": task["chunk_index"]}

        results = run_tasks_concurrent(tasks, worker, max_workers=3)
        self.assertEqual(len(results), 3)
        err = [r for r in results if r.get("chunk_index") == 1][0]
        self.assertIn("error", err)

    def test_enforce_role_consistency(self):
        anchors = {"旁白": 0, "小明": 10}
        assignments = [
            {"line": 0, "role": "旁白", "text": "小明：你好"},
            {"line": 1, "role": "旁白", "text": "旁白：天气很好"},
        ]
        fixed = enforce_role_consistency(assignments, anchors)
        self.assertEqual(fixed[0]["role"], "小明")

    def test_role_continuity_map(self):
        assignments = [
            {"line": 0, "role": "旁白"},
            {"line": 1, "role": "旁白"},
            {"line": 2, "role": "小明"},
            {"line": 4, "role": "小明"},
        ]
        m = build_role_continuity_map(assignments)
        self.assertEqual(m["旁白"], [(0, 1)])
        self.assertEqual(m["小明"], [(2, 2), (4, 4)])

    def test_build_chunk_tasks_overlap(self):
        text = "A" * 300 + "B" * 300
        chunks = split_text_with_offsets(text, max_chars=300)
        anchors = extract_role_anchors("旁白：A")
        tasks = build_chunk_tasks(chunks, anchors, overlap_chars=50)
        self.assertEqual(len(tasks), len(chunks))
        if len(tasks) > 1:
            self.assertEqual(len(tasks[1]["prev_tail"]), 50)

    def test_split_text_prefers_forward_separator(self):
        text = ("甲" * 2100) + "。" + ("乙" * 2100)
        chunks = split_text_with_offsets(text, max_chars=2000)
        self.assertTrue(len(chunks) >= 2)
        self.assertEqual("".join(c["text"] for c in chunks), text)
        self.assertTrue(chunks[0]["text"].endswith("。"))


if __name__ == "__main__":
    unittest.main()
