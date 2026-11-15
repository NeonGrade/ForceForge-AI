## Experimental 3D Solid FEA — stable HTTP view (feature branch)

The 3D work is **not part of the existing 2D truss physics**. It uses a
Gmsh tetrahedral mesh and a new static 3D linear-elastic finite element
solver. To avoid the recurring Streamlit `Connection error` during native
meshing, launch the existing lightweight Python HTTP server, with Gmsh/FEA
running in a crash-isolated subprocess:

```bash
git switch feature/step-solid-fea
git pull --ff-only origin feature/step-solid-fea
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-3d.txt
python web_server.py
```

- **Single engineering workspace (all six tools):** http://127.0.0.1:8000/
- **3D Solid FEA in the same shell:** http://127.0.0.1:8000/#solid3d
- **Solver health:** http://127.0.0.1:8000/api/health

The unified browser keeps all five original 2D tools and the new 3D mode in the same engineering shell. An old /solid3d URL redirects to the integrated sixth tool. The HTTP 3D page has no Streamlit/WebSocket dependency. It includes a
rotatable colored surface, interactive deformation display, STEP solid
import (maximum 4 MB), bounded tetrahedral meshes and explicit child process
failure/timeout reporting. Original 2D features remain unchanged.
Legacy `python -m streamlit run app_3d.py` also delegates native meshing to
the isolated worker, but the HTTP view is the preferred live demo.

For limitations, exact physics assumptions, and acceptance tests, see
[3D Solid FEA](docs/3d-solid-fea.md). Multi-solid STEP import does **not**
implement mechanical contact or tie constraints; CFD, mesh convergence,
nonlinear mechanics and AI-guided CAD modification remain future work.

# ForceForge AI 2.0 — Physics-Verified Generative Truss Design

Hack the Nest 2026 | Eastern Michigan University | Computer Aided Engineering

A working Python hackathon starter. It generates simple 2D trusses, solves the
linear-elastic finite-element equations, searches robust designs under bounded
uncertainty, trains an ML surrogate on FEA results, and **always** FEA-checks
ML-recommended candidate designs. Optional OpenAI API enables structured
natural-language requirement interpretation; the offline path works without it.

## 1. Quick Start (macOS)

```bash
git clone https://github.com/NeonGrade/ForceForge-AI.git
cd ForceForge-AI
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
python demo_cli.py
python -m streamlit run app.py
```

Open the local Streamlit URL printed in the terminal, usually
`http://localhost:8501`.

**No API key is required**. OpenAI integration is opt-in. If you have a key,
set `OPENAI_API_KEY` in your local shell environment. Never commit `.env` or
keys to GitHub.

## 2. Current MVP Features

- `forceforge/physics.py`: 2D pin-jointed linear-elastic **axial bar/truss** element
  (not a bending beam), assembly of global `K`, static `Kuu=F`, reactions,
  axial stress, axial force, mass, simple pinned-pinned Euler buckling screening.
- `forceforge/design.py`: 3 fixed stable topologies (`Triangle`, `Fan`, `Warren-2`).
- `forceforge/robust.py`: exhaustive multi-scenario geometry/area search (8
  corner combinations: nominal/+load, nominal/-E, nominal/-area); yield,
  displacement and ideal buckling utilization, Pareto options.
- `forceforge/sensitivity.py`: finite-difference local elasticities for geometric and area changes.
- `forceforge/surrogate.py`: RandomForestRegressor learns worst-case check
  utilization from FEA labels. A held-out test estimates interpolation error;
  proposals are **re-solved with FEA** before accepting.
- `forceforge/agent.py`: deterministic language parser, optionally OpenAI
  structured outputs via Pydantic. Parsed requirements still require engineer
  validation.
- `app.py`: interactive Streamlit app with charts, challenge test, CSV export.
- `tests/`: reference benchmark and system tests.

## 3. Verified analytical benchmark

Triangle nodes `(0,0), (2,0), (1,1)` in metres, with pin at left and a
vertical roller at right, a `1000 N` downward load at apex, equal members
`E = 200 GPa` and `A = 100 mm²`. The exact small-strain truss solution has:

- bottom chord force `+500 N` (tension),
- each diagonal `-707.10678 N` (compression),
- apex vertical displacement `-0.095710678 mm`,
- two vertical support reactions `+500 N` each.

The automated tests compare FEA output with these values and check global
force equilibrium.

## 4. Robust engineering optimization

Objective: minimize nominal mass `rho * Σ A_i*L_i`.
For every corner scenario `s`, require:

- `|sigma_i,s| <= yield_strength / yield_safety_factor`
- `max nodal translation <= allowed displacement`
- `|N_i,s,compression| <= Euler_Pcr_i,s / buckling_safety_factor`

The round solid member section is an explicit simplifying assumption:
`I = A²/(4*pi)` and ideal pin-pin buckling `Pcr = pi²*E*I/L²`.
The same area is used for all members. It is a screening optimization,
**not** a commercial-grade truss optimization or structural certification.

## 5. AI/ML implementation and limitations

FEA is the source of engineering labels. Machine learning approximates the
mapping from topology, height and member area to scenario constraint
utilizations. It is not a replacement for physics. The default hold-out test
contains unseen design rows but can share a topology with training examples;
that is **not** evidence of generalization to new structure families.

Validation now groups identical topology/height/area combinations into the same
holdout partition, reports a training-mean baseline MAE, and keeps proposals
inside the sampled height/area bounds and observed topologies. This remains an
interpolation check under the current engineering requirements; it does not
validate new topologies, materials, or changed load cases. Changing sidebar
requirements clears previous ML recommendations.

Future work for a more defensible ML claim:
- Group-based holdout by height intervals or by topology, with appropriate
  domain-matching feature encoding;
- cross-validation / learning curves / comparisons with a simple baseline;
- uncertainty-aware candidate rejection and active-learning next-candidate choice.

Optional LLM calls interpret a design request into **bounded**, typed values.
The model cannot write directly into a solver state or declare a structure safe.
API failures use the deterministic offline parser with an explicit fallback
message. Offline parsing supports m/cm, N/kN and mm (plus 米/牛顿/千牛/毫米),
rejects conflicting recognized values, and lists defaults for omitted values.
Review all extracted values before entering them in the sidebar.

## 6. Team split

- Engineering lead (Yusen): physics.py, tests, robust scenario integrity.
- AI/optimization lead: surrogate.py, agent.py, CLI integration.
- Product lead: app.py, documentation, competition submission and demonstration.

If there is only one experienced programmer: keep all P0 tasks assigned to
that person; team members who are less experienced can run test matrices,
collect review evidence, and prepare demo/Devpost assets.

## 7. Demo sequence (90 seconds)

1. Set span, force, allowable deflection and material.
2. Show FEA force/stress/displacement and verified reference test.
3. Run robust search; compare mass and buckling/displacement utilization.
4. Press `Challenge My Design`: increase applied force and reduce E/area.
5. Show ML surrogate hold-out metrics and FEA-reverified suggestion.
6. Explain numerical and physical limitations.

## 8. Known critical limitations

- 2D, linear static, geometrically small displacement, identical material,
  ideal pin joints, point load at fixed prescribed node.
- Only three predefined stable topologies, not arbitrary CAD geometry.
- Euler member buckling under **ideal** conditions, no effective-length
  calibration, local buckling or joint failure.
- No plasticity, fatigue, real manufacturing constraints, imperfection or
  true physical testing; simulated examples must not be described as measurements.
- Nominal material tables are examples, not certified values.
- Some form of true physical experimentation and professional review is
  required before practical engineering safety decisions.

## 9. Audited challenge benchmark (November 14, 2026)

For comparable topology screening, **all three topology families now apply
the same vertical point load at (span / 2, height)**. Earlier experimental
results that placed Warren-2's load at its bottom-center node are not
comparable across topologies and must not be used in the final presentation.

With default 2 m span, steel, 1000 N and a 2 mm displacement limit:

| Scenario range | Feasible / tested | Lowest-mass feasible candidate | Mass | Max utilization |
| --- | ---: | --- | ---: | ---: |
| Up to +20% load, E/area -10% | 100 / 144 | Triangle, h=0.80 m, A=180 mm² | 6.445 kg | 0.8491 |
| Up to +60% load, E/area -10% | 89 / 144 | Triangle, h=0.80 m, A=230 mm² | 8.235 kg | 0.6934 |

The first design FAILS under the second scenario envelope: ideal buckling
utilization is 1.1321. The challenged redesign is 27.8% heavier. These are
repeatable numerical checks for simplified pinned trusses—not laboratory
measurements, proof of arbitrary-topology optimality, or structural certification.

## 10. Official technical references

- SciPy: https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.differential_evolution.html
- scikit-learn RandomForestRegressor: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestRegressor.html
- Streamlit: https://docs.streamlit.io/develop/api-reference/charts/st.plotly_chart
- OpenAI Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs

