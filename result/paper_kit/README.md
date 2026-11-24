# MarketMaker paper kit (RIVF'26)

Generated files: do not edit by hand. Every value is read from the result files below; `kit.json` lists the
values used and the sha256 of each source.

| file | content | source |
|---|---|---|
| `mm_ladder.pdf`, `mm_ladder.png` | per window, final return of each naive rung N0..N3 (dots) and the faithful queue band F-con..F-opt (bar, shaded across the panel); 3.5 in column width, Okabe-Ito colours plus marker shape | `result/mm_ladder/<window>.json` |
| `mm_ladder.tex`, `mm_ladder.md` | the ladder table (return and fills per rung and window) | `result/mm_ladder/<window>.json` |
| `mm_markout.tex`, `mm_markout.md` | markouts (1 min / 5 min / close), taker share, taker price improvement, P&L split into carry / mark switch / trading | full-window `result/mm_markout/<window>_markout.json` only (partial checks such as `*_first6_*` are left out) |
| `kit.json` | every value used, with source sha256 | all of the above |

The LaTeX tables need `booktabs`. The markout table is written only when a full-window markout result exists.

Regenerate (from the repo root):

```bash
.venv/bin/python -m proto_market_maker.experiments.mm_paper_kit
```

Upstream: `mm_faithful_a` → `mm_ladder` for the ladder; `mm_fills_trace` → `mm_markout` for the markouts. The full
chain and the preliminary report are in `result/REPORT.md` (`mm_report`).
