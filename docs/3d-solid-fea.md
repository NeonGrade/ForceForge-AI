# 3D Solid FEA: experimental milestone

Run the original verified 2D application with `python -m streamlit run app.py`.
The separate experimental 3D app is `python -m streamlit run app_3d.py`.

## Installation
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-3d.txt
python -m pytest -q
python -m streamlit run app_3d.py
```

## Implemented
- Gmsh OpenCASCADE native box and uploaded STEP solid import.
- Explicit CAD coordinate unit selection: mm, metre or inch.
- 4-node linear tetrahedral, isotropic, small-strain static 3D FEA.
- Fixed minimum-axis face; nodal point-force distribution on maximum-axis face.
- Per-element von Mises and averaged nodal color interpolation, deformation display.
- Force balance; constant-strain patch test.

## Explicitly not supported
- No assembly contact, tie interfaces, or automated BC detection: disconnected components may lead to singular systems.
- No surface pressure, thermal/CFD, plasticity, nonlinear kinematics, or fatigue.
- No CAD modification/parameter-search feedback loop.
- No convergence study yet: mesh refinement must be checked before using any reported stress.
- Stress singularities at ideal clamps/load nodes and smoothed nodal colors can mislead.
- The solver is intended for education and demonstration; not design safety decisions.

## QA gate before claiming completion
1. Install optional native Gmsh dependencies on the deployment host.
2. Execute pytest and the UI on macOS.
3. Test one CAD STEP solid and a multi-solid STEP file with clearly defined interfaces.
4. Compare a beam displacement/stress case against beam theory and a second validated solver.
5. Run mesh refinement; review reactions and singular/ill-conditioned cases.
6. Check UI stability and upload limits, then merge the feature branch after review.

This feature intentionally uses a separate entrypoint; it does not alter existing 2D workflows.
