# ProtoMarketMaker Canonical Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the flat, script-based research pipeline into a canonical, installable `src/`-layout Python package (`proto_market_maker`) with console-script entry points, a uv-locked environment, and a plutus manifest that drives the package — eliminating the `utils`/`evaluation` name collisions on the way.

**Architecture:** All pipeline source moves under `src/proto_market_maker/`. Entry scripts become package modules exposing `main()`, wired as console scripts in `pyproject.toml`. Dependencies are upgraded and pinned via a committed `uv.lock`. The plutus manifest switches to `manager: uv` + `install_project: true` and invokes the console scripts. `plutus_verify` is **never** a runtime dependency — it is staged into the container by plutus and only installed locally for dev verification.

**Tech Stack:** Python ≥3.11, uv, hatchling build backend, pytest, plutus-verify 0.4.6.

## Global Constraints

- Python `>=3.11`; import/package name is `proto_market_maker` (distribution `proto-market-maker`).
- `src/` layout: package lives at `src/proto_market_maker/`.
- Environment is uv with a **committed `uv.lock`**; `requirements.txt` is removed.
- Dependencies are **upgraded to latest-compatible** (current versions are floors, not targets) and pinned by the lockfile.
- `plutus_verify` is NOT a project dependency (runtime or otherwise). Local dev installs it ad-hoc from the sibling wheel.
- Console scripts: `pmm-load-data`, `pmm-backtest`, `pmm-optimize`, `pmm-evaluate`, each → `proto_market_maker.<module>:main`.
- Data/config/output paths stay at repo root and are cwd-relative: `parameter/`, `data/`, `result/`. Pipeline runs from the repo root.
- The plutus manifest uses `env.install_project: true`. This field **landed in plutus-verify 0.4.6** (the local wheel/checkout), so the `plutus check`/`snapshot` gate (Task 6) can now run; everything before it is also verifiable locally.
- All file moves use `git mv` to preserve history.

---

### Task 1: Bootstrap the package skeleton, `pyproject.toml`, and uv lock

Create the package directory and packaging metadata so the environment installs. Real modules move in Task 2; here the package is an empty shell that builds.

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `src/proto_market_maker/__init__.py`
- Create: `src/proto_market_maker/config/__init__.py`, `src/proto_market_maker/database/__init__.py`, `src/proto_market_maker/metrics/__init__.py`
- Create: `uv.lock` (generated)

**Interfaces:**
- Produces: importable package `proto_market_maker` with `__version__`; console-script names `pmm-load-data|backtest|optimize|evaluate` (targets created in Tasks 2–3).

- [ ] **Step 1: Create the package `__init__.py` files**

`src/proto_market_maker/__init__.py`:
```python
"""ProtoMarketMaker — VN30 futures market-making research pipeline."""

__version__ = "0.1.0"
```
`src/proto_market_maker/config/__init__.py`, `src/proto_market_maker/database/__init__.py`, `src/proto_market_maker/metrics/__init__.py` — each an empty file:
```python
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "proto-market-maker"
version = "0.1.0"
description = "VN30 futures market-making research pipeline"
requires-python = ">=3.11"
dependencies = [
    "pandas>=2.2",
    "numpy>=2.0",
    "matplotlib>=3.9",
    "optuna>=3.6",
    "psycopg2-binary>=2.9",
    "python-dotenv>=1.0",
]

[project.scripts]
pmm-load-data = "proto_market_maker.data_loader:main"
pmm-backtest  = "proto_market_maker.backtest:main"
pmm-optimize  = "proto_market_maker.optimize:main"
pmm-evaluate  = "proto_market_maker.evaluate:main"

[dependency-groups]
dev = ["pytest>=8", "pylint>=3.3"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/proto_market_maker"]
```

- [ ] **Step 3: Write `.python-version`**

```
3.11
```

- [ ] **Step 4: Resolve, lock, and install (upgrade deps)**

Run:
```bash
uv lock
uv sync
```
Expected: `uv.lock` is created/updated with latest-compatible versions; `uv sync` creates `.venv` and installs deps + the `proto-market-maker` project.

- [ ] **Step 5: Verify the package imports and installs**

Run:
```bash
uv run python -c "import proto_market_maker; print(proto_market_maker.__version__)"
```
Expected: prints `0.1.0` (no ImportError).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .python-version uv.lock src/proto_market_maker/__init__.py \
        src/proto_market_maker/config/__init__.py \
        src/proto_market_maker/database/__init__.py \
        src/proto_market_maker/metrics/__init__.py
git commit -m "build: scaffold proto_market_maker package + uv lock"
```

---

### Task 2: Relocate modules into the package, delete residue, rewrite imports

Move every pipeline source file into the package with `git mv`, remove the empty paper-trading residue dirs (dissolving the `utils`/`evaluation` collisions), and rewrite all intra-project imports to be package-qualified.

**Files:**
- Move: `backtesting.py` → `src/proto_market_maker/backtest.py`
- Move: `evaluation.py` → `src/proto_market_maker/evaluate.py`
- Move: `optimization.py` → `src/proto_market_maker/optimize.py`
- Move: `data_loader.py` → `src/proto_market_maker/data_loader.py`
- Move: `price_util.py` → `src/proto_market_maker/price_util.py`
- Move: `utils.py` → `src/proto_market_maker/utils.py`
- Move: `config/config.py` → `src/proto_market_maker/config/config.py`
- Move: `database/data_service.py` → `src/proto_market_maker/database/data_service.py`
- Move: `database/query.py` → `src/proto_market_maker/database/query.py`
- Move: `metrics/metric.py` → `src/proto_market_maker/metrics/metric.py`
- Delete (empty dirs): `engine/ core/ connectors/ paper_trading/ utils/ evaluation/ tools/ config/ database/ metrics/` (the originals after their files move)

**Interfaces:**
- Produces: modules `proto_market_maker.backtest` (class `Backtesting`), `.evaluate`, `.optimize`, `.data_loader`, `.utils` (`get_expired_dates`, `from_cash_to_tradeable_contracts`, `round_decimal`), `.config.config` (`BACKTESTING_CONFIG`, `OPTIMIZATION_CONFIG`, `BEST_CONFIG`, `db_params`), `.database.data_service` (`DataService`), `.database.query`, `.metrics.metric` (`get_returns`, `Metric`).

- [ ] **Step 1: Move the entry-script modules (with rename)**

Run:
```bash
git mv backtesting.py   src/proto_market_maker/backtest.py
git mv evaluation.py    src/proto_market_maker/evaluate.py
git mv optimization.py  src/proto_market_maker/optimize.py
git mv data_loader.py   src/proto_market_maker/data_loader.py
git mv price_util.py    src/proto_market_maker/price_util.py
git mv utils.py         src/proto_market_maker/utils.py
```

- [ ] **Step 2: Move the subpackage modules**

Run:
```bash
git mv config/config.py        src/proto_market_maker/config/config.py
git mv database/data_service.py src/proto_market_maker/database/data_service.py
git mv database/query.py        src/proto_market_maker/database/query.py
git mv metrics/metric.py        src/proto_market_maker/metrics/metric.py
```

- [ ] **Step 3: Remove the empty residue directories**

Run:
```bash
rm -rf engine core connectors paper_trading utils evaluation tools config database metrics
```
Expected: these now-empty dirs (their tracked files already moved; any remaining `__init__.py` were gitignored stubs) are gone. Verify none held tracked files:
```bash
git status --short
```
Expected: shows the renames (`R`) only; no accidental deletions of tracked files beyond the moves.

- [ ] **Step 4: Rewrite imports in `backtest.py`**

In `src/proto_market_maker/backtest.py`, change:
```python
from config.config import BACKTESTING_CONFIG
from metrics.metric import get_returns, Metric
from utils import get_expired_dates, from_cash_to_tradeable_contracts, round_decimal
```
to:
```python
from proto_market_maker.config.config import BACKTESTING_CONFIG
from proto_market_maker.metrics.metric import get_returns, Metric
from proto_market_maker.utils import get_expired_dates, from_cash_to_tradeable_contracts, round_decimal
```

- [ ] **Step 5: Rewrite imports in `evaluate.py`**

In `src/proto_market_maker/evaluate.py`, change:
```python
from config.config import BEST_CONFIG
from backtesting import Backtesting
from metrics.metric import get_returns
```
to:
```python
from proto_market_maker.config.config import BEST_CONFIG
from proto_market_maker.backtest import Backtesting
from proto_market_maker.metrics.metric import get_returns
```

- [ ] **Step 6: Rewrite imports in `optimize.py`**

In `src/proto_market_maker/optimize.py`, change:
```python
from config.config import OPTIMIZATION_CONFIG
from backtesting import Backtesting
```
to:
```python
from proto_market_maker.config.config import OPTIMIZATION_CONFIG
from proto_market_maker.backtest import Backtesting
```

- [ ] **Step 7: Rewrite imports in `data_loader.py`**

In `src/proto_market_maker/data_loader.py`, change:
```python
from database.data_service import DataService
from config.config import BACKTESTING_CONFIG
```
to:
```python
from proto_market_maker.database.data_service import DataService
from proto_market_maker.config.config import BACKTESTING_CONFIG
```

- [ ] **Step 8: Rewrite imports in `database/data_service.py`**

In `src/proto_market_maker/database/data_service.py`, change:
```python
from database.query import MATCHED_QUERY, BID_ASK_QUERY, CLOSE_QUERY
from config.config import db_params
```
to:
```python
from proto_market_maker.database.query import MATCHED_QUERY, BID_ASK_QUERY, CLOSE_QUERY
from proto_market_maker.config.config import db_params
```

- [ ] **Step 9: Verify all modules import**

Run:
```bash
uv pip install /Users/nadan/algotrade-research/plutus-verify/dist/plutus_verify-0.4.6-py3-none-any.whl
uv run python -c "import proto_market_maker.backtest, proto_market_maker.evaluate, proto_market_maker.optimize, proto_market_maker.data_loader, proto_market_maker.utils, proto_market_maker.database.data_service; print('imports OK')"
```
Expected: prints `imports OK`. (The first command installs `plutus_verify` into the dev venv only — it is needed because `backtest.py`/`evaluate.py` do `import plutus_verify`. It is NOT added to `pyproject.toml`.)

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "refactor: relocate pipeline into src/proto_market_maker, package-qualify imports"
```

---

### Task 3: Expose `main()` in each entry module and verify runs

Wrap each entry module's `if __name__ == "__main__":` body in a `def main():` so the console scripts resolve, keeping a thin guard for `python -m` use.

**Files:**
- Modify: `src/proto_market_maker/backtest.py` (the `__main__` block)
- Modify: `src/proto_market_maker/evaluate.py` (the `__main__` block)
- Modify: `src/proto_market_maker/optimize.py` (the `__main__` block)
- Modify: `src/proto_market_maker/data_loader.py` (the `__main__` block)

**Interfaces:**
- Produces: `proto_market_maker.backtest.main()`, `.evaluate.main()`, `.optimize.main()`, `.data_loader.main()` — each takes no args, returns `None`.

- [ ] **Step 1: Refactor `backtest.py`**

Replace the trailing `if __name__ == "__main__":` line with `def main():`, indent the existing block body unchanged into the function, and append a guard at end of file. Resulting shape:
```python
def main():
    bt = Backtesting(
        capital=Decimal("5e5"),
    )
    # ... existing body unchanged (process_data, run, metrics, prints,
    #     plots, and the `with pv.step("in_sample_backtest") as r:` block) ...
    with pv.step("in_sample_backtest") as r:
        r.metric("sharpe_ratio",     float(sharpe),                    unit="ratio")
        # ... rest of the pv.step block unchanged ...
        r.metadata(seed=2025)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Refactor `evaluate.py`**

Same transform — `def main():` wrapping the existing body (`Backtesting.process_data(evaluation=True)` … through the `with pv.step("out_of_sample_backtest")` block), then:
```python
if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Refactor `optimize.py`**

Same transform. The nested `def objective(trial):` and the `OptunaCallBack`/`study.optimize(...)` calls all move inside `def main():` unchanged, then:
```python
if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Refactor `data_loader.py`**

Same transform — `def main():` wrapping the `required_directories` setup through the `loading_bid_ask(...)` calls, then:
```python
if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Re-sync so console scripts pick up the entry points**

Run:
```bash
uv sync
uv run python -c "import importlib.metadata as m; print(sorted(e.name for e in m.entry_points(group='console_scripts') if e.name.startswith('pmm-')))"
```
Expected: `['pmm-backtest', 'pmm-evaluate', 'pmm-load-data', 'pmm-optimize']`.

- [ ] **Step 6: Verify the in-sample backtest runs end-to-end**

(`data/is/` + `data/os/` CSVs are already present on disk from the earlier Drive download. `plutus_verify` was installed into the dev venv in Task 2.)
Run:
```bash
uv run --with /Users/nadan/algotrade-research/plutus-verify/dist/plutus_verify-0.4.6-py3-none-any.whl pmm-backtest
```
Expected: prints Sharpe/Sortino/MDD/HPR/returns and writes `result/backtest/{hpr,drawdown,inventory}.svg`. No `ImportError` (confirms the old `utils` collision is dead).

- [ ] **Step 7: Verify the out-of-sample evaluation runs**

Run:
```bash
uv run --with /Users/nadan/algotrade-research/plutus-verify/dist/plutus_verify-0.4.6-py3-none-any.whl pmm-evaluate
```
Expected: prints metrics and writes `result/optimization/{hpr,drawdown,inventory}.svg`.

Note: `pmm-load-data` is **not** run here — it needs DB secrets that aren't present locally; its full run is covered by the plutus gate (Task 6) via the Drive data source. `pmm-optimize` runs an Optuna study (minutes) and is exercised by the optimization step; run it manually if you want a local check.

- [ ] **Step 8: Commit**

```bash
git add src/proto_market_maker/backtest.py src/proto_market_maker/evaluate.py \
        src/proto_market_maker/optimize.py src/proto_market_maker/data_loader.py
git commit -m "refactor: expose main() entry points for console scripts"
```

---

### Task 4: Add a minimal test suite

A smoke test that the package imports and one true unit test on a pure helper.

**Files:**
- Create: `tests/__init__.py` (empty)
- Create: `tests/test_smoke.py`

**Interfaces:**
- Consumes: `proto_market_maker.utils.round_decimal`, `proto_market_maker.__version__`.

- [ ] **Step 1: Confirm `round_decimal`'s signature**

Run:
```bash
sed -n '1,60p' src/proto_market_maker/utils.py
```
Expected: shows `def round_decimal(...)`. Note its exact parameters/behavior so the unit test below asserts real behavior (adjust the assertion to match the actual rounding contract).

- [ ] **Step 2: Write the test**

`tests/__init__.py`: empty file.

`tests/test_smoke.py`:
```python
"""Smoke + unit tests for proto_market_maker."""
from decimal import Decimal

import proto_market_maker
from proto_market_maker.utils import round_decimal


def test_package_imports_and_has_version():
    assert isinstance(proto_market_maker.__version__, str)


def test_entry_modules_import():
    import proto_market_maker.backtest  # noqa: F401
    import proto_market_maker.evaluate  # noqa: F401
    import proto_market_maker.optimize  # noqa: F401
    import proto_market_maker.data_loader  # noqa: F401


def test_round_decimal_returns_decimal():
    # round_decimal is a pure helper; assert it returns a Decimal and is
    # idempotent on an already-rounded value. Adjust expected value to the
    # real contract observed in Step 1.
    result = round_decimal(Decimal("1.234"))
    assert isinstance(result, Decimal)
```

- [ ] **Step 3: Run the tests**

Run:
```bash
uv run --with /Users/nadan/algotrade-research/plutus-verify/dist/plutus_verify-0.4.6-py3-none-any.whl pytest -q
```
Expected: all tests PASS. (`--with` covers the `plutus_verify` import pulled in transitively by `proto_market_maker.backtest`.)

- [ ] **Step 4: Commit**

```bash
git add tests/__init__.py tests/test_smoke.py
git commit -m "test: add smoke + unit tests"
```

---

### Task 5: Update the manifest, `.gitignore`, README; remove `requirements.txt`

Point the plutus manifest at the console scripts and the uv-locked env, fix the gitignore landmines, drop `requirements.txt`, and refresh run docs. (`env.install_project: true` depends on the plutus patch; the manifest is still structurally validated here.)

**Files:**
- Modify: `.plutus/manifest.yaml` (`env` block + 3 step `command`s)
- Modify: `.gitignore`
- Delete: `requirements.txt`
- Modify: `README.md` (run instructions)

**Interfaces:**
- Consumes: console-script names from Task 1; metric/artifact contract unchanged.

- [ ] **Step 1: Update the manifest `env` block**

In `.plutus/manifest.yaml`, replace the `env:` block with:
```yaml
env:
  base: python
  python_version: '3.11'
  manager: uv
  lockfile: uv.lock
  install_project: true
  requirements_file: null
  os_packages: []
```

- [ ] **Step 2: Update the step commands**

In `.plutus/manifest.yaml`, change each `command:`:
- `data_collection`:        `command: "pmm-load-data"`
- `in_sample_backtest`:     `command: "pmm-backtest"`
- `out_of_sample_backtest`: `command: "pmm-evaluate"`

Leave the `optimization` step unchanged (no `command`, `verification_mode: artifact_check`). Leave all `inputs`/`outputs`/`expected` paths unchanged.

- [ ] **Step 3: Validate the manifest structurally (no Docker)**

Run:
```bash
/Users/nadan/algotrade-research/plutus-verify/.venv/bin/python -c "from pathlib import Path; from plutus_verify.spec.loader import load_manifest; m=load_manifest(Path('.')); print('manifest OK; commands:', [s.command for s in m.steps])"
```
Expected: `manifest OK` and the three console-script commands printed. (If this errors with an `env.install_project` schema violation, the plutus patch has not landed yet — that is expected; proceed and the Task 6 gate will cover it. Note the outcome in the commit.)

- [ ] **Step 4: Fix `.gitignore`**

In `.gitignore`, remove the `__init__.py` line and the `.python-version` line (both must now be committed). Keep `*.csv`, `.env`, `*venv/`, `__pycache__`, and the `.plutus/` ephemera lines. Resulting top section:
```
__pycache__
.DS_Store
.env
*.csv
*venv/

# plutus-verify ephemera
.plutus/run/
.plutus/results/
.plutus/build/
.plutus/Dockerfile.generated
.plutus/manifest.yaml.draft
.plutus/manifest_TODO.md
```

- [ ] **Step 5: Remove `requirements.txt`**

Run:
```bash
git rm requirements.txt
```

- [ ] **Step 6: Update README run instructions**

In `README.md`, replace any `python backtesting.py` / `python evaluation.py` / `pip install -r requirements.txt` style instructions with:
```markdown
## Setup & run

```bash
uv sync                 # create the env from the committed uv.lock
uv run pmm-load-data    # pull data (needs DB secrets in .env)
uv run pmm-optimize     # optimization study
uv run pmm-backtest     # in-sample backtest
uv run pmm-evaluate     # out-of-sample evaluation
```

Reproducibility is verified with `plutus check .` (see `.plutus/manifest.yaml`).
```

- [ ] **Step 7: Commit**

```bash
git add .plutus/manifest.yaml .gitignore README.md
git commit -m "build: point manifest at uv + console scripts; fix gitignore; drop requirements.txt"
```

---

### Task 6 (GATED — pause for user): Re-bless baseline with plutus and verify

**BLOCKED until the plutus-verify `install_project` patch lands.** Do not start until the user confirms. This is the reproducibility gate per the spec.

**Files:**
- Modify (by `plutus snapshot`): `.plutus/manifest.yaml` (metric `value`s), `.plutus/expected/**`, `result/**`

- [ ] **Step 1: Confirm the patch is in**

Ask the user to confirm plutus-verify now supports `env.install_project`. Re-run the Task 5 Step 3 validation; expect no schema error.

- [ ] **Step 2: Verify (read-only) against the current baseline**

Run:
```bash
/Users/nadan/algotrade-research/plutus-verify/.venv/bin/plutus check .
```
Expected: builds, installs the project, runs all steps. Backtest steps now reach execution (no preflight/import failure). Metric comparisons may FAIL only because the baseline predates the dependency upgrade — that is the cue to re-bless.

- [ ] **Step 3: Re-bless the baseline**

Run:
```bash
/Users/nadan/algotrade-research/plutus-verify/.venv/bin/plutus snapshot .
```
Expected: writes fresh metric `value`s into `.plutus/manifest.yaml`, `.plutus/expected/**`, and `result/**` from the in-container run.

- [ ] **Step 4: Verify green**

Run:
```bash
/Users/nadan/algotrade-research/plutus-verify/.venv/bin/plutus check .
echo "exit: $?"
```
Expected: `exit: 0`.

- [ ] **Step 5: Commit the blessed baseline**

```bash
git add .plutus/expected .plutus/manifest.yaml result
git commit -m "chore: re-bless reproducibility baseline under uv-locked deps"
```

---

## Self-Review

**Spec coverage:**
- src/ layout, package skeleton → Task 1, Task 2.
- pyproject + console scripts + hatchling → Task 1.
- uv + committed lockfile, deps upgraded → Task 1 (Step 4).
- Name-collision removal (utils/, evaluation/) → Task 2 (Step 3).
- Import rewrites → Task 2 (Steps 4–8).
- main() refactor → Task 3.
- price_util.py moved (orphan, kept) → Task 2 (Step 1).
- tests/ → Task 4.
- Manifest env (manager/lockfile/install_project) + console-script commands → Task 5 (Steps 1–2).
- .gitignore fixes (__init__.py, .python-version) → Task 5 (Step 4).
- requirements.txt removed → Task 5 (Step 5).
- README updated → Task 5 (Step 6).
- plutus check/snapshot gate, paused on the patch → Task 6.
- Risk: re-blessed metrics under upgraded deps → Task 6 (Steps 2–3).
- Risk: plutus_verify not a project dep, local-only install → Task 2 (Step 9), Task 3/4 verification steps.

No gaps found.

**Placeholder scan:** No TBD/TODO. The one judgment call — `round_decimal`'s exact assertion — is explicitly gated on inspecting the real signature in Task 4 Step 1, with a concrete fallback assertion.

**Type consistency:** Console-script names, module names, and the `main()` no-arg/`None` signature are consistent across Tasks 1, 3, and 5. Manifest commands match the `[project.scripts]` names.
