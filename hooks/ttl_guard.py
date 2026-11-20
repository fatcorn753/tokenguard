#!/usr/bin/env python3
"""UserPromptSubmit hook: prompt cache が切れた長い会話へ戻ってきたとき、送信を一度だけ止める。

Claude Code の prompt cache は 1 時間 TTL。最後の応答から 1 時間以上空くと cache が消え、
次の呼び出しは文脈をまるごと書き直す(cache write、単価は入力の 2 倍、cache read の 20 倍)。
作者の 14 日分のログでは、この書き直しが費用の 15.6% を占めた。
戻ってきた依頼が前の作業と別件なら、/clear か新しい会話で始めると書き直しを丸ごと避けられる。
続きなら、同じ文をもう一度送ればそのまま通す(同じ cache 切れでは 2 回目以降は止めない)。

自動の差し込み(<task-notification> など "<" で始まるもの)とスラッシュコマンドは止めない。
TOKENGUARD_TTL_GUARD=off で無効、TOKENGUARD_TTL_MIN で止める文脈の下限(既定 100000)を変えられる。
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tokenguard.cache import epoch  # noqa: E402
from tokenguard.transcripts import last_usage  # noqa: E402

STATE = Path(os.environ.get("TOKENGUARD_STATE", Path.home() / ".cache/tokenguard/ctx"))
MIN_CTX = int(os.environ.get("TOKENGUARD_TTL_MIN", "100000"))
# TTL ちょうどで切れるとは限らないので、少し手前から止める
MARGIN = 60


def reason(ctx: int, gap: float) -> str:
    k = ctx // 1000
    h = gap / 3600
    when = f"{h:.1f} 時間" if h >= 1 else f"{gap / 60:.0f} 分"
    return (f"[tokenguard] 最後の応答から {when}空き、prompt cache が切れています。"
            f"このまま送ると、文脈 {k}k をまるごと書き直します(普段の 1 往復の約 20 倍の費用)。\n"
            "- 前の作業と別件なら: /clear してから送るか、新しい会話で始める\n"
            "- 続きなら: 同じ文をもう一度送る(次は止めません)")


def main() -> None:
    if os.environ.get("TOKENGUARD_TTL_GUARD", "on").lower() in ("off", "0", "false"):
        return
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    prompt = (data.get("prompt") or "").lstrip()
    tp, sid = data.get("transcript_path"), data.get("session_id", "x")
    # 自動の差し込みは "<タグ" で始まる。ユーザーの貼り付け(<pasted_content)は止める対象に含める
    auto = prompt.startswith("<") and not prompt.startswith("<pasted_content")
    if not tp or auto or prompt.startswith("/"):
        return
    last = last_usage(tp)
    if last.context < MIN_CTX or not last.ts:
        return
    t = epoch(last.ts)
    gap = time.time() - t
    if not t or gap < last.ttl - MARGIN:
        return
    STATE.mkdir(parents=True, exist_ok=True)
    f = STATE / f"{sid}.ttl"
    try:
        if f.read_text() == last.ts:
            return  # この cache 切れでは一度止めた。2 回目は通す
    except OSError:
        pass
    f.write_text(last.ts)
    print(json.dumps({"decision": "block", "reason": reason(last.context, gap)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
