# Context-bound ML and CAD evidence Agent

This integration combines engineering PR #15 (`0cddd5c`) and Spatial UI PR #13
(`6b5b851`). It retains the worker isolation from PR #14 and all older solver,
modal, industry and truss workflows. These parent PRs are still development
branches; this integration is not a release or structural qualification.

## Run

```bash
git fetch origin
git switch --track origin/codex/ml-agent-upgrade
python3 -m pip install -r requirements.txt 'gmsh>=4.12,<5'
python3 studio_server.py
```

Open the printed localhost address. Select **Real CAD**, then open **Advanced
parameters**. In **Design brief · offline Agent**, enter, for example:

`Force 0.25 kN, mesh 12 mm, web 10 mm, E 200 GPa`

1. **Preview extracted parameters** returns bounded, structured changes without
   meshing or solving. No absent parameter is replaced by a 2D truss default.
2. Review the values. **Confirm parameters and run FEA** validates that the source,
   material and other current inputs still match the preview before running.
3. **Results** contains the deterministic evidence-grounded CAD review. The same
   review is included in exported CAD audit JSON. It never calls an LLM or sends
   CAD data to a third party.

Chinese labels and units are supported, for example:
`载荷250牛顿，网格12毫米，腹板厚度10毫米，弹性模量200GPa`.
Conflicting, unsupported-unit and out-of-range inputs are rejected. Imported
geometry requires a revised STEP; the Agent cannot fabricate a web-thickness
edit or remove the worker limits. CAD generation and FEA use bounded isolated
subprocesses, including when initiated from Spatial UI.

For the Streamlit toolkit, run `python3 -m streamlit run app.py`. The Real STEP
page provides input preview and a JSON design review. The three-mesh study is
opt-in and the review only uses evidence matching the exact CAD, load and
baseline solve. No study means **NOT_EVALUATED**, not a convergence claim.

## Task coverage

- **F10/F11:** Truss labels carry exact Requirements and hashes of the current
  physics/design/robust source files. Missing or changed context requires fresh
  labels and retraining. Conflicting labels for identical designs are rejected.
  The Workbench offers duplicate-design holdout or complete height-group holdout,
  reports MAE/R² against a training-mean baseline, and exports context and metrics.
- **F12:** Screen 300 candidates within fitted feature bounds, then recompute
  shortlisted candidates with FEA. Export both predicted and actual utilization,
  absolute error, an FEA-verification flag and the requirements identifier.
- **F13:** Preserve the optional OpenAI-backed truss parser and improve adjacent
  Chinese/scientific-number parsing. CAD proposals are offline, typed, partial,
  bounded and require explicit confirmation against their original input context.
- **F14:** Critiques derive only from completed tetra10 FE outputs. CAD source,
  material, mesh baseline and load must match. Reaction, mesh quality, assumed
  yield and mesh-sensitivity gaps are stated separately. JSON includes a review
  identifier and assumptions.
- **F18/F19:** Original ML and advanced tools stay available. Integration tests
  exercise HTTP preview/confirmation without a solver, exact FE review values,
  stale-context rejection and the original numerical/UI regression suite.

## Limits

The truss surrogate is **not** trained for arbitrary STEP or tetra10 solids.
Whole-height holdout does not validate new topologies or materials. A global
three-mesh stability screen does not establish local notch-stress convergence.
Published modal measurements and NIST geometry do not validate a hypothetical
static load case. Live OpenAI calls and final team demo-Mac acceptance remain
separate checks.
