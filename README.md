# tokenguard

Claude Code のトークン消費を、品質を落とさずに減らすための道具一式。
計測 → 文脈の上限 → 区切りの促し → 引き継ぎ → 画像の縮小、の順に効く。

## 根拠(2026-11-19 の計測。直近 14 日・278 会話)

| 項目 | 値 |
|---|---|
| 費用の内訳 | cache read 71% / cache write 18% / output 11% |
| 1 回あたりの文脈 | 中央値 281k、p90 636k(1M 窓を上限まで使っていた) |
| 文脈 200k 超の呼び出し | 費用の 83% |
| 500 回超の会話 | 13 件で費用の 34% |
| 文脈に入った画像 | 2739 枚 |

費用の大半は「長い会話の文脈を、呼び出しのたびに読み直すこと」にかかる。
返答を短くする工夫(output 削減)は、全体の 11% にしか効かない。

## 構成

| 部品 | 効き方 |
|---|---|
| `tokenguard report / trend / session` | 内訳・重い会話・重いツールを出す。対策の前後比較に使う |
| `autoCompactWindow: 200000` | 1M 窓を 200k 窓として扱い、約 167k で compact する。最も効く |
| `hooks/ctx_guard.py`(UserPromptSubmit) | 文脈が 120k/180k/250k/350k を超えたら、区切りを提案するよう Claude に一度だけ伝える |
| `skills/handoff`(`/handoff`) | 作業状態をファイルに書き出し、小さな文脈の新しい会話で続ける。compact より必要な情報を選んで残せる |
| `hooks/img_shrink.py`(PreToolUse: Read) | 長辺 1280px 超の画像を縮小した複製に差し替える。10 分以内に同じ画像をもう一度 Read すると原寸で通す |

## 導入と解除

```bash
python3 install.py            # settings.json を .bak に残してから書き換える
python3 install.py --window 300000
python3 install.py --uninstall
```

既存の hook はそのまま残る。何度実行しても同じ状態になる。解除すると、autoCompactWindow は導入前の値に戻る。

## 試験

```bash
python3 -m unittest discover tests
```

実機での確認方法:
- 画像の縮小: `claude -p` で大きな PNG を Read させ、会話ログに残った画像の寸法を見る(1280px になっていること)
- 窓: `claude -p "/context" --settings '{"autoCompactWindow":200000}'` で、上限の表示が 200k になること

## 調整用の環境変数

- `TOKENGUARD_CTX_STEPS`: 促す段階(既定 `120000,180000,250000,350000`)
- `TOKENGUARD_IMG_EDGE`: 縮小後の長辺(既定 1280)
