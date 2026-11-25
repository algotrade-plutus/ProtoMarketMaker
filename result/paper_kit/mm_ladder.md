| rung | environment | im2022 return | im2022 fills | krx2025 return | krx2025 fills | krx2025 pre-cutover return | krx2025 pre-cutover fills | krx2025 post-cutover return | krx2025 post-cutover fills |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|
| N0 | naive as-is | -12.93% | 129 | +29.57% | 693 | -5.22% | 228 | +36.70% | 465 |
| N1 | + own-price fills | -15.90% | 129 | -41.99% | 693 | -14.09% | 228 | -32.47% | 465 |
| N2 | + dated VSD IM (13% / 17%) | -15.90% | 129 | -41.99% | 693 | -14.09% | 228 | -32.47% | 465 |
| N3 | + fee on every fill | -16.42% | 129 | -44.77% | 693 | -15.02% | 228 | -35.01% | 465 |
| F-opt | Plutus faithful-A, optimistic queue | -2.52% | 198 | -12.02% | 575 | -7.58% | 261 | -4.81% | 314 |
| F-con | Plutus faithful-A, conservative queue | -11.47% | 116 | -42.96% | 358 | -25.55% | 153 | -23.39% | 205 |

- im2022 (all 40 sessions): faithful band -11.47% .. -2.52%; naive rungs outside it: N0, N1, N2, N3. Source `result/mm_ladder/im2022.json` (sha256 `677d7370abb8b70a…`).
- krx2025 (all 40 sessions): faithful band -42.96% .. -12.02%; naive rungs outside it: N0, N3. Source `result/mm_ladder/krx2025.json` (sha256 `02dccecd959cca5c…`).
- krx2025 pre-cutover (20 pre-cutover sessions (like-for-like with the results committed before plutus-simulator 391e2e2, which compared these sessions only)): faithful band -25.55% .. -7.58%; naive rungs outside it: N0. Source `result/mm_ladder/krx2025.json` (sha256 `02dccecd959cca5c…`).
- krx2025 post-cutover (20 post-cutover sessions from 2025-05-05 (QD 26 two-layer margin; returns from the 2025-04-29 close)): faithful band -23.39% .. -4.81%; naive rungs outside it: N0, N1, N2, N3. Source `result/mm_ladder/krx2025.json` (sha256 `02dccecd959cca5c…`).
