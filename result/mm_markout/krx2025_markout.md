### krx2025: markouts (all 40 sessions; price path: tape)

| arm | sessions | contracts | taker share | taker price impr. (median, pts) | markout 1 min | 5 min | close | P&L (M đ) | carry (M đ) | mark switch (M đ) | trading (M đ) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| N0 | 40 | 713 | 0% |  | +3.11 | +2.80 | +3.23 | +147.8 | -73.4 | +3.7 | +217.4 |
| N3 | 40 | 713 | 0% |  | -1.91 | -2.22 | -1.79 | -223.8 | -73.4 | +3.7 | -154.2 |
| F-opt | 40 | 575 | 50% | +1.20 | +0.06 | -0.68 | -1.67 | -60.1 | +45.3 | +0.0 | -105.4 |
| F-con | 40 | 358 | 68% | +0.70 | -0.08 | -0.31 | -0.41 | -214.8 | -194.1 | +0.0 | -20.7 |

#### view `pre_cutover`: 20 pre-cutover sessions (like-for-like with the results committed before plutus-simulator 4867d46)

| arm | sessions | contracts | taker share | taker price impr. (median, pts) | markout 1 min | 5 min | close | P&L (M đ) | carry (M đ) | mark switch (M đ) | trading (M đ) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| N0 | 20 | 234 | 0% |  | +0.49 | -0.46 | -0.68 | -26.1 | -1.7 | -3.5 | -20.8 |
| N3 | 20 | 234 | 0% |  | -1.40 | -2.36 | -2.58 | -75.1 | -1.7 | -3.5 | -69.9 |
| F-opt | 20 | 261 | 66% | +0.90 | +0.06 | -1.13 | -5.54 | -37.9 | +110.8 | +0.0 | -148.6 |
| F-con | 20 | 153 | 85% | +0.50 | -0.38 | -1.06 | -2.51 | -127.7 | -86.9 | +0.0 | -40.8 |

#### view `post_cutover`: 20 post-cutover sessions from 2025-05-05

| arm | sessions | contracts | taker share | taker price impr. (median, pts) | markout 1 min | 5 min | close | P&L (M đ) | carry (M đ) | mark switch (M đ) | trading (M đ) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| N0 | 20 | 479 | 0% |  | +4.39 | +4.39 | +5.14 | +173.9 | -71.6 | +7.3 | +238.3 |
| N3 | 20 | 479 | 0% |  | -2.16 | -2.15 | -1.40 | -148.7 | -71.6 | +7.3 | -84.4 |
| F-opt | 20 | 314 | 37% | +2.00 | +0.06 | -0.31 | +1.55 | -22.2 | -65.4 | +0.0 | +43.2 |
| F-con | 20 | 205 | 55% | +1.10 | +0.15 | +0.25 | +1.15 | -87.1 | -107.2 | +0.0 | +20.1 |

Markouts: mean per contract, index points, + = good for A (1 point = 100,000 đ per contract). Taker share: contracts filled as taker among those with a liquidity side. Carry = previous end positions x close-to-close move; mark switch = naive's revaluation across its F1/F2 stitch (the basis, naive only); trading = the rest.

Inputs:

- N0: naive trace run by this module
- N3: naive trace run by this module
- F-opt: `krx2025_fills_F-opt.json` (sha256 `de1ec888ae8e9c5f…`)
- F-con: `krx2025_fills_F-con.json` (sha256 `ee6cf8bdd667e0d9…`)
