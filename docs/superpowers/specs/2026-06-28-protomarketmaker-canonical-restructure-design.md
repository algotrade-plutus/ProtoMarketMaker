# ProtoMarketMaker — Canonical Python Project Restructure

**Date:** 2026-06-28
**Status:** Approved design, pending spec review → implementation plan
**Scope:** The committed research pipeline only (backtest / optimization / out-of-sample / data load). The uncommitted paper-trading subsystem is out of scope; the layout leaves a clean slot for it later.

## Goal

Restructure the repo into a canonical, installable Python package (`src/` layout) so that:

1. It is a proper installable package with console-script entry points (deployment + reuse).
2. Runs stay reproducible under `plutus check`/`snapshot` (uv + committed lockfile, no "NOT reproducible" deprecation).
3. The latent module/package name collisions (`utils`, `evaluation`) are eliminated.

This design covers **ProtoMarketMaker only**. A companion change to plutus-verify (an opt-in `env.install_project` so the project package is installed in-container) has been handed off separately and is a **prerequisite** for the `plutus check` gate below.

## Decisions (from brainstorming)

- **Layout:** `src/` layout (Approach B).
- **Invocation:** console scripts (`pmm-*`) declared in `pyproject.toml`; the plutus manifest invokes those console scripts.
- **Environment:** uv + committed `uv.lock`; `requirements.txt` removed.
- **In-container import bridge:** plutus is patched (separately) to install the project (`env.install_project: true`); ProtoMarketMaker assumes that field exists.
- **`price_util.py`:** orphan (imported by nothing); moved into the package, flagged as a drop candidate, not deleted in this pass.
- **Tests:** add a minimal `tests/` (smoke import + one tiny unit).

## Context / starting state

Committed, tracked Python (the pipeline):

- Entry scripts: `backtesting.py`, `evaluation.py`, `optimization.py`, `data_loader.py`, `price_util.py`, `utils.py`
- Packages: `config/config.py`, `database/{data_service,query}.py`, `metrics/metric.py`
- Data/config/output: `parameter/*.json`, `data/` (gitignored), `result/`

Import graph (verified):

- `backtesting.py` → `config.config`, `metrics.metric`, `utils`, `plutus_verify`
- `evaluation.py` → `config.config`, `backtesting`, `metrics.metric`, `plutus_verify`
- `optimization.py` → `config.config`, `backtesting`, `optuna`
- `data_loader.py` → `database.data_service`, `config.config`
- `database/data_service.py` → `database.query`, `config.config`
- `price_util.py` → imported by nothing
- Each entry script uses an `if __name__ == "__main__":` block; none define `main()` yet.

Known problems being fixed:

- **Name collisions:** `utils.py` + `utils/` package (empty `__init__.py` shadows the module → `ImportError: cannot import name 'get_expired_dates'`); `evaluation.py` + `evaluation/` package (same latent shape).
- **`.gitignore` ignores `__init__.py`** → package markers uncommitted; behaves differently in a fresh clone vs local tree (reproducibility hazard).
- **Empty residue dirs** from the uncommitted paper-trading work: `engine/`, `core/`, `connectors/`, `paper_trading/`, plus stub `utils/`, `evaluation/`, `tools/`.

## Target structure

```
ProtoMarketMaker/
├── pyproject.toml              # metadata, deps, [project.scripts], hatchling backend
├── uv.lock                     # committed; reproducibility source of truth
├── .python-version             # "3.11"
├── README.md                   # updated run instructions (uv + console scripts)
├── .gitignore                  # REMOVE the `__init__.py` ignore line
├── src/
│   └── proto_market_maker/
│       ├── __init__.py         # __version__
│       ├── backtest.py         # ← backtesting.py  (class Backtesting + main())
│       ├── evaluate.py         # ← evaluation.py   (main())
│       ├── optimize.py         # ← optimization.py (main())
│       ├── data_loader.py      # ← data_loader.py  (main())
│       ├── price_util.py       # ← price_util.py   (orphan; drop candidate)
│       ├── utils.py            # ← utils.py
│       ├── config/{__init__,config}.py
│       ├── database/{__init__,data_service,query}.py
│       └── metrics/{__init__,metric}.py
├── parameter/                  # *.json inputs — stay at repo root (manifest refs)
├── data/                       # runtime data, gitignored (is/ os/ sample/)
├── result/                     # output artifacts (manifest refs)
├── docs/superpowers/specs/     # this design doc
└── tests/
    └── test_smoke.py           # import package + 1 unit (e.g. utils.round_decimal)
```

Deleted (empty, unused by the pipeline): `engine/`, `core/`, `connectors/`, `paper_trading/`, `utils/`, `evaluation/`, `tools/`. Removing `utils/` and `evaluation/` dissolves both name collisions.

## pyproject.toml

- Build backend: **hatchling**; `requires-python = ">=3.11"`; package = `src/proto_market_maker`.
- `dependencies` (pinned, from current requirements.txt): `pandas==2.2.2`, `numpy==2.0.1`, `matplotlib==3.9.1`, `optuna==3.6.1`, `psycopg2-binary==2.9.9`, `python-dotenv==1.0.1`.
- `[dependency-groups] dev`: `pylint`, `pytest` (PEP 735; installed by `uv sync`).
- `[project.scripts]`:
  - `pmm-load-data = "proto_market_maker.data_loader:main"`
  - `pmm-backtest  = "proto_market_maker.backtest:main"`
  - `pmm-optimize  = "proto_market_maker.optimize:main"`
  - `pmm-evaluate  = "proto_market_maker.evaluate:main"`
- `uv.lock` committed. `requirements.txt` removed (uv.lock is canonical; plutus restores from the lock).

Each entry module: extract the `if __name__ == "__main__":` body into `def main():`, keep a thin guard `if __name__ == "__main__": main()` so both the console script and `python -m proto_market_maker.<mod>` work.

## Import rewrites

All intra-project imports become absolute, package-qualified:

- `from config.config import …`        → `from proto_market_maker.config.config import …`
- `from metrics.metric import …`        → `from proto_market_maker.metrics.metric import …`
- `from utils import …`                 → `from proto_market_maker.utils import …`
- `from database.data_service import …` → `from proto_market_maker.database.data_service import …`
- `from database.query import …`        → `from proto_market_maker.database.query import …`
- `from backtesting import Backtesting`  → `from proto_market_maker.backtest import Backtesting`

## .plutus/manifest.yaml changes

- `env`: `manager: uv`, `lockfile: uv.lock`, `install_project: true`, `requirements_file: null`. (`base: python`, `python_version: "3.11"` unchanged.) This removes the "NOT reproducible" deprecation.
- Step `command`s → console scripts:
  - `data_collection`        → `pmm-load-data`
  - `in_sample_backtest`     → `pmm-backtest`
  - `out_of_sample_backtest` → `pmm-evaluate`
  - `optimization`           → unchanged (`verification_mode: artifact_check`, no command)
- `inputs` / `outputs` / `expected` paths (`parameter/…`, `data/…`, `result/…`) **unchanged** — they stay at repo root, so only commands change.
- Expected metric `value`s are re-blessed via `plutus snapshot` after the move (may shift slightly under the pinned env).
- Artifacts stay `visual_similarity`; promoting charts to `byte_exact` is a possible follow-up once matplotlib SVG determinism under the locked env is confirmed.

## .gitignore changes

- Remove the `__init__.py` line (package markers must be committed).
- Remove the `.python-version` line (it is now part of the uv pin and must be committed).
- Keep: `*.csv`, `.env`, `*venv/`, `__pycache__`, `.plutus/run/`, `.plutus/results/`, `.plutus/build/`, `.plutus/Dockerfile.generated`.

## Verification gate

1. `uv sync` creates the env; `uv run pmm-backtest` (and the other three) run locally from repo root.
2. `uv run pytest` passes the smoke test.
3. With the patched plutus: `plutus check .` builds, installs the project, runs all steps, and reaches the backtests (confirming the old `utils` ImportError is dead). Metrics compared within tolerance.
4. `plutus snapshot .` re-blesses the baseline (metric values + `.plutus/expected/`), then `git add .plutus/expected .plutus/manifest.yaml result` and commit.

## Risks / dependencies

1. **Prerequisite:** the plutus `install_project` patch must land before the `plutus check` gate can import the package. Until then, local `uv run` verification stands in.
2. **Re-blessed metrics:** values may differ slightly under pinned deps; that is expected and the new baseline is committed deliberately.
3. **cwd-relative paths:** `parameter/`, `data/`, `result/` are resolved relative to the working directory; correct under plutus (`/work`) and documented for local runs (run from repo root). Making them configurable is out of scope.
4. **`data/` not committed:** the verifier resolves it from the declared Google Drive source (requires plutus's `gdown` dependency, also handed off separately).

## Out of scope

- Paper-trading subsystem (engine/connectors/runner) — slots into the package later as its own subpackage.
- Making data/result/parameter paths configurable via CLI args.
- `byte_exact` chart baselines.
- The plutus-verify patches (project install, gdown dependency) — tracked separately.
