| window (sessions) | arm | contracts | taker share | taker impr. (median pt) | markout 1 min | 5 min | close | P&L (M đ) | carry (M đ) | mark switch (M đ) | trading (M đ) |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| im2022 (all 40 sessions) | N0 | 137 | 0% | -- | +0.61 | +0.38 | -0.58 | -64.7 | -55.3 | +1.0 | -10.4 |
| im2022 (all 40 sessions) | N3 | 137 | 0% | -- | -0.47 | -0.71 | -1.66 | -82.1 | -55.3 | +1.0 | -27.9 |
| im2022 (all 40 sessions) | F-opt | 198 | 65% | +0.50 | +0.21 | +0.41 | +3.78 | -12.6 | -85.0 | +0.0 | +72.4 |
| im2022 (all 40 sessions) | F-con | 116 | 91% | +0.30 | -0.31 | -0.57 | +3.12 | -57.3 | -92.1 | +0.0 | +34.7 |
| krx2025 (all 40 sessions) | N0 | 713 | 0% | -- | +3.11 | +2.80 | +3.23 | +147.8 | -73.4 | +3.7 | +217.4 |
| krx2025 (all 40 sessions) | N3 | 713 | 0% | -- | -1.91 | -2.22 | -1.79 | -223.8 | -73.4 | +3.7 | -154.2 |
| krx2025 (all 40 sessions) | F-opt | 575 | 50% | +1.20 | +0.06 | -0.68 | -1.67 | -60.1 | +45.3 | +0.0 | -105.4 |
| krx2025 (all 40 sessions) | F-con | 358 | 68% | +0.70 | -0.08 | -0.31 | -0.41 | -214.8 | -194.1 | +0.0 | -20.7 |

Markouts: mean per contract in index points, + = good for A. Mark switch: naive's revaluation across its F1/F2 stitch (P&L = carry + mark switch + trading). Sources: `result/mm_markout/im2022_markout.json` (price path tape), `result/mm_markout/krx2025_markout.json` (price path tape)
