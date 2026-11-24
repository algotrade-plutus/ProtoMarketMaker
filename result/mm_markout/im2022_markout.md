### im2022: markouts (all 40 sessions; price path: tape)

| arm | sessions | contracts | taker share | taker price impr. (median, pts) | markout 1 min | 5 min | close | P&L (M đ) | carry (M đ) | mark switch (M đ) | trading (M đ) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| N0 | 40 | 137 | 0% |  | +0.61 | +0.38 | -0.58 | -64.7 | -55.3 | +1.0 | -10.4 |
| N3 | 40 | 137 | 0% |  | -0.47 | -0.71 | -1.66 | -82.1 | -55.3 | +1.0 | -27.9 |
| F-opt | 40 | 198 | 65% | +0.50 | +0.21 | +0.41 | +3.78 | -12.6 | -85.0 | +0.0 | +72.4 |
| F-con | 40 | 116 | 91% | +0.30 | -0.31 | -0.57 | +3.12 | -57.3 | -92.1 | +0.0 | +34.7 |

Markouts: mean per contract, index points, + = good for A (1 point = 100,000 đ per contract). Taker share: contracts filled as taker among those with a liquidity side. Carry = previous end positions x close-to-close move; mark switch = naive's revaluation across its F1/F2 stitch (the basis, naive only); trading = the rest.

- F-opt: 180 fills had no contract and were assigned one (3 ambiguous).
- F-con: 109 fills had no contract and were assigned one (1 ambiguous).

Inputs:

- N0: naive trace run by this module
- N3: naive trace run by this module
- F-opt: `fills_optimistic40.json` (sha256 `106887adb392315b…`); equity from `result/mm_faithful_a/im2022_optimistic.json`
- F-con: `fills_conservative40.json` (sha256 `e99e702b773595ff…`); equity from `result/mm_faithful_a/im2022_conservative.json`
