| window (sessions) | arm | contracts | taker share | taker impr. (median pt) | markout 1 min | 5 min | close | P&L (M đ) | carry (M đ) | mark switch (M đ) | trading (M đ) |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| im2022 (all 40 sessions) | N0 | 137 | 0% | -- | +0.61 | +0.38 | -0.58 | -64.7 | -55.3 | +1.0 | -10.4 |
| im2022 (all 40 sessions) | N3 | 137 | 0% | -- | -0.47 | -0.71 | -1.66 | -82.1 | -55.3 | +1.0 | -27.9 |
| im2022 (all 40 sessions) | F-opt | 198 | 65% | +0.50 | +0.21 | +0.41 | +3.78 | -12.6 | -85.0 | +0.0 | +72.4 |
| im2022 (all 40 sessions) | F-con | 116 | 91% | +0.30 | -0.31 | -0.57 | +3.12 | -57.3 | -92.1 | +0.0 | +34.7 |

Markouts: mean per contract in index points, + = good for A. Mark switch: naive's revaluation across its F1/F2 stitch (P&L = carry + mark switch + trading). Sources: `result/mm_markout/im2022_markout.json` (price path tape)
