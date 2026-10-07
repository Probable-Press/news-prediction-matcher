# Probable Press

> 予測市場が示す確率と、ニュースが伝える事実。<br>
> その間にある「ギャップ」を、毎日分析するメディア。

🌐 **Live site**: https://news-prediction-matcher.pages.dev

---

## このプロジェクトは何か

Probable Press は、毎日のニュース（NHK / Yahoo Japan / BBC）と Polymarket の予測市場価格を機械的に突き合わせ、両者が乖離している点を「ギャップ」として記事化する自動メディアサイトです。

### コンセプト：「思想ではなく、お金が現実を選別する」

専門家の意見やメディアの論説には、必ず立場や利害が混ざります。一方で予測市場では、間違った確率に賭けると参加者がお金を失います。だから価格には「願望」が剥がれ、参加者の冷静な現実認識だけが残ります。

これは他の情報源にはない構造的な強みです。世界中の何千人ものトレーダーが知識を持ち寄り、その集合知が一つの「価格＝確率」に集約される。そこにニュースを並べることで、世界が少し違って見えてきます。

詳しくは [/about](https://news-prediction-matcher.pages.dev/about) ページを参照してください。

---

## アーキテクチャ

```
[GitHub Actions: fetch-data.yml]
   ├─ src/main.py          ─→ data/news-YYYY-MM-DD.json
   │   (NHK/Yahoo/BBC RSS + 本文スクレイプ)
   └─ src/fetch_markets.py ─→ data/markets-YYYY-MM-DD.json
       (Polymarket 出来高上位50市場)
   ↓ git commit & push to main
[Claude Code]
   ├─ 上記 JSON を読み込み
   ├─ ギャップ分析（±10ppフラグ）
   └─ articles/YYYY-MM-DD-{slug}.md を執筆
   ↓ git push to feature branch → PR → merge
[Cloudflare Pages]
   └─ Astro 静的サイトビルド & 自動デプロイ
```

**重要な設計上の特徴**: `ANTHROPIC_API_KEY` を CI に設定する必要はありません。LLM 分析は Claude Code（人間が起動するセッション）で行います。GitHub Actions は純粋にデータ収集のみ。

---

## ディレクトリ構成

```
news-prediction-matcher/
├── src/
│   ├── main.py             # NHK/Yahoo/BBC RSS フェッチャー + 本文スクレイプ
│   ├── fetch_markets.py    # Polymarket Gamma API 出来高上位市場取得
│   ├── pipeline.py         # GH Actions 起動→ポーリング→分析の自動化
│   └── polymarket.py       # （旧）キーワード検索クライアント
├── data/                   # ニュース・市場の日次 JSON スナップショット
│   ├── news-YYYY-MM-DD.json
│   └── markets-YYYY-MM-DD.json
├── reports/                # 日次サマリレポート（旧形式、互換維持）
│   └── YYYY-MM-DD.md
├── articles/               # 個別記事 Markdown
│   └── YYYY-MM-DD-{slug}.md
├── web/                    # Astro 静的サイト
│   ├── src/pages/
│   │   ├── index.astro     # トップ（記事フィード）
│   │   ├── about.astro     # サイトコンセプト
│   │   ├── articles/[slug].astro
│   │   └── reports/[slug].astro
│   ├── src/layouts/Base.astro
│   └── public/styles/global.css
├── .github/workflows/
│   └── fetch-data.yml      # 手動トリガーのみ (workflow_dispatch)
└── requirements.txt
```

---

## ローカルでの実行

### 環境準備

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### ニュース取得（1ソースあたり5件）

```bash
python src/main.py 5 > data/news-$(date +%Y-%m-%d).json
```

各記事に `body` フィールドが含まれます（最大3,000字）。スクレイプは並列処理（`MAX_WORKERS=8`）。

### Polymarket 市場取得（上位50件）

```bash
python src/fetch_markets.py 50 > data/markets-$(date +%Y-%m-%d).json
```

カテゴリ多様化のため、出力の80%は非スポーツ市場が割り当てられます。

### サイトのビルド

```bash
cd web
npm install
npm run build      # → web/dist/
npm run dev        # ローカル開発サーバー
```

---

## GitHub Actions による自動化

### 手動トリガー

```bash
# Personal Access Token (repo + workflow スコープ) を発行
export GITHUB_PAT=ghp_xxxxxxxxxxxx

curl -X POST \
  -H "Authorization: Bearer $GITHUB_PAT" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/probable-press/news-prediction-matcher/actions/workflows/fetch-data.yml/dispatches \
  -d '{"ref":"main"}'
```

### Claude Code からの一気通貫実行

```bash
GITHUB_PAT=ghp_xxxx python src/pipeline.py
```

`pipeline.py` は以下を自動実行します：

1. `workflow_dispatch` で `fetch-data.yml` を起動
2. 完了まで最大10分ポーリング（15秒間隔）
3. `git pull` でデータ取得
4. （オプション）`src/analyze.py` 呼び出し

---

## 編集方針

### ギャップ判定

|gap| ≥ 10pp（パーセンテージポイント）を「🚩」フラグの基準としています。例：

- ニュースが「協議が決裂」を示唆 → 市場は依然として 66% Yes
- → ニュース示唆値を 42% と算出 → Gap −24pp → **flagged**

### 記事スタイル

- 専門知識を前提にしない（高校生が読み進められる文体）
- 一次ソース（RSS本文）から具体的な数字・固有名詞を引用
- 予測市場の概念は毎記事で簡潔に再説明
- 結論セクションで「何を覚えておくといいか」を箇条書き

### 信頼性の担保

- すべてのデータ・コード・分析プロセスは公開
- 編集介入なし（Claude Code が機械的に実行）
- データソースの一次URLを各記事末尾に明示
- 投資助言ではなく、教育・情報提供目的

---

## なぜ ANTHROPIC_API_KEY を CI に置かないのか

LLM 分析を CI で自動化すると、以下のリスクが生じます：

- 月数千円〜数万円のコストが沈黙の中で発生し続ける
- プロンプトの調整が困難（CI ログだけでは原因特定が難しい）
- ハルシネーション（幻覚）が無監視で記事になる

そのため Claude Code（人間がセッションを起動して対話的に実行）で分析する設計にしています。これは時間効率と品質管理のバランスを優先した判断です。

---

## ライセンス・免責

- コード: MIT License（予定）
- 記事: 内容の利用は個人の自由ですが、引用時は出典明示をお願いします
- **本サイトの分析は投資助言ではありません**。予測市場には操作リスクや薄商い市場の不安定性があり、価格は将来の出来事を保証するものではありません

---

## コントリビューション

データソースの追加・記事スタイルの改善・バグ修正の Issue / PR は歓迎です。ソースを追加する場合は以下の条件を満たすこと：

- RSS / 公開API があること（スクレイプ前提のサイトは避ける）
- 利用規約上、データ収集が許諾されていること
- 編集方針（ギャップ分析）に貢献するソースであること

---

## 関連リンク

- 🌐 [Live site](https://news-prediction-matcher.pages.dev)
- ℹ️ [About ページ](https://news-prediction-matcher.pages.dev/about)
- 📊 [Polymarket](https://polymarket.com)
- 📰 ニュースソース: [NHK](https://news.web.nhk/newsweb) / [Yahoo Japan](https://news.yahoo.co.jp) / [BBC](https://www.bbc.com/news)


## RSS / 記事取得の安全境界

`src/main.py` の取得は HTTPS のみ。BBC RSS も HTTPS を使用する。
許可先は完全一致の `news.web.nhk` / `www3.nhk.or.jp`、
`news.yahoo.co.jp`、`feeds.bbci.co.uk` / `www.bbc.co.uk` / `www.bbc.com`。
リダイレクトは同じ配信元グループ内で最大5回とし、各段で URL と DNS を再検証する。
保存済み `data/news-2026-08-10.json` の記事ホスト（NHK / Yahoo / BBC UK）を維持し、
BBC UK → BBC.com と旧NHK → news.web.nhk の公式ホスト間移動を許容する。
新しい配信先はワイルドカードで許可せず、公式情報と実際の配信を確認して追加する。

- DNS の全回答が公開 unicast IP であることを確認し、その数値 IP に直接接続する。
  接続時の再DNS解決は行わず、TLSの証明書・hostname検証とSNIには元のホスト名を使う。
  private / loopback / link-local / multicast / 予約済みアドレスやIPv6移行アドレスを拒否する。
- 環境変数の HTTP(S) proxy、認証情報、Cookie は使用しない。HTTPS downgrade、
  userinfo、443以外のport、配信元をまたぐredirectを拒否する。
- RSSは2MiB、記事は4MiBまでをストリームで読み、Content-Lengthの有無だけに依存しない。
  圧縮応答による展開負荷を避けるためidentity encodingを要求し、圧縮された応答は拒否する。
- connect/TLSは最大5秒、socket readは最大10秒、redirectとbody readには協調的な
  30秒deadlineを設ける。OSのDNS解決とHTTPヘッダ・chunk trailer解析には厳密な全体deadline保証がないため、
  Actionsのjob timeoutも維持する。これらを超えて全面的に無制限取得を許可しない。
- 新ホスト、圧縮強制、サイズ超過等は取得失敗になる。RSS失敗はそのsourceをskipし、
  記事失敗は既存の空body（Yahooはpickup本文へのfallback）になる。
  取得した内容自体の真実性やMarkdownのHTML安全性を保証するものではない。

ネットワークアクセスなしの検証:

```bash
python -m unittest discover -s tests -v
```

安全境界のテストはDNS・socket・HTTP応答をmockする。
応答の寿命の回帰テストはローカルのUnix socketpairと実際のHTTP parserを使い、
Content-Length分の読み取りでsocketが閉じる場合、空応答、chunked、EOF、
途中切断、サイズ上限とtimeoutを検証する。公開/内部IPには接続しない。
本番collectorやworkflowを起動する必要はない。


## 取得元ごとの障害分離

`fetch-data.yml` は `src/collect_data.py` で5つのcollectorを個別に実行する。
Guardian の401などで一つが失敗しても、残りの取得を続け、成功したデータを
先にコミット・pushする。最後の status step は一部失敗・警告・設定不足があれば
失敗（赤）になり、Actions summary に取得元別の結果を残す。赤い実行でも
一部のデータは保存されているため、保存の成否は `Commit data` step で確認する。

- stdout は一時ファイルに取り、終了コード0・JSON配列・各レコードの識別項目を
  検証してから日次ファイルをatomic replaceする。失敗時は同日・過去日の
  保存済みデータを変更せず、空ファイルや途中のJSONを公開しない。
- news / markets / Guardian の空配列は取得失敗扱い。Dune / Metaculus の
  設定済みcollectorが返した正常な空配列は許容する。設定不足は明示的なskipとし、
  既存データを空配列で上書きしない。
- collector が有効なデータとstderrの警告を返した場合は `partial` と表示し、
  データは保存する。RSSの一部失敗・記事本文のfallbackを全件成功と表示しない。
- API例外にはキーを含むURLが入る場合があるため、生のstderrはログやmanifestへ
  転記しない。失敗理由にはHTTP statusなど固定の情報だけを出す。
- コミット対象はこの実行で検証した変更ファイルだけ。既存のmtimeによる保存期間
  （news/Guardian 7日、Dune 14日、Metaculus 30日）は、その取得元の新しい
  正常データがある場合のみ適用し、失敗・skipした取得元は削除しない。
- subprocessごとの上限はnews 240秒、markets 90秒、Dune 120秒、
  Metaculus/Guardian 45秒。さらにcheckoutより前から全collector共通の7分deadlineを
  設け、setup・依存installにも同じ時間枠を使う。各subprocessは残り時間との小さい方で
  打ち切り、時間切れ後の取得元は `collection budget exhausted` としてskipする。
  既に検証したデータは保存し、未取得元の既存データは保持して、最後にdegradedを報告する。
  既存の10分job timeoutは延長せず、commit/pushと最終報告に約3分の余裕を残す。
  通信の安全境界も維持する。

状態manifestは `$RUNNER_TEMP` に置き、公開データには含めない。収集、対象ファイルの
stage、最終結果の報告を分けているため、部分成功の保存前にエラーで終了しない。
ネットワーク不要の `python -m unittest discover -s tests -v` で、Guardian 401、
先頭collectorの失敗、全件失敗、不正/空/途中JSON、タイムアウト、設定不足、
変更なし、対象限定の実Git commit/push、最後の失敗表示まで検証できる。
