# Unified 2D + 3D Spatial Workspace (review build)

Run `python3 web_server.py` to open **http://127.0.0.1:8000**. From the centered workspace selector choose **Truss engineering** (2D axial FEA) or **3D Spatial Studio** (true 3D solid, Real CAD, and measured laboratory scene). Both are served at the same local origin and port, with direct in-page switching and unchanged numerical solvers. Install `gmsh>=4.12,<5` for real STEP/Gmsh workflows. The 3D integration requires the unified review branch; 2D-only checkouts continue to run without a 3D backend. See [the unified interface guide](docs/UNIFIED_SPATIAL_WORKSPACES.md).

---

# ForceForge AI — Engineering Workspace II

**Hack the Nest 2026 · physics-verified truss design · browser-based engineering studio**

Workspace II is a no-build, single-page web interface that runs on the existing ForceForge Python solver. It **does not replace** the original Streamlit app, `app.py`; both entry points can coexist. All engineering numbers displayed by the workspace originate in `forceforge/physics.py`, `forceforge/robust.py`, `forceforge/surrogate.py`, and `forceforge/agent.py`, not JavaScript approximations.

## Start on macOS

From the checked-out 2D Spatial Parity branch (or the unzipped package):

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 web_server.py
```

Open <http://127.0.0.1:8000> in Safari or Chrome. On macOS, you can also run `open http://127.0.0.1:8000` in a second Terminal window. Press **Control+C** in the server window to stop it.

If installing from the standalone ZIP instead of GitHub, unzip it, open Terminal in the extracted folder, and use the same commands starting from `python3 -m venv .venv`.

No OpenAI API key, Node.js, npm, React, or build step is required. OpenAI-assisted requirements interpretation is optional and only used when a server-side key is configured and the engineer enables it.

## Workspaces

| Mode | Purpose | Source of engineering evidence |
| --- | --- | --- |
| **Analyze** | Explore three supported truss topologies, hover/click members and nodes, inspect displacement, forces, stress, reactions and screening utilization | Python FEA and 8-scenario robustness checks |
| **Optimize** | Screen 144 topology/height/section combinations, review feasible alternatives and Pareto designs, apply the best result, export CSV | Full FEA evaluations across 8 scenarios per candidate |
| **Challenge** | Raise the force multiplier up to 1.60, include elastic modulus and section reduction, detect failed constraints, re-optimize | Expanded FEA load-envelope check and new robust grid search |
| **ML Verify** | Train a Random Forest surrogate on FEA-generated labels, report held-out errors and re-solve proposed candidates | Grouped-split interpolation diagnostics plus FEA verification |
| **AI Brief** | Interpret a typed engineering brief, review proposed inputs and apply valid values | Deterministic parser; optional server-side LLM, never LLM-calculated stresses |

The 2D interface now shares the graphite / alabaster / ion-lime visual system of 3D Spatial UI v0.2.1. The primary scene fills the viewport, while engineering settings and full results open as dismissible floating sheets. Force and member-area control handles are anchored to the model and can be clicked or dragged horizontally. The result marker opens the FEA data drawer. All five original analysis workflows remain available in the compact bottom rail.

The grid, X/Y axes, span/height dimensions, central force vector and idealized support constraints remain visible. Hover a truss member or node for instant physical state; click to inspect the real numerical fields. The viewport supports wheel zoom, drag pan, and fit reset. On narrow screens, the settings and results panels become toggleable overlays, and the outer page does not scroll. The separate 3D Studio is linked from the centered scene selector and needs its own server on port 8765. See [2D Spatial Parity](docs/2D_SPATIAL_PARITY.md) for design notes and fidelity limits.

### Keyboard controls

`1–5` navigate workspaces. `F` fits the model. `Esc` clears a selection/closes side overlays. Mouse wheel zooms, drag pans, hover inspects, click selects.

### JSON/CSV export

The top Export button downloads a JSON engineering study with inputs, FEA output and completed checks. Analyze exports member results to CSV; Optimize exports the FEA candidate database to CSV.

## HTTP API

The no-dependency Python HTTP entry point (`web_server.py`) uses standard-library `ThreadingHTTPServer`. It serves `/`, `/style.css`, `/app.js`, `/spatial-theme.css`, and `/spatial-shell.js` and accepts JSON requests:

- `GET /api/health`
- `POST /api/solve`: nominal structural FEA plus robust screen
- `POST /api/search`: grid-search designs, best feasible, Pareto options and sensitivity
- `POST /api/challenge`: expanded load-case assessment and optional FEA redesign
- `POST /api/ml`: surrogate validation and FEA re-verification
- `POST /api/interpret`: bounded structured design-brief interpretation
- `POST /api/sensitivity`: finite-difference local sensitivities

The browser sends structured inputs; server validates material, dimensions, loads and uncertainty ranges. Requirement-changing edits invalidate stale optimization/ML outputs, and asynchronous browser results are ignored if their inputs changed while the request was running.

## Test

```bash
python3 -m pytest -q tests/test_web_api.py
```

The test suite checks the reference triangle benchmark (member forces, apex displacement and equilibrium), robust optimization benchmark, expanded challenge buckling failure, optimized redesign, ML proposal verification, parsing and bounds validation.

## Verified default numerical case

Default input: 2.0 m steel truss span, 1,000 N top-center vertical load, 2.0 mm displacement limit, 2.0 safety factors, +20% load, −10% E and −10% section.

| Check | Result |
| --- | --- |
| Grid search | 100 / 144 feasible designs |
| Least-mass robust design | Triangle, height 0.80 m, section 180 mm² |
| Nominal mass | 6.445 kg |
| Normal worst-case utilization | 0.849 |
| Expanded +60% challenge | Original fails ideal Euler buckling, utilization 1.132 |
| FEA-verified redesign | Triangle, height 0.80 m, section 230 mm², mass 8.235 kg |

These are **numerical computations** within an idealized 2D pin-jointed axial truss model. They are not experimental measurements or certification. The solver excludes joint behavior, bending, fatigue, local buckling, out-of-plane instability, geometric/material nonlinearity and manufacturing defects. The nominal materials and circular-bar assumption are illustrative.

## Coexistence with the legacy app

The new files are additive: `web_server.py`, `web/`, `tests/test_web_api.py`, and `docs/WORKSPACE_II.md`. The old Streamlit UI remains available:

```bash
python3 -m streamlit run app.py
```

## Network and deployment

The default server listens on `127.0.0.1:8000` and is meant for **local use on the development Mac**. It is not a production application server: it has no user authentication, HTTPS proxy, deployment secrets integration or rate limiting. Do not expose the development server publicly without a separate production deployment/security review.
