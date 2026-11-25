#!/usr/bin/env python3
"""委任先のモデルごとに、下調べ・要約・調べものの正確さを測る(agy 専用)。

- survey: delegate リポジトリについての設問に、ファイルを読んで答えさせる。正解は commit を固定して作者が確かめた値
- summarize: tokenguard の README の実験の節を渡し、数値や判断を抜き出させる
- research: Web で調べさせ、各主張に URL と原文の引用を付けさせる。引用が出典にあるかを research/verify.py で確かめる

survey と summarize には、資料に無いことを尋ねる設問(probe)を混ぜる。「記載なし」と答えられずに値を作れば
ハルシネーションとして数える。採点は正規表現の一致だけで行い、言い換えの正誤は判定しない(結果の JSON を目で確かめる)。

例:
  python3 bench/accuracy.py --models gemini-4-neon-medium gemini-3.8-flash-low --tasks survey summarize research
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "research"))
import verify  # noqa: E402

READONLY = {"agentMode": "", "permissions": {"deny": ["command(*)", "write_file(*)", "mcp(*)"]}}
NONE = r"(記載な|存在しな|見当たらな|ない|なし|不明|null|none|n/a)"

DELEGATE = Path.home() / "artistme/python/delegate"
DELEGATE_REV = "4ba8b59"
SURVEY = {
    "q1": ("summarize タスクの既定のモデル名", r"gemini-3\.8-flash-low"),
    "q2": ("implement タスクの既定の委任先(backend)", r"copilot"),
    "q3": ("implement タスクで、テストの失敗を差し戻す最大回数の既定値(初回を含む)", r"^\D*3\D*$"),
    "q4": ("agy backend の既定のタイムアウト秒数", r"600"),
    "q5": ("リポジトリ内の既定値(config.py)での、copilot に対する secret_policy の値", r"mask"),
    "q6": ("安全装置が委任を拒否したときの delegate の終了コード", r"^\D*2\D*$"),
    "q7": ("秘匿情報を中身で判定するときに読むファイルの最大バイト数の既定値", r"262144"),
    "q8": ("agy に渡すコマンドライン引数を組み立てる関数の名前", r"build_agy_argv"),
    "q9": ("gh タスクのフォールバック先", NONE),
    "q10": ("Copilot にシェルを使わせないために渡しているコマンドラインオプション", r"--deny-tool\W+shell"),
    "h1": ("`--model` を指定して最初の委任先が失敗し、フォールバック先に切り替わったとき、フォールバック先に渡すモデル名",
           r"(空|\"\"|''|既定|default|渡さな|指定しな)"),
    "h2": ("secret_policy が mask で、秘匿ファイルの走査が上限(scan_depth/max_scan_files)で打ち切られたときの振る舞い",
           r"(拒否|委任しな|GuardError|refuse|しない|できない)"),
    "h3": ("secret_policy が allow で、走査が上限で打ち切られたときの振る舞い", r"(委任する|隠さ|空|そのまま|許可|通す|allow)"),
    "h4": ("gh タスクで委任先のプロセスを動かすディレクトリ", r"(一時|temp|mkdtemp|空の)"),
    "h5": ("Copilot の credits を計算する元の JSON フィールド名と換算式", r"totalNanoAiu.*1e9|totalNanoAiu.*10\^?9|totalNanoAiu.*1,?000,?000,?000"),
    "h6": ("委任の記録(ログ)の既定の保存先パス(環境変数を設定しない場合)", r"\.local/state/delegate/log\.jsonl"),
    "h7": ("implement で差し戻しのたびに前回の会話を引き継ぐために Copilot に渡すオプション", r"--session-id"),
    "h8": ("survey タスクでプロンプトに添えるファイル一覧の最大件数の既定値", r"400"),
    "p1": ("設定の max_retries の既定値", NONE),
    "p2": ("Copilot に渡している --max-ai-credits の既定値", NONE),
    "p3": ("agy backend に渡している --effort の既定値", NONE),
}

README = ROOT / "README.md"
SUMMARY = {
    "q1": ("記憶テストで、窓 200k のときの費用(USD)", r"2\.27"),
    "q2": ("親+作業役 の比較で、題材 A の親+作業役の親の重み付き消費", r"343"),
    "q3": ("親+作業役 の所要時間は単独の何倍か", r"2\.4"),
    "q4": ("題材 B の作業役の費用(AI credits)", r"2\.6"),
    "q5": ("独立レビューを回した合計回数", r"22"),
    "q6": ("本番 8 試行の親の費用の合計(USD)", r"4\.47"),
    "q7": ("作業役(Copilot CLI)の既定モデル", r"gpt-5\.6-luna"),
    "q8": ("親+作業役 を導入するかどうかの判断", r"(導入しない|不採用|しない)"),
    "q9": ("導入後の実測で、文脈が頭打ちになった大きさ", r"267"),
    "q10": ("記憶テストに使ったモデル", r"sonnet"),
    "h1": ("14 日分で、cache 切れ(最後の応答から 1 時間超)の書き直しが費用に占めた割合", r"15\.6"),
    "h2": ("ttl_guard の効果の見積もり(14 日分、300k 窓が基準)", r"2\.8.*7\.7"),
    "h3": ("55 分放置で自動 compact する案の、悲観的な見積もり(14 日 / 直近 3 日)", r"5\.5.*10\.1"),
    "h4": ("サブエージェントが費用に占めた割合", r"0\.45"),
    "h5": ("独立レビューで、本番で 3 件だった差分 2 つを再採点したときの件数", r"10.*14.*13.*10"),
    "h6": ("ログ分析に使った期間と会話数と呼び出し回数(研究の記録の節)", r"14.*303.*36,?566"),
    "h7": ("agy が出した主張のうち引用の検証を通った件数と全体の件数", r"(61.*72|72.*61)"),
    "h8": ("記憶テストで、決定事項を伝えたあと文脈を何トークン近くまで育てたか", r"43"),
    "p1": ("親を Opus にした場合の節約率", NONE),
    "p2": ("題材 C の隠しテストの通過数", NONE),
    "p3": ("AI credits 1 件あたりの確定したドル換算値", NONE),
}

RESEARCH = {
    "py313": "Python 3.13 で入った主な変更(free-threaded ビルド、実験的な JIT、新しい対話シェル、削除されたモジュールなど)",
    "sqlite_wal": "SQLite の WAL モードの仕組み・利点・制約(チェックポイント、読み書きの並行性、ネットワークファイルシステムでの制限など)",
}


def run_agy(prompt: str, model: str, cwd: Path, timeout: int = 900) -> tuple[dict, float]:
    t0 = time.time()
    try:
        r = subprocess.run(["agy", "-p", prompt, "--model", model, "--output-format", "json",
                            "--print-timeout", f"{timeout - 30}s", "--settings", json.dumps(READONLY)],
                           cwd=cwd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        out = r.stdout
    except subprocess.TimeoutExpired:
        out = ""
    try:
        d = json.loads(out[out.index("{"):])
    except ValueError:
        d = {"status": "NO_OUTPUT"}
    return d, round(time.time() - t0)


def ask_json(questions: dict) -> str:
    qs = "\n".join(f"- {k}: {q}" for k, (q, _) in questions.items())
    return ("次の設問に答え、キーを設問 ID、値を短い答え(文字列)とする JSON だけを返す。"
            "資料に書かれていない・確かめられないものは、推測せず \"記載なし\" と答える。\n" + qs)


def grade(answer: dict, questions: dict) -> dict:
    res = {"correct": 0, "wrong": [], "probe_hallucinated": []}
    for k, (_, pat) in questions.items():
        v = str(answer.get(k, "")).strip()
        ok = bool(re.search(pat, v, re.I))
        if ok:
            res["correct"] += 1
        elif k.startswith("p"):
            res["probe_hallucinated"].append(f"{k}={v[:80]}")
        else:
            res["wrong"].append(f"{k}={v[:80]}")
    res["total"] = len(questions)
    return res


def extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except ValueError:
        return {}


def task_survey(model: str, work: Path) -> dict:
    wt = work / f"survey-{re.sub(r'[^\w.-]', '_', model)}-{time.time_ns()}"
    subprocess.run(["git", "worktree", "add", "--detach", str(wt), DELEGATE_REV], cwd=DELEGATE,
                   capture_output=True, check=True)
    try:
        prompt = "このディレクトリは delegate というツールのリポジトリ。ソースを読んで答える。\n" + ask_json(SURVEY)
        d, sec = run_agy(prompt, model, wt)
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=DELEGATE, capture_output=True)
    return {"seconds": sec, "status": d.get("status"), "usage": d.get("usage"),
            "answer": extract_json(d.get("response", "")), **grade(extract_json(d.get("response", "")), SURVEY)}


def task_summarize(model: str, work: Path) -> dict:
    lines = README.read_text().splitlines()
    start = next(i for i, s in enumerate(lines) if s.startswith("## 実験"))
    end = next(i for i, s in enumerate(lines) if s.startswith("## cache 切れ"))
    src = work / f"summ-{re.sub(r'[^\w.-]', '_', model)}-{time.time_ns()}"
    src.mkdir(parents=True)
    # 今回の実験の結果が README に追記されても設問の正解が変わらないよう、節を切り出して渡す
    sec_text = "\n".join(lines[start:end])
    sec_text = sec_text.split("### 2026-11-24")[0]
    research = (ROOT / "research/README.md").read_text()
    prompt = ("次の 2 つの資料を読んで答える。\n\n<資料1>\n" + sec_text + "\n</資料1>\n\n<資料2>\n" + research
              + "\n</資料2>\n\n" + ask_json(SUMMARY))
    d, sec = run_agy(prompt, model, src)
    ans = extract_json(d.get("response", ""))
    return {"seconds": sec, "status": d.get("status"), "usage": d.get("usage"), "answer": ans,
            **grade(ans, SUMMARY)}


def task_research(model: str, work: Path, theme: str) -> dict:
    cwd = work / f"res-{re.sub(r'[^\w.-]', '_', model)}-{theme}-{time.time_ns()}"
    cwd.mkdir(parents=True)
    prompt = (f"テーマ: {RESEARCH[theme]}\nWeb で一次資料(公式文書など)を調べ、事実の主張を 8 件挙げる。"
              "各主張に、出典の URL と、その出典の本文からそのまま写した英語の引用(1 文、5 語以上、省略記号なし)を付ける。"
              "次の形の JSON だけを返す: {\"claims\": [{\"id\": \"...\", \"claim\": \"...\", \"url\": \"...\", "
              "\"quote\": \"...\"}]}")
    d, sec = run_agy(prompt, model, cwd)
    claims = extract_json(d.get("response", "")).get("claims") or []
    statuses = [verify.check(c) for c in claims]
    ok = sum(s.startswith("verified") for s in statuses)
    return {"seconds": sec, "status": d.get("status"), "usage": d.get("usage"), "theme": theme,
            "claims": len(claims), "verified": ok, "statuses": statuses,
            "rejected": [{"url": c.get("url"), "quote": c.get("quote", "")[:120], "status": s}
                         for c, s in zip(claims, statuses) if not s.startswith("verified")]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--tasks", nargs="+", default=["survey", "summarize", "research"])
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--log", default=str(Path.home() / ".cache/tokenguard/bench/accuracy.jsonl"))
    a = ap.parse_args()
    work = Path.home() / ".cache/tokenguard/bench/accuracy"
    work.mkdir(parents=True, exist_ok=True)
    jobs = []
    for _ in range(a.reps):
        for m in a.models:
            for t in a.tasks:
                if t == "research":
                    jobs += [(m, t, th) for th in RESEARCH]
                else:
                    jobs.append((m, t, None))

    def one(job):
        m, t, th = job
        try:
            r = task_research(m, work, th) if t == "research" else globals()[f"task_{t}"](m, work)
        except Exception as e:  # 1 件の失敗で全体を止めない
            r = {"error": str(e)[:300]}
        r |= {"model": m, "task": t}
        with open(a.log, "a") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        brief = {k: r.get(k) for k in ("model", "task", "theme", "correct", "total", "verified", "claims",
                                       "seconds", "status", "error")}
        print(json.dumps(brief, ensure_ascii=False), flush=True)

    with ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(one, jobs))


if __name__ == "__main__":
    main()
