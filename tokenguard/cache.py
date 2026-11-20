"""cache write(費用の約 1/4)が何で起きたかを、呼び出しごとに分類する。

Claude Code は会話の文脈を prompt cache に載せ、次の呼び出しで読み直す(cache read、0.1 倍)。
cache が使えないと、文脈をまるごと書き直す(cache write、1 時間 TTL では 2 倍)。
書き直しの原因を次の 5 つに分ける。
  start        会話の最初の呼び出し(システムプロンプトなどの固定分)
  ttl          前の呼び出しから TTL(既定 1 時間)を超えて間が空き、cache が切れた
  compact      compact などで文脈が縮んだ直後
  break        TTL 内なのに文脈の大半を書き直した(モデル切り替え・ツール定義の変化・不具合など)
  incremental  新しく増えた分だけを書いた(正常)
"""
from __future__ import annotations

import collections
import datetime as dt

from .transcripts import WEIGHTS, Call, Session

KINDS = ("start", "ttl", "compact", "break", "incremental")
BIG_SHARE = 0.5  # 文脈のこの割合以上を書いたら「書き直し」とみなす
BIG_MIN = 20_000  # 小さな文脈の書き直しは無視する
SHRINK = 0.7  # 前の呼び出しよりこの比率未満に縮んだら compact とみなす


def epoch(ts: str) -> float:
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def ttl_of(c: Call) -> int:
    # 5 分 TTL の書き込みしかない呼び出し(サブエージェントなど)は 300 秒、それ以外は 1 時間
    return 300 if c.write_5m and c.write_5m >= c.cache_write else 3600


def classify(s: Session) -> list[str]:
    out = []
    prev: Call | None = None
    for c in s.calls:
        if prev is None:
            k = "start"
        else:
            gap = epoch(c.ts) - epoch(prev.ts)
            big = c.cache_write >= BIG_SHARE * c.context and c.cache_write >= BIG_MIN
            if c.context < prev.context * SHRINK:
                k = "compact"
            elif big and gap > ttl_of(prev):
                k = "ttl"
            elif big:
                k = "break"
            else:
                k = "incremental"
        out.append(k)
        prev = c
    return out


def breakdown(sessions: list[Session]) -> dict[str, list[float]]:
    """原因ごとの [回数, cache write トークン, 重み付き費用]。"""
    agg: dict[str, list[float]] = collections.OrderedDict((k, [0, 0, 0.0]) for k in KINDS)
    for s in sessions:
        for c, k in zip(s.calls, classify(s)):
            a = agg[k]
            a[0] += 1
            a[1] += c.cache_write
            a[2] += c.cache_write * WEIGHTS["cache_write"]
    return agg
