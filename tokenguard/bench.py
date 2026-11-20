"""記憶テスト: 窓の大きさを変えたとき、compact で会話の前半の事実をどれだけ忘れるかを測る。

1 回の試行の流れ(すべて `claude -p` と `--resume` で同じ会話を続ける):
  1. 事実を 7 個伝える(決定事項・却下した案とその理由・固有の値)
  2. 埋め草の資料を 1 つずつメッセージで渡して要約させ、文脈を膨らませる(途中で事実を 3 個追加・1 個変更)
  3. 最後に 10 問を JSON で答えさせ、自動で採点する
窓の条件は `--settings '{"autoCompactWindow": N}'` で与える(ユーザー設定より優先される)。
"""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import transcripts as T

WORK = Path(os.environ.get("TOKENGUARD_BENCH_DIR", Path.home() / ".cache/tokenguard/bench"))
# 埋め草の語彙。答えと紛れないよう、数字・人名・技術名を含めない
SYLL = ["ka", "ri", "mo", "ten", "su", "lo", "vex", "na", "dor", "pi", "qua", "zel", "mu", "ash", "fen", "ol"]


@dataclass
class Fact:
    key: str
    say: str  # 会話で伝える文
    ask: str  # 質問
    answer: str  # 期待する答え(部分一致で採点)


def make_facts(rng: random.Random) -> tuple[list[Fact], list[Fact], str]:
    port = str(rng.randint(20000, 59999))
    db, rej = rng.sample(["PostgreSQL", "MySQL", "MongoDB", "CockroachDB", "DynamoDB"], 2)
    reason = rng.choice(["監査ログとの結合", "書き込みの整合性", "運用コスト", "スキーマ移行の手間"])
    date = f"2027-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
    code = f"{rng.choice('QWXZ')}{rng.randint(2, 9)}-{rng.choice(['ZEBRA', 'OTTER', 'HERON', 'LYNX'])}"
    path = f"/etc/{rng.choice(['kestrel', 'osprey', 'merlin'])}/{rng.choice(['core', 'edge'])}.toml"
    team = rng.choice(["ペンギン班", "カワウソ班", "フクロウ班", "ヤマネ班"])
    limit = str(rng.randint(120, 980))
    t_old, t_new = 30, rng.choice([45, 55, 75, 90])
    build = str(rng.randint(1000, 9999))
    cache_rej = rng.choice(["Redis", "Memcached"])
    early = [
        Fact("port", f"ステージング環境のポートは {port} に決めた。", "ステージング環境のポート番号", port),
        Fact("db", f"データベースは {db} に決定。{rej} 案は却下した。", "採用したデータベース", db),
        Fact("rejected_db", "", "却下したデータベース案", rej),
        Fact("release", f"リリース日は {date} とする。", "リリース日(YYYY-MM-DD)", date),
        Fact("code", f"この案件の担当コードは {code}。", "担当コード", code),
        Fact("cache_reason", f"キャッシュに {cache_rej} を使う案は却下。理由は{reason}が問題になるため。",
             f"{cache_rej} 案を却下した理由", reason),
        Fact("timeout", f"API のタイムアウトは {t_old} 秒にする。", "API のタイムアウト(秒、最新の決定)", str(t_new)),
    ]
    late = [
        Fact("config", f"設定ファイルの置き場所は {path} に決まった。", "設定ファイルのパス", path),
        Fact("team", f"レビュー担当は {team}。", "レビュー担当", team),
        Fact("limit", f"1 日あたりの処理上限は {limit} 件。", "1 日あたりの処理上限(件数)", limit),
        Fact("build", f"今回のビルド番号は {build}。", "ビルド番号", build),
    ]
    change = f"変更: API のタイムアウトは {t_old} 秒ではなく {t_new} 秒にする。"
    return early, late, change


def make_fillers(d: Path, n: int, rng: random.Random, words: int = 11_000) -> list[Path]:
    """1 ファイルあたり約 2 万トークン(Read の上限 25k に収める)の意味のない文書を作る。"""
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for i in range(n):
        lines = []
        for _ in range(words // 12):
            lines.append(" ".join("".join(rng.choices(SYLL, k=rng.randint(2, 4))) for _ in range(12)))
        p = d / f"notes_{i:02d}.txt"
        p.write_text(f"# 議事メモ {i}(本文は暗号化済み。要約は 1 行でよい)\n" + "\n".join(lines) + "\n")
        out.append(p)
    return out


@dataclass
class Trial:
    window: int
    seed: int
    score: int = 0
    total: int = 0
    wrong: list[str] = field(default_factory=list)
    weighted: float = 0.0
    compactions: int = 0
    peak: int = 0
    cost_usd: float = 0.0
    seconds: float = 0.0
    error: str = ""


def _claude(prompt: str, cwd: Path, model: str, window: int, sid: str | None) -> dict:
    cmd = ["claude", "-p", prompt, "--model", model, "--output-format", "json",
           "--allowedTools", "Read", "--settings", json.dumps({"autoCompactWindow": window})]
    if sid:
        cmd += ["--resume", sid]
    # 文脈の促し hook が結果を乱さないよう止める
    env = {**os.environ, "TOKENGUARD_CTX_STEPS": "999999999"}
    for attempt in range(2):
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=900, env=env)
        if not r.returncode:
            return json.loads(r.stdout)
        # 一時的な制限で落ちることがあるので 1 回だけ待って再試行する。原因は stdout の JSON に出る
        err = (r.stderr.strip() or r.stdout.strip())[-300:]
        if attempt == 0:
            time.sleep(90)
    raise RuntimeError(f"claude 終了コード {r.returncode}: {err}")


def score(answer_text: str, facts: list[Fact]) -> tuple[int, list[str]]:
    m = re.search(r"\{.*\}", answer_text, re.S)
    got = {}
    if m:
        try:
            got = json.loads(m.group(0))
        except ValueError:
            pass
    norm = lambda s: re.sub(r"\s+", "", str(s)).lower()  # noqa: E731
    wrong = [f.key for f in facts if norm(f.answer) not in norm(got.get(f.key, ""))]
    return len(facts) - len(wrong), wrong


def run_trial(window: int, seed: int, n_files: int, model: str, log=print) -> Trial:
    rng = random.Random(seed)
    tr = Trial(window, seed)
    cwd = WORK / f"w{window // 1000}k-s{seed}-{int(time.time())}"
    early, late, change = make_facts(rng)
    files = make_fillers(cwd, n_files, rng)
    t0 = time.time()
    try:
        r = _claude("これから案件の決定事項を伝える。あとで質問するので覚えておくこと。返事は「了解」だけでよい。\n"
                    + "\n".join(f.say for f in early if f.say), cwd, model, window, None)
        sid = r["session_id"]
        cost = r.get("total_cost_usd", 0)
        mid = n_files // 2
        for i, p in enumerate(files):
            extra = ""
            if i == mid:
                extra = "\nあわせて決定事項の追加と変更:\n" + "\n".join(f.say for f in late) + "\n" + change
            # Read の結果は Claude Code が古い順に消すことがあり文脈が育たないので、本文に直接入れる
            r = _claude(f"次の資料を 1 行で要約して。{extra}\n\n{p.read_text()}", cwd, model, window, sid)
            sid = r["session_id"]
            cost = max(cost, r.get("total_cost_usd", 0))
            log(f"  [{window // 1000}k s{seed}] {i + 1}/{n_files}")
        facts = early + late
        q = "\n".join(f'"{f.key}": {f.ask}' for f in facts)
        r = _claude("ファイルは読まずに、これまでの会話で伝えた決定事項について答えて。分からなければ \"不明\"。"
                    "次のキーを持つ JSON だけを返す:\n" + q, cwd, model, window, sid)
        # total_cost_usd は --resume をまたいだ累計なので、足さずに最後の値を使う
        cost = max(cost, r.get("total_cost_usd", 0))
        tr.score, tr.wrong = score(r.get("result", ""), facts)
        tr.total = len(facts)
        tr.cost_usd = cost
        hits = list(T.PROJECTS.rglob(f"{sid}.jsonl"))
        if hits:
            s = T.parse(hits[0])
            tr.weighted, tr.compactions, tr.peak = s.weighted, s.compactions, s.peak
    except Exception as e:  # 1 試行の失敗で全体を止めない
        tr.error = str(e)[:300]
    tr.seconds = time.time() - t0
    return tr
