"""過去の会話ログを「別の autoCompactWindow で動いていたら」として再計算する。

各会話の呼び出しごとの文脈の増分を、そのまま新しい条件で積み直す。
  - 文脈が閾値(窓 - 予備 33k)を超えたら compact する。compact 後の文脈は「初回文脈 + 要約」になる
  - compact 1 回の費用 = その時点の文脈を読む(cache read) + 要約を書く(output) + 新しい文脈の cache write
  - 実ログで compact が起きた所(文脈が大きく減った所)は、シミュレーション側も実ログの値以下に下げる
  - compact 後に必要なファイルを読み直す分を reread トークンとして足す(悲観シナリオ用)
  - 書き込み量は実ログの値を使うが、シミュレーション側の文脈を超えないようにする
    (cache が切れた所で、実ログの 900k をそのまま書き直したと数えないため)
  - clear_on_ttl > 0 のとき、cache が切れた後の依頼(ttl_guard hook が止める場面)のうち、その割合で
    ユーザーが /clear して新しい会話で始めたとして、文脈を初回文脈まで戻す
画像縮小や /handoff による会話の分割は含めない。そのぶん節約を少なめに見積もる。
品質(compact で失われる情報)はこの計算では測れない。
"""
from __future__ import annotations

from dataclasses import dataclass

from .cache import classify
from .transcripts import WEIGHTS, Session

BUFFER = 33_000  # Claude Code の autocompact buffer(/context の表示による)


@dataclass
class Scenario:
    name: str
    window: int | None  # None = 実ログのまま(比較の基準)
    summary: int = 6_000  # compact 後に残る要約の大きさ(実ログの中央値)
    reread: int = 0  # compact 後に読み直す量
    clear_on_ttl: float = 0.0  # cache 切れの後で /clear する割合(0〜1)
    ttl_min: int = 100_000  # ttl_guard が止める文脈の下限
    clear_reread: int = 30_000  # /clear した新しい会話で、必要なファイルを読み直す量(悲観側に置く)
    # 比較用: cache が切れる直前(55 分放置)に compact しておく方式(sparkjoy プラグインと同じ考え方)。
    # 戻ってこなかった会話でも compact の費用がかかるので、会話の最後にもその費用を足す
    idle_compact: bool = False


@dataclass
class Result:
    weighted: float = 0.0
    cache_read: int = 0
    compactions: int = 0
    clears: int = 0
    ttl_events: int = 0
    ctx_sum: int = 0
    calls: int = 0


def simulate(sessions: list[Session], sc: Scenario) -> Result:
    r = Result()
    acc = 0.0  # clear_on_ttl の割合を、会話をまたいで決定的に配るための累積
    for s in sessions:
        cs = s.calls
        if not cs:
            continue
        kinds = classify(s)
        base = cs[0].context
        ctx = base
        prev_real = base
        for i, c in enumerate(cs):
            delta = 0
            if i:
                delta = c.context - prev_real
                if delta >= 0:
                    ctx += delta
                else:
                    # 実ログで compact や消去が起きた。シミュレーション側も実際の値を超えないようにする
                    ctx = min(ctx, c.context)
                prev_real = c.context
            write = c.cache_write + c.input
            if kinds[i] == "ttl":
                # cache が切れた。書き直し量は実ログの値(下の min で文脈以下に抑える)
                if sc.idle_compact and ctx - delta >= sc.ttl_min:
                    # 放置中に compact 済み: 古い文脈を cache から読んで要約を書き、要約入りの文脈から再開する
                    r.ttl_events += 1
                    r.compactions += 1
                    r.weighted += (ctx - delta) * WEIGHTS["cache_read"] + sc.summary * WEIGHTS["output"]
                    ctx = base + sc.summary + sc.reread + max(0, delta)
                    write = ctx
                elif ctx - delta >= sc.ttl_min:
                    r.ttl_events += 1
                    acc += sc.clear_on_ttl
                    if acc >= 1 - 1e-9:
                        # 新しい会話: 固定分と今回の依頼だけから始める
                        acc -= 1
                        r.clears += 1
                        ctx = base + max(0, delta) + sc.clear_reread
                        write = ctx
            write = min(write, ctx)
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
        if sc.idle_compact and ctx >= sc.ttl_min:
            # 最後の応答のあと誰も戻らなくても、55 分後の compact は走る
            r.weighted += ctx * WEIGHTS["cache_read"] + sc.summary * WEIGHTS["output"]
            r.compactions += 1
    return r


def ttl_scenarios(window: int | None, shares: list[float]) -> list[Scenario]:
    w = f"{window // 1000}k 窓" if window else "窓そのまま"
    return ([Scenario(f"{w}・cache 切れ後に {p:.0%} を /clear", window, clear_on_ttl=p) for p in shares]
            + [Scenario(f"{w}・比較: 55 分放置で compact", window, idle_compact=True),
               Scenario(f"{w}・比較: 55 分放置で compact(悲観)", window, idle_compact=True, summary=16_000, reread=30_000)])


def scenarios(window: int) -> list[Scenario]:
    return [
        Scenario("実際(導入前)", None),
        Scenario(f"{window // 1000}k 窓・標準", window, summary=6_000),
        Scenario(f"{window // 1000}k 窓・悲観(要約 16k+読み直し 30k)", window, summary=16_000, reread=30_000),
    ]
