---
name: daily-report
description: Probable Press の日次レポートを英語で生成する。data/ の全ソースを読み、ニュースと予測市場の対応関係・ギャップ・データ品質を事実中心で整理し reports/YYYY-MM-DD.md として保存する。
---

# Daily Report — Probable Press

## ミッション

その日のデータを**英語で**冷静に整理し、編集判断の素材を作る。articles/ と異なり、感情的な比喩・読みやすさ優先の言い換えは不要。**事実、数字、観察、アクションアイテム**だけ。

## 実行手順

1. **データ読込**：本日の日付に対応する以下を読む
   - `data/markets-YYYY-MM-DD.json`
   - `data/news-YYYY-MM-DD.json`
   - `data/guardian-YYYY-MM-DD.json`
   - `data/metaculus-YYYY-MM-DD.json`
   - `data/dune-YYYY-MM-DD.json`

2. **集計**：
   - 市場数、非スポーツ市場数、24時間出来高の分布
   - ニュース件数、ソース別内訳
   - Metaculus questions のうち community_prediction が取得できた件数
   - Dune の大口取引件数

3. **クラスタ分類**：当日のトピックを 3〜6 個のクラスタに分ける（例：Iran/ME, Energy, Fed/Monetary, Crypto, Politics, Disasters）

4. **保存**：`reports/YYYY-MM-DD.md`

## レポートフォーマット

```markdown
# News × Polymarket Gap Analysis — YYYY-MM-DD

_Generated: YYYY-MM-DD UTC | Sources: NHK / Yahoo / BBC RSS, Guardian Open Platform API, Polymarket Gamma API, Metaculus API, Dune Analytics_

---

## Data Summary

| Source | Items | Notes |
|---|---:|---|
| Polymarket markets | N | top by 24h volume; M non-sports |
| News (NHK/Yahoo/BBC) | N | RSS + body scrape |
| Guardian articles | N | sections: ... |
| Metaculus questions | N | M with community_prediction |
| Dune large bets | N | $10K+ threshold |

**Flagged gaps (|gap| ≥ 10pp)**: N
**Notable timeframe splits**: N

---

## {Cluster Name 1, e.g. Iran / Middle East}

### Diplomatic / news developments

- {Bullet points, source attribution}
- {Each bullet ≤ 25 words; cite source: NHK / Guardian / etc}

### Polymarket — {topic} markets

| Market | Yes price | 24h vol | endDate |
|---|---:|---:|---|

### Observation

- {Factual analysis: term structure, gap vs news, asymmetric volume}
- {No editorializing. State what is.}

---

{Repeat for each cluster}

---

## Articles published YYYY-MM-DD

1. `slug.md` — one-line summary
2. ...

---

## Outstanding observations for editorial follow-up

- {Action items: data quality issues, missing markets, future angles}
- {Be honest about limitations, e.g. "Metaculus community_prediction returned 0 — free tier limitation"}
```

## スタイルルール

- **Language**: English only.
- **Tone**: Analytical, factual, no rhetorical questions, no emotive adjectives.
- **Numbers**: Use exact figures from the data. Format: `99.8%`, `$5.20M / 24h`, `$13.2M`.
- **Sourcing**: Always cite (NHK / Guardian / Polymarket / etc.) inline.
- **Brevity**: Bullets ≤ 25 words; observations ≤ 3 bullets per cluster.
- **No speculation**: If the data doesn't show it, don't write it.

## データ品質の記述

毎回必ずチェックして記載：

- **Metaculus**: `community_prediction is None` の件数 → 0件なら制限について明記し、必要ならBot Benchmarking Tier申請を action item に追加
- **Dune**: 0 rows なら原因仮説（クエリのカラム・コントラクトアドレス）を記載
- **Markets**: Top 50 がスポーツに偏っている場合は注記

## 観察すべき主な指標

1. **Term structure**: 同一テーマで時間軸が異なる市場の確率差
2. **Volume asymmetry**: 確率は低いが24h出来高が大きい市場（ヘッジ vs 信念）
3. **News × market mapping**: ニュースに対応する市場の有無
4. **Gap magnitude**: ニュースから推定される確率と市場確率の差

## 完了後

- `git add reports/` → `git commit -m "report: YYYY-MM-DD gap analysis"` → `git push origin main`
- ユーザーにレポートのファイルパスとクラスタ要約（3〜5行）を報告
