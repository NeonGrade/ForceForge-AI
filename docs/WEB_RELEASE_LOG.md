# ForceForge Engineering Workspace II — Release Log

**Date:** 2026-11-14
**Version:** Workspace II / integrated web main site
**Compatibility baseline:** `NeonGrade/ForceForge-AI` `main` at `a6d0b53ddc9cdcc3e118d7d9cd235bab7670f250` (confirmed before development)

## Scope

- Added a no-build responsive browser workspace with a permanent full-screen structural viewport and internally scrollable configuration/result inspectors.
- Added desktop and mobile layouts, collapsible settings and results, compact status/metric dock, keyboard shortcuts and export controls.
- Added real finite-element truss rendering for Triangle, Fan and Warren-2. Preserved world X/Y axes, numbered nodes, supports, grid, load arrow, dimensions, exaggerated deformation and axial tension/compression coloring.
- Added mouse hover and click inspection of arbitrary member and node states, plus pan, zoom, model fitting and display modes.
- Added a standard-library HTTP API that imports and invokes the existing repository's Python physics, optimization, ML and structured requirements modules.
- Integrated scenario-based robust evaluation and 144-candidate grid search, Pareto comparison, local sensitivity, 1.60x challenge envelope, FEA-verified redesign and FEA-verified ML proposals.
- Kept the existing `app.py` Streamlit entry point and all original solver files untouched.

## Validation results

- Python API: `7 passed` (`tests/test_web_api.py`).
- Reference axial forces, deflection and support equilibrium matched published project benchmark.
- Default optimization reproduced 100/144 feasible with 6.445 kg best design.
- +60% applied load challenge reproduced buckling utilization 1.132 and an 8.235 kg successful redesign.
- Surrogate grouped holdout metrics and 12 FEA-verified recommendations returned.
- Browser: Chromium scripted interactions passed for Analyze, hover, member click, Optimize, Apply Best, Challenge, Redesign, ML Verify, AI Brief, Export.
- Responsive browser checks passed at widths 1440, 1280, 900 and 430 px with no outer page vertical scrolling or uncaught JavaScript errors.

## Known limitations

- The truss solver supports only predefined 2D stable topologies and idealized pin-jointed axial-bar FEA, not full CAD structural certification.
- Local development server is not production-authenticated or publicly deployed.
- Browser screenshots in the package are QA artifacts; the application is interactive and rendered by JavaScript at runtime.
- The frontend must be opened through `python3 web_server.py` for live calculations; opening `index.html` directly as a file does not connect to the solver.

## User-facing start command

```bash
git pull origin main
python3 web_server.py
```

Then browse `http://127.0.0.1:8000`.