# QUICKSTART for macOS — ゼロから最初のコマンド投入まで

「Terminal は開いたことあるけどそんなに自信はない」「uv って何？」「`.env` ってどこに作る？」レベルから、
`uv run pipeline generate` の1コマンドが通るところまで、コピペで進める完全手順です。

> 所要時間: 初回 30〜40 分（API キー取得のメール認証待ち含む）
> 想定: MacBook Pro（Apple Silicon / Intel どちらでも）

---

## 0. Terminal を開く

`⌘ + Space` で Spotlight を開いて `Terminal` と打って Enter。

出てくる黒い（または白い）ウィンドウ＝Terminal です。以下、`$` で始まる行は **`$` を含めず** Terminal に貼り付けて Enter してください。

---

## 1. Homebrew を入れる（既に入っていればスキップ）

確認:

```
$ brew --version
```

`Homebrew x.x.x` と出たら入っています → §2 へ。
`command not found` ならインストール:

```
$ /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

途中で macOS のパスワードを聞かれます（タイプしても画面に表示されないのは仕様）。
インストール完了後、画面の最後に "Next steps:" として2行ほどの `eval ...` コマンドが表示されるので、それを **そのまま貼り付けて実行** してください（PATH 設定）。

---

## 2. uv を入れる（Python の高速パッケージマネージャ）

```
$ brew install uv
$ uv --version
```

`uv 0.x.x` と出れば OK。

---

## 3. リポジトリを取得する

ホームディレクトリに `dougasakusei` フォルダを作るのが楽です:

```
$ cd ~
$ git clone https://github.com/Yukinori1018/dougasakusei.git
$ cd dougasakusei
```

> もしすでに別の場所にクローン済み・ZIP で受け取って手元にある場合は、`cd <そのフォルダのパス>` で移動すれば OK。

---

## 4. Python 仮想環境を作って依存パッケージを入れる

```
$ uv venv
$ uv pip install -e ".[audio]"
```

- 初回は数分かかります。Apple Silicon でも Intel でも動きます。
- 最後の行が `Installed XXX packages` のような表示で終われば成功。
- エラーが出る場合の代表例:
  - `error: command 'cc' failed` → `xcode-select --install` を実行してから再度 §4。
  - ネットワークタイムアウト → もう一度同じコマンドを叩く。

---

## 5. ANTHROPIC_API_KEY を取得する

1. ブラウザで <https://console.anthropic.com/> を開く（メアド／Google アカウントで登録）
2. 左メニュー `Settings → API keys`
3. `Create Key` → 名前は何でも OK（例: `dougasakusei`）
4. 表示された `sk-ant-...` の文字列を **コピー**（画面を閉じると二度と表示されません）
5. 課金設定（Settings → Billing）でクレジットカードを登録し $10 ほど入金。動画 1 本あたり $4 程度なので $10 で 2 本は試せます。

> **他のキー（ElevenLabs / Pexels / FAL など）は今は不要**。空欄のまま進めて構いません（パイプラインが自動でフォールバックします）。

---

## 6. `.env` ファイルを作る

Terminal で（`cd ~/dougasakusei` の中にいる前提）:

```
$ cp .env.example .env
$ open -e .env
```

`open -e` で TextEdit が開きます。`ANTHROPIC_API_KEY=` の行を:

```
ANTHROPIC_API_KEY=sk-ant-ここに§5でコピーしたキーを貼る
```

に編集 → `⌘ + S` で保存 → ウィンドウを閉じる。

> 他の行はすべて空でも構いません。`PIPELINE_MODE=auto` だけ最後に残っていればOK。

---

## 7. 動作確認（mock モードで API を消費せず空走らせ）

```
$ PIPELINE_MODE=mock uv run pipeline generate --topic "テスト動画"
```

- ログがガーッと流れて、最後に `projects/<日付>_test/` のような出力が出れば「インストール成功」のサイン。
- `command not found: pipeline` と出た場合は `uv run --` を付け直すか `uv pip install -e .` を再実行。

---

## 8. 本番モードで1本生成

```
$ uv run pipeline generate --topic "インボイス経過措置の80%控除が2026年9月に終了"
```

- 20〜35 分ほど自動で動きます（モニタしなくて OK、別の作業をどうぞ）。
- 終わると `projects/<YYYY-MM-DD>_invoice-...` フォルダができています。

ここまで来たら **HUMAN_RUNBOOK.md の Step 2 から** 続行してください。

---

## ここからの参照ドキュメント

| やりたいこと | ドキュメント |
|---|---|
| 1 本の動画を投稿するまでの全工程 | `HUMAN_RUNBOOK.md` |
| 設定の細かい調整（録音方針、モデル選定など） | `config.toml` のコメント |
| API キーの追加（ElevenLabs等で音声品質を上げる、Pexels で B-roll を充実させる、など） | `README.md` の「API キー取得方法」表 |

---

## トラブルが起きたら

下記をそのままコピーして相談に使ってください:

```
$ uv --version
$ python3 --version
$ pwd
$ ls -la .env pyproject.toml
$ uv run pipeline --help
```

これらの出力を添付してくれれば、私（or 自分）が状態を把握しやすいです。
