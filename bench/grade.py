#!/usr/bin/env python3
"""replay が残した差分を、条件名を伏せて固定の採点表で採点する(事後採点)。

- 採点者は別系統の 2 モデル(既定: agy の claude-opus-5-5-high と gemini-4-neon-high)。各 2 回
- 採点表の各項目は 0〜2 点。4 票の中央値をその差分の点にする
- 4 票の幅が 2 以上(0 点と 2 点が両方ある)の項目は「不一致」として別に数える
- 採点の失敗は 0 点と数えず、票から外して失敗数を記録する
- 正解の commit(再現対象)の差分も同じ表で採点し、基準にする
agy の Claude は Claude の使用量に数えられない(2026-11-24 確認)ので、採点の費用は Claude 側にかからない。

使い方: python3 bench/grade.py ~/.cache/tokenguard/bench/exp1124/replay.jsonl
結果: 入力と同じ場所の grades.jsonl(差分ファイルごと)に追記する。採点済みの差分は飛ばす。
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import defects  # noqa: E402

RUBRIC = {
    "R1_requirements": "依頼に書かれた機能・変更をすべて満たしている(2: すべて / 1: 一部欠ける / 0: 主要部分が欠ける)",
    "R2_no_regression": "既存の振る舞いを壊していない(2: 壊していない / 1: 軽微な懸念 / 0: 明らかに壊している)",
    "R3_edge_cases": "例外・境界値・失敗時の扱いが妥当(2: 妥当 / 1: 一部漏れ / 0: 重大な漏れ)",
    "R4_scope": "依頼にない変更・不要な書き換えがない(2: ない / 1: 少しある / 0: 多い)",
    "R5_clean": "未使用コード・空や冗長なコメント・TODO がない(2: ない / 1: 少しある / 0: 多い)",
    "R6_style": "既存のコードの作法に沿い、読みやすい(2: 沿う / 1: 一部外れる / 0: 大きく外れる)",
}
GRADERS = ["claude-opus-5-5-high", "gemini-4-neon-high"]
READONLY = {"agentMode": "", "permissions": {"deny": ["command(*)", "write_file(*)", "mcp(*)"]}}


def task_text(repo: str, target: str) -> str:
    msg = subprocess.run(["git", "show", "-s", "--format=%B", target], cwd=repo, capture_output=True, text=True).stdout
    return "\n".join(line for line in msg.splitlines() if not line.startswith("Co-Authored-By"))


def prompt(task: str, diff: str) -> str:
    items = "\n".join(f"- {k}: {v}" for k, v in RUBRIC.items())
    keys = json.dumps({**{k: 0 for k in RUBRIC}, "bugs": ["..."]}, ensure_ascii=False)
    return ("あなたは独立したコードレビュアー。次の依頼に対する実装の差分(テストファイルは除いてある)を、"
            "固定の採点表で採点する。差分だけで判断し、確信のない減点はしない。\n\n"
            f"採点表(各 0〜2 点):\n{items}\n\n"
            "bugs には、依頼どおりに動かない・既存の振る舞いを壊すと確信できる欠陥だけを 1 件 1 行で挙げる。\n"
            f"次の形の JSON だけを返す: {keys}\n\n依頼:\n{task}\n\n差分:\n{diff[:200_000]}")


def one_vote(model: str, text: str, cwd: Path) -> dict:
    try:
        r = subprocess.run(["agy", "-p", text, "--model", model, "--output-format", "json", "--print-timeout",
                            "870s", "--settings", json.dumps(READONLY)], cwd=cwd, capture_output=True, text=True,
                           timeout=900, stdin=subprocess.DEVNULL)
        out = r.stdout
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    try:
        d = json.loads(out[out.index("{"):])
        m = re.search(r"\{.*\}", d.get("response", ""), re.S)
        got = json.loads(m.group(0))
        votes = {k: int(got[k]) for k in RUBRIC}
        if not all(0 <= v <= 2 for v in votes.values()):
            raise ValueError("out of range")
        return {**votes, "bugs": [str(b) for b in got.get("bugs") or []]}
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        return {"error": f"{type(e).__name__}: {str(e)[:120]} / {out[-200:]}"}


def grade(task: str, diff: str, work: Path, reps: int) -> dict:
    text = prompt(task, diff)
    jobs = [m for m in GRADERS for _ in range(reps)]
    with ThreadPoolExecutor(len(jobs)) as ex:
        votes = list(ex.map(lambda m: {"grader": m, **one_vote(m, text, work)}, jobs))
    ok = [v for v in votes if "error" not in v]
    res = {"votes": votes, "failed_votes": len(votes) - len(ok)}
    if not ok:
        return res
    res["items"] = {k: statistics.median(v[k] for v in ok) for k in RUBRIC}
    res["score"] = sum(res["items"].values())
    res["disagree"] = [k for k in RUBRIC if max(v[k] for v in ok) - min(v[k] for v in ok) >= 2]
    res["bugs_median"] = statistics.median(len(v["bugs"]) for v in ok)
    res["by_grader"] = {m: statistics.mean(sum(v[k] for k in RUBRIC) for v in ok if v["grader"] == m)
                        for m in GRADERS if any(v["grader"] == m for v in ok)}
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--reps", type=int, default=2, help="採点者ごとの回数")
    ap.add_argument("--jobs", type=int, default=2, help="同時に採点する差分の数(1 差分 = 4 票)")
    a = ap.parse_args()
    src = Path(a.results).expanduser()
    out = src.parent / "grades.jsonl"
    done = {json.loads(line)["diff_file"] for line in out.open()} if out.exists() else set()
    work = src.parent / "grade-work"
    work.mkdir(exist_ok=True)
    rows = [json.loads(line) for line in src.open()]
    todo, refs = [], {}
    for r in rows:
        if r.get("diff_file") and r["diff_file"] not in done and Path(r["diff_file"]).exists():
            todo.append((r["diff_file"], r["repo"], r["base"], r["target"]))
        if r.get("repo"):
            refs[(r["repo"], r["base"], r["target"])] = 1
    for repo, base, target in refs:  # 正解の commit も同じ表で採点して基準にする
        f = src.parent / "diffs" / f"reference-{Path(repo).name}-{target}.diff"
        if not f.exists():
            tests = [p for p in subprocess.run(["git", "diff", "--name-only", base, target], cwd=repo,
                                               capture_output=True, text=True).stdout.split() if "test" in p]
            diff = subprocess.run(["git", "diff", base, target], cwd=repo, capture_output=True, text=True).stdout
            f.parent.mkdir(exist_ok=True)
            f.write_text(defects.strip_files(diff, tests))
        if str(f) not in done:
            todo.append((str(f), repo, base, target))

    def run(job):
        f, repo, base, target = job
        res = grade(task_text(repo, target), Path(f).read_text(), work, a.reps)
        res |= {"diff_file": f, "target": target, "ts": time.time()}
        with out.open("a") as fh:
            fh.write(json.dumps(res, ensure_ascii=False) + "\n")
        print(f"{Path(f).name}: score={res.get('score')} disagree={res.get('disagree')} "
              f"failed={res['failed_votes']}", flush=True)

    with ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(run, todo))


if __name__ == "__main__":
    main()
