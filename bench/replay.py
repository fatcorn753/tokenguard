#!/usr/bin/env python3
"""過去の作業の再現実験: ある commit の直前から、完成形のテストを渡して同じ機能を実装させる。

窓の条件ごとに、テストの通過数と消費量を比べる。テストファイルは採点の前に元へ戻すので、
エージェントがテストを書き換えても点にはならない。

例:
  python3 bench/replay.py --repo ~/artistme/python/delegate --base 50c804f --target 4600115 \
      --tests tests/test_delegate.py --window 1000000 300000 200000
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tokenguard import transcripts as T  # noqa: E402

WORK = Path(os.environ.get("TOKENGUARD_BENCH_DIR", Path.home() / ".cache/tokenguard/bench")) / "replay"
TOOLS = ["Read", "Edit", "Write", "Glob", "Grep", "Bash(python3 -m unittest*)", "Bash(python3 -m py_compile*)",
         "Bash(git diff*)", "Bash(git status*)", "Bash(ls*)"]


def sh(*a, cwd=None, check=True):
    return subprocess.run(a, cwd=cwd, capture_output=True, text=True, check=check)


def run_tests(wt: Path, tests: str) -> tuple[int, int]:
    mod = tests.removesuffix(".py").replace("/", ".")
    r = subprocess.run([sys.executable, "-m", "unittest", mod], cwd=wt, capture_output=True, text=True, timeout=600)
    out = r.stderr
    ran = int(m.group(1)) if (m := re.search(r"Ran (\d+) test", out)) else 0
    bad = sum(int(x) for x in re.findall(r"(?:failures|errors)=(\d+)", out))
    return ran - bad, ran


def trial(a, window: int) -> dict:
    wt = WORK / f"{Path(a.repo).name}-{window // 1000}k-{int(time.time())}"
    wt.parent.mkdir(parents=True, exist_ok=True)
    sh("git", "worktree", "add", "--detach", str(wt), a.base, cwd=a.repo)
    res = {"window": window, "model": a.model, "base": a.base, "target": a.target}
    try:
        sh("git", "checkout", a.target, "--", a.tests, cwd=wt)
        msg = sh("git", "show", "-s", "--format=%B", a.target, cwd=a.repo).stdout
        msg = "\n".join(line for line in msg.splitlines() if not line.startswith("Co-Authored-By"))
        prompt = (f"このリポジトリに次の変更を実装して。\n\n{msg}\n\n"
                  f"{a.tests} は完成形のテスト。テストは変更せず、すべて通るように実装すること。"
                  f"最後に python3 -m unittest で通ることを確かめ、変更点を 3 行で報告して。")
        t0 = time.time()
        r = subprocess.run(["claude", "-p", prompt, "--model", a.model, "--output-format", "json",
                            "--allowedTools", *TOOLS, "--settings", json.dumps({"autoCompactWindow": window})],
                           cwd=wt, capture_output=True, text=True, timeout=3600,
                           env={**os.environ, "TOKENGUARD_CTX_STEPS": "999999999"})
        res["seconds"] = round(time.time() - t0)
        out = json.loads(r.stdout) if r.stdout.strip() else {}
        res["cost_usd"] = out.get("total_cost_usd", 0)
        sid = out.get("session_id")
        sh("git", "checkout", a.target, "--", a.tests, cwd=wt)  # テストの書き換えを無効にする
        res["passed"], res["ran"] = run_tests(wt, a.tests)
        if sid and (hits := list(T.PROJECTS.rglob(f"{sid}.jsonl"))):
            s = T.parse(hits[0])
            res.update(weighted=round(s.weighted), calls=len(s.calls), peak=s.peak, compactions=s.compactions)
    except Exception as e:  # 1 試行の失敗で全体を止めない
        res["error"] = str(e)[:300]
    finally:
        if not a.keep:
            sh("git", "worktree", "remove", "--force", str(wt), cwd=a.repo, check=False)
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--base", required=True, help="作業を始める commit(対象の親)")
    ap.add_argument("--target", required=True, help="再現する commit(テストと依頼文をここから取る)")
    ap.add_argument("--tests", required=True)
    ap.add_argument("--window", type=int, nargs="+", default=[1_000_000, 300_000, 200_000])
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--keep", action="store_true", help="作業ツリーを消さずに残す")
    a = ap.parse_args()
    a.repo = str(Path(a.repo).expanduser())
    WORK.mkdir(parents=True, exist_ok=True)
    log = WORK.parent / "replay_results.jsonl"
    for _ in range(a.reps):
        for w in a.window:
            res = trial(a, w)
            with open(log, "a") as f:
                f.write(json.dumps(res, ensure_ascii=False) + "\n")
            print(json.dumps(res, ensure_ascii=False), flush=True)
    print(f"結果は {log} に追記した")


if __name__ == "__main__":
    main()
