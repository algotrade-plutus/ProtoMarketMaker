### im2022: markouts (all 6 sessions, first 6; price path: tape)

| arm | sessions | contracts | taker share | taker price impr. (median, pts) | markout 1 min | 5 min | close | P&L (M đ) | carry (M đ) | mark switch (M đ) | trading (M đ) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| N0 | 6 | 29 | 0% |  | -0.21 | -1.34 | +2.49 | +11.0 | +4.3 | +0.0 | +6.7 |
| N3 | 6 | 29 | 0% |  | -0.73 | -1.86 | +1.98 | +8.8 | +4.3 | +0.0 | +4.6 |
| F-opt | 6 | 39 | 59% | +0.40 | -0.54 | -0.92 | +3.68 | +20.2 | +6.3 | +0.0 | +13.9 |

Markouts: mean per contract, index points, + = good for A (1 point = 100,000 đ per contract). Taker share: contracts filled as taker among those with a liquidity side. Carry = previous end positions x close-to-close move; mark switch = naive's revaluation across its F1/F2 stitch (the basis, naive only); trading = the rest.

Inputs:

- N0: naive trace run by this module
- N3: naive trace run by this module
- F-opt: `im2022_fills_F-opt.json` (sha256 `771899659987ad1a…`)
