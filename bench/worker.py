#!/usr/bin/env python3
"""replay の「親+作業役」条件で、親 Claude が呼ぶ作業役の窓口。

使い方(作業ツリーの中で): python3 bench/worker.py <仕様書のパス>

- 前回の作業役の変更が残っていれば、先に作業ツリーへ wip commit する。delegate implement は
  未コミットの変更があると動かないため(差し戻しのたびに必要)。採点は base との差分で行うので影響しない。
- delegate implement の JSON と、呼び出し後の base からの差分を BENCH_LOG_DIR に保存する。
  レビュー前の欠陥(1 回目の作業役の出力)を数えるのに使う。
- 親には要点だけを返す(作業役の報告・変更ファイル・テスト結果)。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import defects  # noqa: E402


def git(*a: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "user.email=bench@local", "-c", "user.name=bench", *a],
                          capture_output=True, text=True)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: worker.py <spec.md>", file=sys.stderr)
        return 64
    spec = Path(sys.argv[1]).expanduser().resolve()
    log_dir = Path(os.environ["BENCH_LOG_DIR"])
    base, test_cmd = os.environ["BENCH_BASE"], os.environ["BENCH_TEST_CMD"]
    log_dir.mkdir(parents=True, exist_ok=True)
    n = len(list(log_dir.glob("call*.json"))) + 1
    if git("status", "--porcelain").stdout.strip():
        git("add", "-A")
        git("commit", "-qm", f"wip: worker call {n - 1}")
    r = subprocess.run(["delegate", "implement", "-f", str(spec), "-C", ".", "--test", test_cmd, "--json",
                        "--rounds", os.environ.get("BENCH_ROUNDS", "3")], capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
    except ValueError:
        d = {"passed": False, "error": (r.stderr or r.stdout)[-1500:], "rounds": []}
    d["exit"] = r.returncode
    tests = json.loads(os.environ.get("BENCH_TESTS", "[]"))
    d["defects"] = defects.count(Path.cwd(), base, json.loads(os.environ.get("BENCH_TARGET_FILES", "[]")), tests)
    (log_dir / f"call{n}.json").write_text(json.dumps(d, ensure_ascii=False, indent=2))
    (log_dir / f"call{n}.diff").write_text(git("diff", base).stdout)

    print(f"作業役の呼び出し {n} 回目: テスト {'PASS' if d.get('passed') else 'FAIL'}"
          f"(ラウンド {len(d.get('rounds') or [])})")
    if d.get("worker_text"):
        print("--- 作業役の報告 ---\n" + d["worker_text"][-3000:])
    print("--- 今回の変更 ---\n" + str(d.get("edit_report", "")))
    if not d.get("passed"):
        print("--- テスト出力(末尾)---\n" + str(d.get("test_tail") or d.get("error", ""))[-2000:])
    print("差分の全体は git diff " + base + " で読める。")
    return 0 if d.get("passed") else 1


if __name__ == "__main__":
    sys.exit(main())
