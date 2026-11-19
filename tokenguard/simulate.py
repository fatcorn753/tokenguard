"""過去の会話ログを「別の autoCompactWindow で動いていたら」として再計算する。

各会話の呼び出しごとの文脈の増分を、そのまま新しい条件で積み直す。
  - 文脈が閾値(窓 - 予備 33k)を超えたら compact する。compact 後の文脈は「初回文脈 + 要約」になる
  - compact 1 回の費用 = その時点の文脈を読む(cache read) + 要約を書く(output) + 新しい文脈の cache write
  - 実ログで compact が起きた所(文脈が大きく減った所)は、シミュレーション側も実ログの値以下に下げる
  - compact 後に必要なファイルを読み直す分を reread トークンとして足す(悲観シナリオ用)
画像縮小や /handoff による会話の分割は含めない。そのぶん節約を少なめに見積もる。
品質(compact で失われる情報)はこの計算では測れない。
"""
from __future__ import annotations

from dataclasses import dataclass

from .transcripts import WEIGHTS, Session

BUFFER = 33_000  # Claude Code の autocompact buffer(/context の表示による)


@dataclass
class Scenario:
    name: str
    window: int | None  # None = 実ログのまま(比較の基準)
    summary: int = 6_000  # compact 後に残る要約の大きさ(実ログの中央値)
    reread: int = 0  # compact 後に読み直す量


@dataclass
class Result:
    weighted: float = 0.0
    cache_read: int = 0
    compactions: int = 0
    ctx_sum: int = 0
    calls: int = 0


def simulate(sessions: list[Session], sc: Scenario) -> Result:
    r = Result()
    for s in sessions:
        cs = s.calls
        if not cs:
            continue
        base = cs[0].context
        ctx = base
        prev_real = base
        for i, c in enumerate(cs):
            if i:
                delta = c.context - prev_real
                if delta >= 0:
                    ctx += delta
                else:
                    # 実ログで compact や消去が起きた。シミュレーション側も実際の値を超えないようにする
                    ctx = min(ctx, c.context)
                prev_real = c.context
            write = c.cache_write + c.input
            if sc.window and ctx > sc.window - BUFFER:
                # compact: 今の文脈を読んで要約を書き、要約入りの新しい文脈を cache write する
                r.weighted += ctx * WEIGHTS["cache_read"] + sc.summary * WEIGHTS["output"]
                r.cache_read += ctx
                r.compactions += 1
                ctx = base + sc.summary + sc.reread
                write = ctx
            read = max(0, ctx - write)
            r.weighted += write * WEIGHTS["cache_write"] + read * WEIGHTS["cache_read"] + c.output * WEIGHTS["output"]
            r.cache_read += read
            r.ctx_sum += ctx
            r.calls += 1
    return r


def scenarios(window: int) -> list[Scenario]:
    return [
        Scenario("実際(導入前)", None),
        Scenario(f"{window // 1000}k 窓・標準", window, summary=6_000),
        Scenario(f"{window // 1000}k 窓・悲観(要約 16k+読み直し 30k)", window, summary=16_000, reread=30_000),
    ]
