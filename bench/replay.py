#!/usr/bin/env python3
"""過去の作業の再現実験: ある commit の直前から、完成形のテストを渡して同じ機能を実装させる。

窓の条件ごとに、テストの通過数と消費量を比べる。テストファイルは採点の前に元へ戻すので、
エージェントがテストを書き換えても点にはならない。

条件(--cond):
- solo: Claude が 1 人で実装する(従来の条件)
- parent: 親 Claude は仕様を書いて bench/worker.py(delegate implement)に実装を任せ、
  git diff をレビューして必要なら差し戻す。親はコードを直接編集できない(Edit/Write は仕様書の置き場だけ)

品質はテストの通過数と、bench/defects.py の欠陥数(空コメント・未使用 import/定義・仕様外のファイル)で測る。
parent では 1 回目の作業役の出力(親のレビュー前)と最終結果(レビュー後)の両方を数える。

例:
  python3 bench/replay.py --repo ~/artistme/python/delegate --base 50c804f --target 4600115 \
      --tests tests/test_delegate.py --window 1000000 300000 200000
  python3 bench/replay.py --repo ~/artistme/python/delegate --base 50c804f --target 4600115 \
      --tests tests/test_delegate.py --window 300000 --cond solo parent --reps 2
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

BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH.parent))
sys.path.insert(0, str(BENCH))
import defects  # noqa: E402
from tokenguard import transcripts as T  # noqa: E402

WORK = Path(os.environ.get("TOKENGUARD_BENCH_DIR", Path.home() / ".cache/tokenguard/bench")) / "replay"
TOOLS = ["Read", "Edit", "Write", "Glob", "Grep", "Bash(python3 -m unittest*)", "Bash(python3 -m py_compile*)",
         "Bash(git diff*)", "Bash(git status*)", "Bash(ls*)"]


def sh(*a, cwd=None, check=True):
    return subprocess.run(a, cwd=cwd, capture_output=True, text=True, check=check)


def test_cmd(tests: list[str]) -> str:
    mod = tests[0].removesuffix(".py").replace("/", ".")
    return f"python3 -m unittest {mod}"


def run_tests(wt: Path, tests: list[str]) -> tuple[int, int]:
    r = subprocess.run(test_cmd(tests).split(), cwd=wt, capture_output=True, text=True, timeout=600)
    out = r.stderr
    ran = int(m.group(1)) if (m := re.search(r"Ran (\d+) test", out)) else 0
    bad = sum(int(x) for x in re.findall(r"(?:failures|errors)=(\d+)", out))
    return ran - bad, ran


def task_text(a) -> str:
    msg = sh("git", "show", "-s", "--format=%B", a.target, cwd=a.repo).stdout
    return "\n".join(line for line in msg.splitlines() if not line.startswith("Co-Authored-By"))


def solo_prompt(a) -> tuple[str, list[str]]:
    prompt = (f"このリポジトリに次の変更を実装して。\n\n{task_text(a)}\n\n"
              f"{a.tests[0]} は完成形のテスト。テストは変更せず、すべて通るように実装すること。"
              f"最後に python3 -m unittest で通ることを確かめ、変更点を 3 行で報告して。")
    return prompt, TOOLS


def parent_prompt(a, spec_dir: Path) -> tuple[str, list[str]]:
    worker = f"python3 {BENCH / 'worker.py'}"
    prompt = (
        "あなたは親役。コードは自分で書かず、作業役(GitHub Copilot)に実装させてレビューする。\n\n"
        f"依頼:\n{task_text(a)}\n\n"
        f"{a.tests[0]} は完成形のテスト。テストは変更させず、すべて通るようにさせること。\n\n"
        "手順:\n"
        "1. 依頼と関連コード・テストを読み、作業役向けの仕様書を書く。変更するファイル・関数・振る舞い、"
        "やってはいけないこと(仕様外の変更・空コメント・未使用コード・テストの変更)を具体的に書く。"
        f"仕様書は {spec_dir}/spec1.md に Write で置く(このディレクトリ以外には書けない)。\n"
        f"2. `{worker} {spec_dir}/spec1.md` を Bash で実行する(timeout は 1200000)。作業役が実装し、"
        "テストを回して直すところまで行う。\n"
        f"3. `git diff {a.base}` を読んでレビューする。見るもの: テストが通るか、バグ、仕様外の変更、"
        "空のコメント、未使用の import や関数、既存の振る舞いを壊していないか。\n"
        f"4. 直すべき点があれば、差し戻し内容を {spec_dir}/spec2.md(次は spec3.md)に書き、"
        "同じコマンドで作業役に直させる。差し戻しは 2 回まで。\n"
        "5. 最後に結果と残った問題を 3 行で報告する。\n"
        "コードを Edit/Write で直接変えてはいけない。"
    )
    tools = ["Read", "Glob", "Grep", f"Write(/{spec_dir}/**)", f"Edit(/{spec_dir}/**)", f"Bash({worker}*)",
             "Bash(git diff*)", "Bash(git status*)", "Bash(git log*)", "Bash(git show*)",
             "Bash(python3 -m unittest*)", "Bash(ls*)"]
    return prompt, tools


REVIEW_KEYS = ["bug", "out_of_spec", "dead_code", "empty_comment"]


def blind_review(a, diff: str) -> dict:
    """両条件の差分を同じ条件で採点する独立レビュー。どの条件の差分かは伝えない。

    テストの通過数では見えない欠陥(仕様外の変更・未使用コードなど)を数えるため。ツールは与えず、
    空のディレクトリで動かす。レビューの費用は条件の費用に含めない。
    """
    prompt = (
        "あなたは独立したコードレビュアー。次の依頼に対する実装の差分(テストファイルは除いてある)を読み、欠陥を挙げる。\n"
        "分類: bug(依頼どおりに動かない・既存の振る舞いを壊す・例外処理の漏れ)、out_of_spec(依頼にない変更・不要な書き換え)、"
        "dead_code(使われない関数・import・到達しない分岐)、empty_comment(中身のない・コードを繰り返すだけのコメント)。"
        "確信があるものだけを、1 件 1 行の短い日本語で挙げる。好みの問題は挙げない。\n"
        f"次のキーを持つ JSON だけを返す: {json.dumps(REVIEW_KEYS)}(値は文字列の配列)\n\n"
        f"依頼:\n{task_text(a)}\n\n差分:\n{diff[:200_000]}")
    cwd = WORK / f"review-{int(time.time() * 1000)}"
    cwd.mkdir(parents=True)
    r = subprocess.run(["claude", "-p", prompt, "--model", a.review_model, "--output-format", "json",
                        "--disallowedTools", "Bash", "Read", "Edit", "Write", "Glob", "Grep", "WebFetch", "WebSearch",
                        "Task"], cwd=cwd, capture_output=True, text=True, timeout=1800,
                       env={**os.environ, "TOKENGUARD_CTX_STEPS": "999999999"})
    out = json.loads(r.stdout) if r.stdout.strip() else {}
    text = out.get("result", "")
    m = re.search(r"\{.*\}", text, re.S)
    try:
        got = json.loads(m.group(0)) if m else {}
    except ValueError:
        got = {}
    res = {k: len(got.get(k) or []) for k in REVIEW_KEYS}
    res["total"] = sum(res.values())
    res["items"] = {k: got.get(k) or [] for k in REVIEW_KEYS}
    res["cost_usd"] = out.get("total_cost_usd", 0)
    return res


def worker_totals(log_dir: Path) -> dict:
    calls = [json.loads(p.read_text()) for p in sorted(log_dir.glob("call*.json"), key=lambda p: int(p.stem[4:]))]
    out = {"worker_calls": len(calls), "worker_rounds": sum(len(c.get("rounds") or []) for c in calls),
           "worker_tokens_in": sum(c.get("tokens_in") or 0 for c in calls),
           "worker_tokens_out": sum(c.get("tokens_out") or 0 for c in calls),
           "worker_credits": round(sum(c.get("credits") or 0 for c in calls), 4),
           "worker_seconds": round(sum(c.get("duration") or 0 for c in calls))}
    if calls:
        out["defects_before"] = calls[0].get("defects")
    return out


def trial(a, window: int, cond: str = "solo") -> dict:
    stamp = f"{Path(a.repo).name}-{cond}-{window // 1000}k-{int(time.time())}"
    wt = WORK / stamp
    side = WORK / f"{stamp}-side"  # 仕様書と作業役のログ。作業ツリーの外に置き、採点の差分に混ぜない
    wt.parent.mkdir(parents=True, exist_ok=True)
    sh("git", "worktree", "add", "--detach", str(wt), a.base, cwd=a.repo)
    res = {"cond": cond, "window": window, "model": a.model, "base": a.base, "target": a.target}
    try:
        sh("git", "checkout", a.target, "--", *a.tests, cwd=wt)
        target_files = sh("git", "diff", "--name-only", a.base, a.target, cwd=a.repo).stdout.split()
        env = {**os.environ, "TOKENGUARD_CTX_STEPS": "999999999"}
        if cond == "parent":
            (side / "spec").mkdir(parents=True)
            prompt, tools = parent_prompt(a, side / "spec")
            env |= {"BENCH_LOG_DIR": str(side / "log"), "BENCH_BASE": a.base, "BENCH_TEST_CMD": test_cmd(a.tests),
                    "BENCH_TESTS": json.dumps(a.tests),
                    "BENCH_TARGET_FILES": json.dumps(target_files),
                    # 作業役の呼び出しは数分かかるので、Bash の既定の 2 分で切られないようにする
                    "BASH_DEFAULT_TIMEOUT_MS": "1200000", "BASH_MAX_TIMEOUT_MS": "1800000"}
        else:
            prompt, tools = solo_prompt(a)
        t0 = time.time()
        r = subprocess.run(["claude", "-p", prompt, "--model", a.model, "--output-format", "json",
                            "--allowedTools", *tools, "--settings", json.dumps({"autoCompactWindow": window})],
                           cwd=wt, capture_output=True, text=True, timeout=5400, env=env)
        res["seconds"] = round(time.time() - t0)
        out = json.loads(r.stdout) if r.stdout.strip() else {}
        res["cost_usd"] = out.get("total_cost_usd", 0)
        sid = out.get("session_id")
        res["tests_modified"] = bool(sh("git", "diff", "--name-only", a.target, "--", *a.tests, cwd=wt).stdout.strip())
        sh("git", "checkout", a.target, "--", *a.tests, cwd=wt)  # テストの書き換えを無効にする
        res["passed"], res["ran"] = run_tests(wt, a.tests)
        res["defects_after"] = defects.count(wt, a.base, target_files, a.tests)
        final_diff = defects.strip_files(sh("git", "diff", a.base, cwd=wt).stdout, a.tests)
        if cond == "parent":
            res.update(worker_totals(side / "log"))
            first = side / "log" / "call1.diff"
            if first.exists() and not a.no_review:
                res["review_before"] = blind_review(a, defects.strip_files(first.read_text(), a.tests))
        if not a.no_review:
            res["review_after"] = blind_review(a, final_diff)
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
    ap.add_argument("--tests", required=True, nargs="+", help="完成形のテスト。先頭のファイルを unittest で回す")
    ap.add_argument("--cond", nargs="+", default=["solo"], choices=["solo", "parent"])
    ap.add_argument("--window", type=int, nargs="+", default=[1_000_000, 300_000, 200_000])
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--keep", action="store_true", help="作業ツリーを消さずに残す")
    ap.add_argument("--review-model", default="sonnet", help="独立レビューのモデル")
    ap.add_argument("--no-review", action="store_true", help="独立レビューを省く")
    a = ap.parse_args()
    a.repo = str(Path(a.repo).expanduser())
    WORK.mkdir(parents=True, exist_ok=True)
    log = WORK.parent / "replay_results.jsonl"
    for _ in range(a.reps):
        for w in a.window:
            for cond in a.cond:
                res = trial(a, w, cond)
                with open(log, "a") as f:
                    f.write(json.dumps(res, ensure_ascii=False) + "\n")
                print(json.dumps(res, ensure_ascii=False), flush=True)
    print(f"結果は {log} に追記した")


if __name__ == "__main__":
    main()
