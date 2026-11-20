# tokenguard

Claude Code のトークン消費を、品質を落とさずに減らすための道具一式。
計測 → 文脈の上限 → cache 切れの書き直しの防止 → 区切りの促し → 引き継ぎ → 画像の縮小、の順に効く。依存は Python 標準ライブラリだけ。

## まず自分の環境で測る

効く対策は使い方で変わる。導入する前に、自分の会話ログ(`~/.claude/projects/`)で測る。
ログは手元で読むだけで、外部には送らない。

```bash
git clone https://github.com/fatcorn753/tokenguard && cd tokenguard
bin/tokenguard report      # 費用の内訳・cache write の原因・重い会話・重いツール・診断
bin/tokenguard simulate    # 窓を 200k / 300k にした場合の見積もり
bin/tokenguard simulate --window 300000 --clear-on-ttl 0.25 0.5 1   # ttl_guard の見積もり
```

`report` の診断で「cache read が費用の 4 割超」と出たら、この道具の効果が大きい。

## 根拠(作者の環境。2026-11-19 の計測、直近 14 日・278 会話)

| 項目 | 値 |
|---|---|
| 費用の内訳 | cache read 64% / cache write 26% / output 10% |
| 1 回あたりの文脈 | 中央値 273k、p90 632k(1M 窓を上限まで使っていた) |
| 文脈 200k 超の呼び出し | 費用の約 8 割 |
| 500 回超の会話 | 13 件で費用の 34% |
| 文脈に入った画像 | 2739 枚 |

費用の大半は「長い会話の文脈を、呼び出しのたびに読み直すこと」にかかる。
返答を短くする工夫(output 削減)は、全体の 10% にしか効かない。

## 効果の見積もり(`tokenguard simulate`)

過去の会話ログを、autoCompactWindow だけ変えて再計算した結果(2026-11-21 に再計算)。
compact 後の要約の大きさ(中央値 6k、p75 16k)は、実ログで compact が起きた 38 回から測った。

| 条件 | 14 日分 | 直近 3 日分 |
|---|---|---|
| 200k 窓・標準 | -45% | -27% |
| 200k 窓・悲観(要約 16k、compact ごとに 30k 読み直し) | -24% | **+23%** |
| 300k 窓・標準 | -39% | -22% |
| 300k 窓・悲観 | -34% | -18% |

- 直近 3 日分は、ほぼ 300k 窓を導入した後のログ。その「実際」との差なので、窓の効果は小さく出る
- 2026-11-21 の修正で、14 日分の節約が以前の見積もり(300k 標準 -30%)より大きくなった。
  cache が切れた所で、実ログの書き直し量(最大 960k)を、窓で小さくなった文脈にもそのまま数えていたため。
  いまは書き直し量をシミュレーション側の文脈で頭打ちにしている

- 数字は導入前(1M 窓)との差。入力トークン換算の重み付き消費で比べた。比率は cache read 0.1、
  cache write 2(Claude Code の cache は 1 時間 TTL)、output 5
- compact は文脈を丸ごと書き直す(cache write)ので、窓が小さすぎると compact が増えて逆効果になる。
  200k は悲観シナリオで消費が増えることがある。300k はどの条件でも減った。そのため既定は 300k にしている
- 画像の縮小と /handoff による会話の分割は計算に含めていない。その分、節約は少なめに出る

## 実験(品質と費用)

### 記憶テスト(`tokenguard bench`)

決定事項 11 個を会話の前半と途中で伝え、約 5 万トークンの資料 8 つで文脈を 43 万トークン近くまで育ててから、
11 問を答えさせた。Sonnet 5.5、各条件 2 回。

| 窓 | 正答 | compact 回数 | 費用(USD) |
|---|---|---|---|
| 1M | 22/22 | 0 | 1.91 |
| 300k | 22/22 | 各 1 回 | 2.03(+6%) |
| 200k | 22/22 | 各 3 回 | 2.27(+19%) |

- この範囲では、compact で決定事項を忘れることはなかった。ただし試行数は少ない。
  旧版の試験(資料を Read で読ませた版)では、200k で 1 問(却下理由)を落とした回が 1 回あった
- この試験では費用が増えた。1 通ごとに 5 万トークンずつ文脈が増え、呼び出しが 10 回しかないので、
  読み直しの節約より compact の書き直しの費用が上回るため。実際の会話は 1 回あたりの増分が小さく呼び出しが多いので、
  上のシミュレーションの方が実態に近い

### 過去の作業の再現(`bench/replay.py`)

`delegate` リポジトリの機能追加の commit を、その直前から完成形のテストを渡してやり直させた。
1M / 300k / 200k のどれも 38/38 のテストが通った。ただし文脈は最大 10 万トークンで、compact は起きなかった。
普通の長さの作業は、窓の大きさの影響を受けない。

### 導入後の実測(2026-11-20、1 会話・313 回の呼び出し)

1 回あたりの重み付き消費が導入前の直近 3 日と比べて約 30% 減り、文脈は 267k で頭打ちになった。

## cache 切れの書き直しを防ぐ(`hooks/ttl_guard.py`)

### 何が起きているか

Claude Code は会話の文脈を prompt cache に載せ、次の呼び出しで安く読み直す(cache read、0.1 倍)。
cache には有効期限(TTL)があり、Claude Code の会話では 1 時間。最後の応答から 1 時間以上空けて戻ると cache は消えていて、
次の呼び出しは文脈をまるごと書き直す(1 時間 TTL の cache write、2 倍)。同じ文脈を読むだけの場合の 20 倍の単価になる。

`tokenguard report` の「cache write の原因」で、作者のログを分類した結果:

| 原因 | 14 日分 | 直近 3 日分(300k 窓の導入後) |
|---|---|---|
| cache 切れ(TTL 超過)の書き直し | **450 回・費用の 15.6%** | 42 回・6.1% |
| TTL 内の書き直し(原因不明の cache 落ち) | 96 回・2.0% | 15 回・0.8% |
| 会話の開始 | 0.9% | 1.6% |
| compact 直後 | 0.4% | 1.3% |
| 増分(正常) | 7.0% | 10.7% |

cache 切れの書き直しは、cache write(費用の 26%)の 6 割を占めていた。
戻ってきた依頼 40 件を抜き出して読むと、同じプロジェクトの続きが多いが、
「招待リンクをくれ」「この講座はどう？」のような、40 万トークンの文脈が要らない質問も混ざっていた。

### 仕組み

`UserPromptSubmit` hook で、次の 3 つがそろったときだけ、送信を一度止める。
- 直近の応答から TTL(1 時間。会話ログの `cache_creation` が 5 分 TTL だけなら 5 分)が過ぎている
- 直近の文脈が 100k 以上(`TOKENGUARD_TTL_MIN`)
- 依頼が自動の差し込み(`<task-notification>` など)やスラッシュコマンドではない

止めたときは、ユーザーに次のように表示する(送った文も一緒に表示されるので、打ち直さずに済む)。

```
[tokenguard] 最後の応答から 3.2 時間空き、prompt cache が切れています。このまま送ると、文脈 250k をまるごと書き直します(普段の 1 往復の約 20 倍の費用)。
- 前の作業と別件なら: /clear してから送るか、新しい会話で始める
- 続きなら: 同じ文をもう一度送る(次は止めません)
```

続きなら同じ文を送り直せばそのまま通る。止めるのは同じ cache 切れにつき 1 回だけ。
`/clear` の後は、前の会話の文脈を読み直さないので、書き直しもその後の読み直しも発生しない。

### 効果の見積もり(`tokenguard simulate --clear-on-ttl`)

300k 窓を前提に、止めた場面のうち何割でユーザーが `/clear` したかを変えて再計算した。
`/clear` した新しい会話では、必要なファイルを 30k 読み直すとして悲観側に置いた。

| 条件(300k 窓) | 14 日分 | 直近 3 日分 |
|---|---|---|
| ttl_guard なし | 1.11B(基準) | 154.5M(基準) |
| 止めた場面の 25% で /clear | **-2.8%** | **-1.1%** |
| 50% で /clear | -5.6% | -2.3% |
| 100% で /clear | -7.7% | -2.6% |
| 比較: 55 分放置で自動 compact(標準) | -9.8% | -3.6% |
| 比較: 55 分放置で自動 compact(悲観) | +5.5% | +10.1% |

- 14 日分と直近 3 日分の差は、300k 窓の導入後は文脈が小さく、書き直し 1 回の費用が下がったため
- 比較の「55 分放置で自動 compact」は、cache が切れる前に compact しておく方式
  ([sparkjoy](https://github.com/max-sixty/sparkjoy) と同じ考え方)。戻ってこない会話でも compact の費用がかかり、
  要約が大きい悲観シナリオでは費用が増える。hook では放置中に動けない(プラグイン API が必要)ことも合わせて、見送った。
  ttl_guard は、ユーザーが「別件」と判断したときしか文脈を捨てないので、費用は増えない
- 効果は小さめだが、副作用は「1 時間以上空けて長い会話へ戻ったときに、1 回送り直す手間」だけ

### 根拠(引用は `research/verify.py` で出典の本文にあることを確かめた)

- 1 時間 TTL の書き込みは 2 倍、読み出しは 0.1 倍:
  "Cache write tokens with a 1-hour TTL are 2 times the base input tokens price."
  ([Anthropic: Prompt caching](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching))
- 放置後の最初の呼び出しは文脈全体を書き直す。TTL は hook から読めない:
  [anthropics/claude-code#110535](https://github.com/anthropics/claude-code/issues/110535)
- 別の利用者の分析でも、cache write の大半が少数の書き直し(TTL 切れなど)に集中:
  "68% of all cache-write tokens (14.8M of 21.7M) come from 36 events"
  ([anthropics/claude-code#94177](https://github.com/anthropics/claude-code/issues/94177))

文献調査の全体(78 件中、引用を確かめられた 67 件)と、採用・見送りの判断と理由は [research/](research/README.md) にある。

## 構成

| 部品 | 効き方 |
|---|---|
| `tokenguard report / trend / simulate / bench / session` | 内訳・重い会話・重いツールを出す。過去ログを別の窓で再計算する。記憶テストを走らせる |
| `autoCompactWindow: 300000` | 1M 窓を 300k 窓として扱い、約 267k で compact する。最も効く |
| `hooks/ttl_guard.py`(UserPromptSubmit) | prompt cache が切れた長い会話へ戻ったとき、送信を一度止め、別件なら /clear するよう知らせる |
| `hooks/ctx_guard.py`(UserPromptSubmit) | 文脈が 120k/180k/250k/350k を超えたら、区切りを提案するよう Claude に一度だけ伝える |
| `skills/handoff`(`/handoff`) | 作業状態をファイルに書き出し、小さな文脈の新しい会話で続ける。compact より必要な情報を選んで残せる |
| `hooks/img_shrink.py`(PreToolUse: Read) | 長辺 1280px 超の画像を縮小した複製に差し替える。10 分以内に同じ画像をもう一度 Read すると原寸で通す |

## 導入と解除

必要なもの: `autoCompactWindow` 設定に対応した Claude Code(動作確認は 2.1.319)、Python 3.10 以降。
画像の縮小は macOS の `sips` を使う。macOS 以外では何もせず、原寸のまま読ませる。

```bash
python3 install.py            # settings.json を .bak に残してから書き換える
python3 install.py --window 200000   # より攻める場合
python3 install.py --uninstall
```

既存の hook はそのまま残る。何度実行しても同じ状態になる。解除すると、autoCompactWindow は導入前の値に戻る。
導入すると、次のものが入る:
- `~/.claude/settings.json` の `autoCompactWindow` と、3 つの hook
- `~/.claude/skills/handoff`(このリポジトリへのシンボリックリンク)
- `~/.local/bin/tokenguard`(同上)

導入後に始めた会話から効く。引き継ぎファイルは `~/.claude/handoffs/` に書かれる。

## 注意

- 窓を小さくすると compact が増え、長い作業の途中の細かい記憶は薄れる。区切りでは `/handoff` を使う
- 文脈を区切るよう促す注入文は、段階ごとに 1 回、80 字ほど。毎回は入れない
- ttl_guard は送信を止める。自動で動かしている会話(`claude -p --resume` を 1 時間以上空けて続ける等)では、
  依頼が止まって進まなくなる。そうした用途では `TOKENGUARD_TTL_GUARD=off` を付ける
- cache の TTL はアカウントと設定で決まり、Claude Code から hook へは渡されない
  ([anthropics/claude-code#110535](https://github.com/anthropics/claude-code/issues/110535))。
  ttl_guard は会話ログの `cache_creation` の内訳から推定している
- `--fork-session` で分岐した会話は、新しい会話ログから始まるので ttl_guard は止めない
- 料金の比率は API 単価(cache read 0.1 倍・cache write 2 倍・output 5 倍)に基づく。
  サブスクリプションの使用量の上限が、同じ比率で数えられているかは公開されていない

## 試験

```bash
python3 -m unittest discover tests
```

実機での確認方法:
- 画像の縮小: `claude -p` で大きな PNG を Read させ、会話ログに残った画像の寸法を見る(1280px になっていること)
- ttl_guard: 1 時間以上前に終わった会話を `claude -p --resume <id> --settings '<ttl_guard だけの hooks>'` で再開する。
  1 回目は `UserPromptSubmit operation blocked by hook` と理由が返り、使用量は 0。同じ文の 2 回目は通る(2026-11-21 確認)
- 窓: `claude -p "/context" --settings '{"autoCompactWindow":200000}'` で、上限の表示が 200k になること

## 調整用の環境変数

- `TOKENGUARD_CTX_STEPS`: 促す段階(既定 `120000,180000,250000,350000`)
- `TOKENGUARD_IMG_EDGE`: 縮小後の長辺(既定 1280)
- `TOKENGUARD_TTL_GUARD`: `off` で ttl_guard を無効にする
- `TOKENGUARD_TTL_MIN`: ttl_guard が止める文脈の下限(既定 100000)

## ライセンス

MIT
