# 動画作成までの実作業手順（HUMAN_RUNBOOK）

監修者を別途立てない運用（税理士監修なし）を前提とした、あなた自身の手作業フローです。
パイプラインが自動でやる工程は省略し、**人間が実際にキーを叩く / マイクに向かう / ボタンを押す箇所だけ** を時系列で並べています。

> 想定環境: macOS or Linux、Python 3.12、`uv`、DaVinci Resolve（無料版可）、USBマイク。

---

## 0. 一度だけやる初期セットアップ

**初めての方は先に [`QUICKSTART_MAC.md`](QUICKSTART_MAC.md) を実行してください。**
Homebrew / uv / リポジトリ取得 / `.env` / Anthropic API キーまで、ゼロからコピペで進められる手順を用意しています。
それが終わったら下記の任意項目だけ済ませて Step 1 に進んでください。

| ステップ | コマンド / 操作 | 目安 |
|---|---|---|
| 0-1 | （初回必須）`QUICKSTART_MAC.md` を §1〜§7 まで実行 | 30〜40 分 |
| 0-2 | `assets/bgm/library.json` のローカル BGM ライセンスを実購入実体に合わせて確認 | 5 分 |
| 0-3 | DaVinci Resolve をインストール（公式無料版）、`Preferences > General > Working Folders` を確認 | 10 分 |
| 0-4 | （任意）`config.toml` の `[long_form].target_duration_sec` などをチャンネル方針に合わせて編集 | 5 分 |

---

## 1. 動画 1 本ごとのフロー（90分以内 / 投稿前まで）

### Step 1: 自動生成を走らせる（あなたの作業: 1 コマンド）

```bash
uv run pipeline generate --topic "<今回扱いたいテーマ>"
# 例:
uv run pipeline generate --topic "インボイス経過措置の80%控除が2026年9月に終了"
```

- 出力: `projects/<YYYY-MM-DD>_<slug>/` の下に台本・音声・サムネ・字幕・タイムライン一式
- 所要: 20〜35 分（並列実行中はマシンを触らなくてOK）

トレンド自動選定で回したいときは:

```bash
uv run pipeline auto
```

### Step 2: コンプラレポートと事実精度を目視する（5〜10 分）

ファイル開いて、ブロックが立っていないかと、論点の方向性が許容範囲かを確認:

```bash
open projects/<slug>/compliance/final_report.md
open projects/<slug>/compliance/content_accuracy_review.md   # 存在すれば
open projects/<slug>/script/script.md
```

判断基準:

- `final_report.md` が `ブロッキング状態: ✅ なし` であること
- `hallucination` の severity が `block` でないこと
- 各 claim の出典URLを **ブラウザで実際に開いて該当記載があるか** スポット確認（最低3件）

このとき気になる文言や事実があれば、`script/script.json` を直接編集する。
編集したらレンダー再生成（後述 Step 7）か、CLI で再実行:

```bash
uv run pipeline run --project <YYYY-MM-DD>_<slug> --from factcheck
```

### Step 3: 録音用カンペを開いて自分の声パートを録る（20〜25 分）

```bash
open projects/<slug>/script/teleprompter.html
```

ブラウザに USER セグメントだけ並んだカンペが出ます。それを見ながら、各セグメントを USB マイクで録音。

- 録音先: `projects/<slug>/audio/user_segments/`
- 既に `seg_NNN_RECORD_ME.wav` というプレースホルダがあるはず。**同じファイル名で上書き** すれば差し替わります（リネーム不要の運用にしている場合）。
- 録音 SOP（マイク距離・収録レベル）は `assets/recording/template.html` に従う。

録音後、一応 Whisper を再走らせて字幕を更新:

```bash
uv run pipeline run --project <slug> --from subtitle
```

### Step 4: B-roll / サムネを選ぶ（10 分）

```bash
open projects/<slug>/visuals/broll/gallery.html
open projects/<slug>/visuals/thumbnails/
```

- B-roll: ギャラリーから採用カットを選び、`broll/candidates.json` の `accepted: true` を付ける（or UI でクリック）。
- サムネ: A/B/C の 3 案から 1 つ選ぶ。差し替えたい文字があれば Pillow 焼き込み画像を直接編集。

### Step 5: ショート候補を見る / 切り出す（5 分、任意）

```bash
open projects/<slug>/output/shorts/PICK_ME.md
```

採用したい区間をマークして:

```bash
uv run pipeline shorts --project <slug> --count 3
```

### Step 6: メタデータを最終確認（5 分）

```bash
open projects/<slug>/metadata/description.md
open projects/<slug>/metadata/metadata.json
```

- `chosen_title` を必要なら別案に差し替え（`title_candidates` から選ぶ）
- `description.md` の章タイムスタンプが録音後の実尺と合っているか確認（ずれてたら手で直す）
- 概要欄末尾の免責文（「本動画は一般的な情報提供であり、個別税務相談には該当しません」）が残っているか確認

### Step 7: プレビュー mp4 を生成して通しで観る（5 分）

```bash
bash projects/<slug>/render_preview.sh
open projects/<slug>/output/preview.mp4
```

通しで観て、明らかな違和感（誤読、無音、テロップ位置）があればここで把握する。

### Step 8: DaVinci Resolve で最終調整（10〜20 分）

`projects/<slug>/timeline/project.otio`（または `.fcpxml`、CapCut なら `.edl`）を開く。

- 不要部分のカット、テロップの位置調整、サムネ用静止画書き出し
- 完了したら `File > Deliver` で本番 mp4 を書き出し（推奨: H.264 / 8-12Mbps / 1080p）

### Step 9: YouTube Studio で投稿（10 分）

`compliance/final_report.md` の YouTube Studio チェックリストを **1個ずつチェックしながら** 進める:

- [ ] 動画アップロード
- [ ] タイトル: `metadata.json` の `chosen_title` を貼り付け
- [ ] 概要欄: `metadata/description.md` の中身を全文貼り付け
- [ ] タグ: `metadata/tags.txt` を貼り付け
- [ ] サムネイル: Step 4 で選んだ画像をアップロード
- [ ] **『合成・改変メディア』の AI 使用開示にチェック**（必須）
- [ ] 視聴者層: 「子ども向けではない」を選択
- [ ] 字幕: `subtitles/ja.srt` をアップロード
- [ ] **固定コメント**: 「個別の税務相談はお受けできません。具体的な適用判断は税理士にご相談ください」を準備しておき、公開直後に固定する

### Step 10: 公開後の運用（毎回 5 分以内）

- コメント欄に個別の税務相談が来ても **回答しない**（税理士相談を案内する固定コメントへ誘導）。
- 公開後 48 時間以内に YouTube Studio の `推奨アクション` と `ポリシー` 通知を確認。

---

## トラブルシューティング（よくある引っかかり）

| 症状 | 対処 |
|---|---|
| `factcheck` で URL が `高 severity` で落ちる | NTA など政府系なら `urlcheck.py` の `_TRUSTED_GOV_DOMAINS` に追加。それ以外は別の一次ソースに差し替え |
| `inauthentic` で `warn` | USER セグメントの録音尺を足す。`script.json` の `user` 行の `duration_est_sec` 合計を 60s 以上 & 全体の 10% 以上に |
| 字幕の数字が誤変換（80% → 80パーセント など） | `assets/dictionary/tax_terms.json` に正規化ルールを追加して `--from subtitle` 再実行 |
| プレビューの音量バランス | DaVinci Resolve の Fairlight で AI 音声 -3dB / USER 0dB / BGM -22dB を目安に |
| サムネの文字が読みにくい | Pillow 焼き込みのフォントを `assets/fonts/NotoSansJP-Black.otf` に切替、文字サイズ 96pt 以上 |

---

## 1 本あたりの実作業時間サマリー

| ステップ | 内容 | 所要 |
|---|---|---|
| 1 | 自動生成コマンド投入 | 1 分（あとは放置） |
| 2 | コンプラ・事実精度の目視 | 5〜10 分 |
| 3 | 録音 | 20〜25 分 |
| 4 | B-roll / サムネ選択 | 10 分 |
| 5 | ショート切り出し（任意） | 5 分 |
| 6 | メタデータ確認 | 5 分 |
| 7 | プレビュー視聴 | 5 分 |
| 8 | DaVinci 最終調整 + 書き出し | 10〜20 分 |
| 9 | YouTube Studio 投稿 | 10 分 |
| **合計** | | **70〜90 分** |

放置時間（自動生成・レンダー）を除けば実作業は約 60 分です。
