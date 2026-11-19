#!/usr/bin/env python3
"""UserPromptSubmit hook: 文脈が大きくなった会話で、区切りを付けるよう Claude に促す。

費用の大半は「長い会話の文脈を毎回読み直す」cache read なので、
新しい依頼が来た時点で文脈が大きければ、引き継ぎ(/handoff)と新しい会話を提案させる。
同じ段階では 1 回しか注入しない(注入文そのものが文脈を増やすため)。
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tokenguard.transcripts import last_context  # noqa: E402

STATE = Path(os.environ.get("TOKENGUARD_STATE", Path.home() / ".cache/tokenguard/ctx"))
# 段階の境目(トークン)。環境変数で上書きできる
STEPS = [int(x) for x in os.environ.get("TOKENGUARD_CTX_STEPS", "120000,180000,250000,350000").split(",")]


def message(ctx: int) -> str:
    k = ctx // 1000
    if ctx >= STEPS[min(2, len(STEPS) - 1)]:
        return (f"[tokenguard] 文脈 {k}k。この会話は重い。今回の依頼が前の作業と独立なら、着手前に "
                "/handoff で引き継ぎを書いて新しい会話へ移るようユーザーに一言提案する。"
                "続きなら、画像・長いログ・全文 Read を避け、範囲指定で読む。")
    return (f"[tokenguard] 文脈 {k}k。依頼が前の作業と無関係なら、新しい会話で始める方が安い旨を一言添える。"
            "続きなら、大きな出力(画像・長いログ)を文脈に入れない。")


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    tp, sid = data.get("transcript_path"), data.get("session_id", "x")
    if not tp:
        return
    ctx = last_context(tp)
    level = sum(1 for s in STEPS if ctx >= s)
    if level == 0:
        return
    STATE.mkdir(parents=True, exist_ok=True)
    f = STATE / f"{sid}.json"
    try:
        prev = json.loads(f.read_text()).get("level", 0)
    except (OSError, ValueError):
        prev = 0
    if level <= prev:
        return
    f.write_text(json.dumps({"level": level, "ctx": ctx}))
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                             "additionalContext": message(ctx)}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
