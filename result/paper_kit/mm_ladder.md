| rung | environment | im2022 return | im2022 fills | krx2025 return | krx2025 fills |
|---|---|--:|--:|--:|--:|
| N0 | naive as-is | -12.93% | 129 | -5.22% | 228 |
| N1 | + own-price fills | -15.90% | 129 | -14.09% | 228 |
| N2 | + dated VSD IM (13% / 17%) | -15.90% | 129 | -14.09% | 228 |
| N3 | + fee on every fill | -16.42% | 129 | -15.02% | 228 |
| F-opt | Plutus faithful-A, optimistic queue | -2.52% | 198 | -7.58% | 261 |
| F-con | Plutus faithful-A, conservative queue | -11.47% | 116 | -25.55% | 153 |

- im2022 (all 40 sessions): faithful band -11.47% .. -2.52%; naive rungs outside it: N0, N1, N2, N3. Source `result/mm_ladder/im2022.json` (sha256 `aa4c9551545099b8…`).
- krx2025 (20 pre-cutover sessions): faithful band -25.55% .. -7.58%; naive rungs outside it: N0. Source `result/mm_ladder/krx2025.json` (sha256 `d8ae7770b1d5e78e…`).
