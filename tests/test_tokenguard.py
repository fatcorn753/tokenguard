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
            self.assertEqual(s["autoCompactWindow"], 300_000)
            self.assertEqual(len(s["hooks"]["UserPromptSubmit"]), 2)  # 既存 1 + 自分 1(2 回実行しても増えない)
            self.assertEqual(len(s["hooks"]["PreToolUse"]), 1)
            ours = [h["command"] for h in s["hooks"]["UserPromptSubmit"][1]["hooks"]]
            self.assertTrue(any(c.endswith("/hooks/ttl_guard.py") for c in ours))
            self.assertNotIn("tokenguard", s)
            self.assertTrue((Path(home) / ".claude/skills/handoff/SKILL.md").exists())
            subprocess.run([sys.executable, str(ROOT / "install.py"), "--uninstall"], env=env, check=True, capture_output=True)
            self.assertEqual(json.loads(st.read_text()), orig)


if __name__ == "__main__":
    unittest.main()


class SimulateTest(unittest.TestCase):
    def make(self, n=400, step=2_000, base=70_000):
        s = T.Session(sid="x", path=Path("x"))
        for i in range(n):
            ctx = base + i * step
            s.calls.append(T.Call("t", "m", 0, step, ctx - step, 100))
        return s

    def test_baseline_matches_real(self):
        from tokenguard.simulate import Scenario, simulate
        s = self.make()
        r = simulate([s], Scenario("real", None))
        self.assertAlmostEqual(r.weighted, s.weighted, delta=1)
        self.assertEqual(r.compactions, 0)

    def test_window_cuts_cost_and_caps_context(self):
        from tokenguard.simulate import BUFFER, Scenario, simulate
        s = self.make()
        r = simulate([s], Scenario("200k", 200_000))
        self.assertGreater(r.compactions, 0)
        self.assertLess(r.weighted, s.weighted)
        self.assertLessEqual(r.ctx_sum / r.calls, 200_000 - BUFFER)

    def test_real_compaction_is_respected(self):
        from tokenguard.simulate import Scenario, simulate
        s = self.make(n=10)
        s.calls.append(T.Call("t", "m", 0, 1000, 70_000, 10))  # 実ログで compact が起きた
        r = simulate([s], Scenario("real", None))
        self.assertAlmostEqual(r.weighted, s.weighted, delta=1)


class CompactCountTest(unittest.TestCase):
    def test_boundary_and_summary_count_once(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.jsonl"
            p.write_text(asst("m1", 10) + line(type="system", subtype="compact_boundary")
                         + line(type="user", isCompactSummary=True, message={"content": "要約"}))
            self.assertEqual(T.parse(p).compactions, 1)


def call(ts, write, read, w5=0):
    return T.Call(ts, "m", 0, write, read, 10, w5)


class CacheTest(unittest.TestCase):
    def test_classify(self):
        from tokenguard.cache import classify
        s = T.Session(sid="x", path=Path("x"))
        s.calls = [call("2026-11-20T10:00:00Z", 70_000, 0),          # 開始
                   call("2026-11-20T10:01:00Z", 2_000, 70_000),      # 増分
                   call("2026-11-20T12:00:00Z", 72_000, 0),          # 2 時間空いて書き直し
                   call("2026-11-20T12:01:00Z", 74_000, 0),          # TTL 内の書き直し
                   call("2026-11-20T12:02:00Z", 30_000, 0)]          # compact で縮んだ
        self.assertEqual(classify(s), ["start", "incremental", "ttl", "break", "compact"])

    def test_five_minute_ttl(self):
        from tokenguard.cache import classify
        s = T.Session(sid="x", path=Path("x"))
        s.calls = [call("2026-11-20T10:00:00Z", 50_000, 0, w5=50_000),
                   call("2026-11-20T10:10:00Z", 51_000, 0, w5=51_000)]
        self.assertEqual(classify(s), ["start", "ttl"])

    def test_last_usage_ttl(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.jsonl"
            p.write_text(line(type="assistant", timestamp="2026-11-20T10:00:00Z", message={"id": "m", "usage": {
                "input_tokens": 1, "cache_creation_input_tokens": 10, "cache_read_input_tokens": 0,
                "cache_creation": {"ephemeral_5m_input_tokens": 10, "ephemeral_1h_input_tokens": 0}}}))
            u = T.last_usage(p)
            self.assertEqual((u.context, u.ts, u.ttl), (11, "2026-11-20T10:00:00Z", 300))
            p.write_text(asst("m1", 1000))
            self.assertEqual(T.last_usage(p).ttl, 3600)


class SimulateTTLTest(unittest.TestCase):
    def make(self):
        # 300k まで育った会話に、3 時間空けて戻り、さらに 50 回続ける
        s = T.Session(sid="x", path=Path("x"))
        ctx = 70_000
        s.calls.append(call("2026-11-20T10:00:00Z", ctx, 0))
        for i in range(115):
            s.calls.append(call(f"2026-11-20T10:{i // 60 + 1:02d}:{i % 60:02d}Z", 2_000, ctx))
            ctx += 2_000
        s.calls.append(call("2026-11-20T14:00:00Z", ctx + 1_000, 0))
        ctx += 1_000
        for i in range(50):
            s.calls.append(call(f"2026-11-20T14:01:{i:02d}Z", 1_000, ctx))
            ctx += 1_000
        return s

    def test_clear_on_ttl_saves(self):
        from tokenguard.simulate import Scenario, simulate
        s = self.make()
        base = simulate([s], Scenario("real", None))
        self.assertAlmostEqual(base.weighted, s.weighted, delta=1)
        self.assertEqual(base.ttl_events, 1)
        r = simulate([s], Scenario("clear", None, clear_on_ttl=1.0))
        self.assertEqual(r.clears, 1)
        self.assertLess(r.weighted, base.weighted * 0.8)  # 書き直し 60 万と、その後の読み直しが減る
        # 下限より小さい文脈なら止めない
        r = simulate([s], Scenario("clear", None, clear_on_ttl=1.0, ttl_min=1_000_000))
        self.assertEqual(r.clears, 0)

    def test_share_is_spread_across_sessions(self):
        from tokenguard.simulate import Scenario, simulate
        r = simulate([self.make() for _ in range(4)], Scenario("half", None, clear_on_ttl=0.5))
        self.assertEqual((r.ttl_events, r.clears), (4, 2))

    def test_rewrite_is_capped_by_simulated_context(self):
        # 窓で文脈が小さくなっていれば、cache 切れの書き直しも小さくなる
        from tokenguard.simulate import Scenario, simulate
        s = self.make()
        r = simulate([s], Scenario("200k", 200_000))
        self.assertLess(r.weighted, s.weighted)


class TTLGuardTest(unittest.TestCase):
    def run_hook(self, payload, env):
        r = subprocess.run([sys.executable, str(ROOT / "hooks" / "ttl_guard.py")], input=json.dumps(payload),
                           capture_output=True, text=True, env={**os.environ, **env}, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def transcript(self, d, ago, ctx=150_000, five_min=False):
        import datetime as dt
        ts = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=ago)).isoformat().replace("+00:00", "Z")
        cc = {"ephemeral_5m_input_tokens": 100, "ephemeral_1h_input_tokens": 0} if five_min else {}
        p = Path(d) / f"t{ago}{ctx}{five_min}.jsonl"
        p.write_text(line(type="assistant", timestamp=ts, message={"id": "m", "usage": {
            "input_tokens": 0, "cache_creation_input_tokens": 100, "cache_read_input_tokens": ctx - 100,
            "cache_creation": cc}}))
        return str(p)

    def test_blocks_once_after_expiry(self):
        with tempfile.TemporaryDirectory() as d:
            env = {"TOKENGUARD_STATE": d}
            tp = self.transcript(d, 2 * 3600)
            out = self.run_hook({"transcript_path": tp, "session_id": "a", "prompt": "次の件"}, env)
            self.assertEqual(out["decision"], "block")
            self.assertIn("150k", out["reason"])
            self.assertIn("/clear", out["reason"])
            # 同じ cache 切れでは 2 回目を通す
            self.assertIsNone(self.run_hook({"transcript_path": tp, "session_id": "a", "prompt": "次の件"}, env))

    def test_passes(self):
        with tempfile.TemporaryDirectory() as d:
            env = {"TOKENGUARD_STATE": d}
            old = self.transcript(d, 2 * 3600)
            cases = [
                ({"transcript_path": self.transcript(d, 600), "prompt": "x"}, env),            # TTL 内
                ({"transcript_path": self.transcript(d, 7200, 50_000), "prompt": "x"}, env),   # 文脈が小さい
                ({"transcript_path": old, "prompt": "<task-notification>x"}, env),            # 自動の差し込み
                ({"transcript_path": old, "prompt": "/compact"}, env),                        # コマンド
                ({"transcript_path": old, "prompt": "x"}, {**env, "TOKENGUARD_TTL_GUARD": "off"}),
            ]
            for i, (payload, e) in enumerate(cases):
                self.assertIsNone(self.run_hook({**payload, "session_id": f"s{i}"}, e), payload)

    def test_pasted_and_five_minute_ttl(self):
        with tempfile.TemporaryDirectory() as d:
            env = {"TOKENGUARD_STATE": d}
            out = self.run_hook({"transcript_path": self.transcript(d, 7200), "session_id": "p",
                                 "prompt": '<pasted_content id="1">\nlog\n</pasted_content id="1">'}, env)
            self.assertEqual(out["decision"], "block")
            out = self.run_hook({"transcript_path": self.transcript(d, 600, five_min=True), "session_id": "f",
                                 "prompt": "x"}, env)
            self.assertEqual(out["decision"], "block")
            self.assertIn("10 分", out["reason"])


sys.path.insert(0, str(ROOT / "bench"))
import defects  # noqa: E402


class DefectsTest(unittest.TestCase):
    """bench/defects.py: base からの増分だけを欠陥として数える。"""

    def git(self, *a):
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=self.wt,
                       check=True, capture_output=True)

    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.wt = Path(self.d.name)
        self.git("init", "-q")
        # base の時点ですでにある未使用 import は数えない
        (self.wt / "a.py").write_text("import os\n\n\ndef used():\n    return 1\n")
        (self.wt / "b.py").write_text("from a import used\n\nprint(used())\n")
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.wt, capture_output=True,
                                   text=True).stdout.strip()

    def test_counts_only_new_defects(self):
        (self.wt / "a.py").write_text(
            "import os\nimport json\nfrom typing import Any  # noqa: F401\n\n\n"
            "def used():\n    #\n    return 1\n\n\ndef orphan():\n    return 2\n\n\n"
            "def helper():\n    return 3\n\n\nX: 'Any' = helper()\n")
        (self.wt / "new.py").write_text("import sys\n#  \nprint(sys.argv)\n")
        r = defects.count(self.wt, self.base, ["a.py"])
        self.assertEqual(r["empty_comments"], 2)
        self.assertEqual(r["unused_imports"], 1)  # json だけ(os は base から、Any は noqa)
        self.assertEqual(r["unused_defs"], 1)  # orphan だけ
        self.assertEqual(r["extra_files"], ["new.py"])
        self.assertEqual(r["total"], 5)
        self.assertEqual(r["files_changed"], 2)

    def test_excluded_files_are_not_counted(self):
        (self.wt / "test_x.py").write_text("import json\n#\n")
        r = defects.count(self.wt, self.base, [], exclude=["test_x.py"])
        self.assertEqual(r["total"], 0)
        diff = "diff --git a/a.py b/a.py\n+x\ndiff --git a/test_x.py b/test_x.py\n+y\n"
        self.assertEqual(defects.strip_files(diff, ["test_x.py"]), "diff --git a/a.py b/a.py\n+x\n")

    def test_clean_change_has_no_defects(self):
        (self.wt / "a.py").write_text("import os\n\n\ndef used():\n    # 理由のあるコメント\n    return 2\n")
        r = defects.count(self.wt, self.base, ["a.py"])
        self.assertEqual(r["total"], 0)
        self.assertEqual(r["lines_changed"], 3)
