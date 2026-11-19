"""python3 -m unittest discover tests で実行する。実際の ~/.claude には触れない。"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tokenguard import transcripts as T  # noqa: E402


def line(**d):
    return json.dumps(d) + "\n"


def asst(mid, cr, out=10, model="claude-sonnet-5-5", tool=None):
    content = [{"type": "text", "text": "x"}]
    if tool:
        content.append({"type": "tool_use", "id": tool[0], "name": tool[1], "input": tool[2]})
    return line(type="assistant", timestamp="2026-11-19T10:00:00Z", message={
        "id": mid, "model": model, "content": content,
        "usage": {"input_tokens": 1, "cache_creation_input_tokens": 100, "cache_read_input_tokens": cr, "output_tokens": out}})


class TranscriptTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.p = Path(self.d.name) / "s1.jsonl"

    def tearDown(self):
        self.d.cleanup()

    def test_dedupe_by_message_id(self):
        # 同じ応答が content ブロックごとに 3 行書かれても 1 回と数える
        self.p.write_text(line(type="user", message={"content": "最初の依頼"})
                          + asst("m1", 1000, 5) + asst("m1", 1000, 5) + asst("m1", 1000, 50)
                          + asst("m2", 2000) + "壊れた行\n")
        s = T.parse(self.p)
        self.assertEqual(len(s.calls), 2)
        self.assertEqual(s.calls[0].output, 50)  # 最後の行(確定値)を採る
        self.assertEqual(s.title, "最初の依頼")
        self.assertEqual(s.peak, 2101)

    def test_tool_and_image_count(self):
        self.p.write_text(asst("m1", 10, tool=("t1", "Read", {"file_path": "/a/b.PNG"}))
                          + line(type="user", message={"content": [{"type": "tool_result", "tool_use_id": "t1",
                                 "content": [{"type": "image", "source": {"data": "AAAA"}}]}]}))
        s = T.parse(self.p)
        self.assertEqual(s.images, 1)
        self.assertIn("Read:image", s.tools)

    def test_continued_summary_is_not_title(self):
        self.p.write_text(line(type="user", message={"content": "This session is being continued from a previous"})
                          + line(type="user", message={"content": "本当の依頼"}) + asst("m1", 1))
        self.assertEqual(T.parse(self.p).title, "本当の依頼")

    def test_last_context(self):
        self.p.write_text(asst("m1", 1000) + asst("m2", 250_000) + line(type="user", message={"content": "次"}))
        self.assertEqual(T.last_context(self.p), 250_101)
        self.assertEqual(T.last_context(Path(self.d.name) / "none.jsonl"), 0)


class HookTest(unittest.TestCase):
    def run_hook(self, name, payload, env):
        r = subprocess.run([sys.executable, str(ROOT / "hooks" / name)], input=json.dumps(payload),
                           capture_output=True, text=True, env={**os.environ, **env}, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def test_ctx_guard_levels_once(self):
        with tempfile.TemporaryDirectory() as d:
            tp = Path(d) / "t.jsonl"
            env = {"TOKENGUARD_STATE": d}
            tp.write_text(asst("m1", 50_000))
            self.assertIsNone(self.run_hook("ctx_guard.py", {"transcript_path": str(tp), "session_id": "a"}, env))
            tp.write_text(asst("m1", 130_000))
            out = self.run_hook("ctx_guard.py", {"transcript_path": str(tp), "session_id": "a"}, env)
            self.assertIn("130k", out["hookSpecificOutput"]["additionalContext"])
            # 同じ段階では繰り返さない
            self.assertIsNone(self.run_hook("ctx_guard.py", {"transcript_path": str(tp), "session_id": "a"}, env))
            tp.write_text(asst("m1", 300_000))
            out = self.run_hook("ctx_guard.py", {"transcript_path": str(tp), "session_id": "a"}, env)
            self.assertIn("/handoff", out["hookSpecificOutput"]["additionalContext"])

    def test_img_shrink_skips_small_and_non_image(self):
        with tempfile.TemporaryDirectory() as d:
            env = {"TOKENGUARD_IMG_CACHE": d}
            self.assertIsNone(self.run_hook("img_shrink.py", {"tool_input": {"file_path": "/etc/hosts"}}, env))
            small = Path(d) / "s.png"
            subprocess.run(["sips", "-s", "format", "png", "-z", "100", "100",
                            "/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/GenericDocumentIcon.icns",
                            "--out", str(small)], capture_output=True)
            if small.exists():
                self.assertIsNone(self.run_hook("img_shrink.py", {"tool_input": {"file_path": str(small)}}, {"TOKENGUARD_IMG_CACHE": d + "/c"}))


class InstallTest(unittest.TestCase):
    def test_install_idempotent_and_uninstall(self):
        with tempfile.TemporaryDirectory() as home:
            (Path(home) / ".claude").mkdir()
            orig = {"model": "sonnet", "hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "other"}]}]}}
            st = Path(home) / ".claude" / "settings.json"
            st.write_text(json.dumps(orig))
            env = {**os.environ, "HOME": home}
            for _ in range(2):
                subprocess.run([sys.executable, str(ROOT / "install.py")], env=env, check=True, capture_output=True)
            s = json.loads(st.read_text())
            self.assertEqual(s["autoCompactWindow"], 200_000)
            self.assertEqual(len(s["hooks"]["UserPromptSubmit"]), 2)  # 既存 1 + 自分 1(2 回実行しても増えない)
            self.assertEqual(len(s["hooks"]["PreToolUse"]), 1)
            self.assertNotIn("tokenguard", s)
            self.assertTrue((Path(home) / ".claude/skills/handoff/SKILL.md").exists())
            subprocess.run([sys.executable, str(ROOT / "install.py"), "--uninstall"], env=env, check=True, capture_output=True)
            self.assertEqual(json.loads(st.read_text()), orig)


if __name__ == "__main__":
    unittest.main()
