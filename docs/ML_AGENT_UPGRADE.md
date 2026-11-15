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
parameters**. In **Ask an engineering question · English-first Agent**, enter, for example:

`Force 0.25 kN, mesh 12 mm, web 10 mm, E 200 GPa`

1. **Understand English request** distinguishes a parameter-change request from
   a question about the completed result. It does not mesh or solve.
   No absent parameter is replaced by a 2D truss default.
2. Review the values. **Confirm parameters and run FEA** validates that the source,
   material and other current inputs still match the preview before running.
3. **Results** contains the deterministic evidence-grounded CAD review. The same
   review is included in exported CAD audit JSON. It never calls an LLM or sends
   CAD data to a third party.

## English-first questions and requests

English engineering questions are the primary acceptance path. Examples:

| Request or question | Behavior |
| --- | --- |
| What if I increase the load to 300 N? | Preview 300 N; require confirmation before solving |
| Increase the load by 20 percent. | Derive from the current load, preview and confirm |
| Double the load. | Derive from the current load; still enforce input bounds |
| Use a 12 mm mesh and make the web 10 mm thick. | Understand value-before-noun phrasing |
| Why is this design failing? | Explain assumed-yield ratio and numerical evidence gaps |
| What is the current displacement and stress? | Quote completed FE results and units |
| Has the mesh converged? | State the actual mesh-study status; do not invent convergence |
| How can I make this bracket lighter? | Suggest the independently solved CAD revision workflow |
| Is this safe for real-world use? | Explain the evidence limitations, without certifying safety |

Answers are in English and reference the server-held completed result, exact CAD
and input context. The browser cannot supply invented numerical results for the
Agent to repeat. Changed inputs require a fresh solve before numerical questions
can be answered. Asking a question does not trigger FEA or silently change inputs.
This is an offline assistant for the listed engineering topics, not an unrestricted
engineering chatbot. Unsupported questions receive a clarification prompt.

Chinese labels and units remain compatible but are not the primary demo path:
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
