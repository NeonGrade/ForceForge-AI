# ForceForge UI V3 — Engineering Studio

A dedicated, engineering-first interface for ForceForge AI 2.0. It uses the existing physics, optimization, requirements-parser, and ML modules without changing their numerical methods.

## Launch on macOS

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
python -m streamlit run app_ui_v3.py
```

The original `app.py` remains available. V3 is a separate entry point, not a replacement for the team baseline.

## Information architecture

- **Overview:** real-time screening pass/fail, four priority KPIs, and the truss viewport.
- **Structure Analysis:** deformed geometry, signed axial stress, nodal displacement, ideal-member buckling utilization, and support reactions. Detailed numerical tables are collapsed by default.
- **Optimization:** 144-candidate FEA scenario search, worst-case utilization versus mass scatter, feasible Pareto frontier, topology comparison, current-versus-recommended comparisons, local sensitivity, and CSV export.
- **AI Assistant:** natural-language requirements with review-before-apply, grouped-holdout surrogate validation, and FEA rechecks of recommended designs.

Each page shares one set of design inputs and a live engineering inspector. Changing engineering requirements clears cached optimization and ML results to avoid presenting stale conclusions.

## Engineering boundaries

The backend models idealized 2D pin-jointed axial trusses using small-strain linear elasticity. Euler buckling is a preliminary ideal pinned-member screen. No physical testing, joint certification, local buckling, fatigue, imperfections, nonlinear response, or structural safety certification is provided.

Values in the viewport come from the solver, not from invented example figures. Deformation is exaggerated for visualization and the scale factor is displayed. The robustness screen checks eight uncertainty combinations; ML recommendations are not accepted without repeat FEA checks.

## UI workflow and team integration

Work on the `ui/elysian-progress` branch and open a pull request into `main` only after review. Keep source content, UI text, documentation, comments, and commit messages in English. Do not commit `.env` files or API keys.

The auto-sync helper watches `app_ui_v3.py` in addition to the standard UI folders. It requires a local Mac installation, an authenticated Git client, and an awake computer; uploading code through the ChatGPT GitHub connector is not equivalent to continuously watching local changes.
