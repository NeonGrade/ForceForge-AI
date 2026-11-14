# ForceForge X v1.0 — Mesh-Sensitivity Evidence

## The decision this solves

A colorful 3D von Mises plot is insufficient to show that the answer is
numerically trustworthy. With a single grid, the value may depend heavily
on tetrahedral resolution, especially around clamps, notches and bolt holes.

This version adds a **user-triggered three-level numerical sensitivity
experiment** on the exact same STEP CAD input, material, fixture and load.
It is compatible with v0.9's crash-isolated macOS Python 3.13 runtime.

### Before/after workflow

1. On the **Real STEP → 3D FEA / CAD redesign** page, choose the NIST
   original STEP (source-traceable but static loads not measured), generated
   drilled L-bracket, or import your own permission-cleared single solid.
2. Press **Run CAD import + 3D FEA**. This imports STEP geometry, meshes
   the real volume and computes 3D linear-elastic tetra10 deformation and
   Gauss-point stress in a **bounded subprocess**, not the Streamlit server.
3. Open **Mesh-sensitivity evidence · 3 independent volume meshes**.
   Nothing runs merely from opening this section or changing a control.
4. Press **Run mesh-sensitivity study (2 additional FE solves)**.
   The baseline result is reused; two *new* isolated 3D FE solves are run
   using coarser and finer Gmsh mesh targets.
5. A table and plot report actual tetra count, quadratic-node count,
   CAD-to-mesh volume difference, minimum shape quality proxy,
   tip displacement, sampled von Mises peak, strain energy,
   and reaction-equilibrium residual.
6. Results are discarded for display if CAD SHA-256, material, mesh,
   load or fixture differs from the inputs now shown.
7. Download the evidence JSON for reproducibility.

With the default 12mm mesh, the planned target edge lengths are
**15 mm, 12 mm and 10 mm**. The user does not have to recompute the
baseline. Actual element counts (not target lengths) are used to verify
whether refinement truly happened.

## Engineering meaning of the screen

The tool reports one of:

- `PRELIMINARY_GLOBAL_DISPLACEMENT_STABILITY`: the two finest global
  displacement estimates differ by <=3% (heuristic) and the latest
  absolute change has not grown by more than 10% relative to the earlier
  refinement. This is **not** formal grid convergence, independent
  experimental validation or certification.
- `MESH_SENSITIVE`: the displacement response still depends visibly on
  grid resolution.
- `INCONCLUSIVE_REFINEMENT`: actual tetra counts did not grow when
  a smaller target mesh size was requested.
- `INSUFFICIENT_REFINEMENT`: actual element counts increased by less
  than 10% between steps.
- `INVALID_MODEL_EVIDENCE`: one of the runs failed the minimum volume,
  positive quality proxy, elastic energy or global force-equilibrium
  checks.

It *separately reports* percentage change in the **peak sampled von
Mises stress** between meshes. Global displacement consistency
**cannot** prove stress convergence at holes, hard support corners,
contact interfaces, material discontinuities or singular loads.
The mesh geometry is straight-sided, even though the displacement
interpolation is quadratic. Curved surfaces are geometrically faceted.

No new material certificates, independent static measurements, bolt
preload, nonlinear contact, thermal CFD, plasticity or professional
certification have been added. The NIST manufacturing residual-strain
measurements must not be misrepresented as independent validation for
the user-assumed 50-250 N static transverse tests.

## Stable macOS runbook

Stop Streamlit with Control+C. Before switching branches inspect changes
with `git status --short`. Never delete untracked team research.

```bash
cd ~/ForceForge-AI
git status --short
git fetch origin
git switch --track origin/feature/mesh-evidence-v10
source .venv/bin/activate
python -m pip install -r requirements.txt 'gmsh>=4.12,<5'
python -m pytest -q
python -m streamlit run app.py --server.fileWatcherType none
```

If your local branch already exists:

```bash
git switch feature/mesh-evidence-v10
git pull --ff-only origin feature/mesh-evidence-v10
```

To check the result without cloud download links: run the page locally at
http://localhost:8501/Real_STEP_Engineering.

## Acceptance tests

- Pure scientific/numerical checks for mixed CAD hashes, mixed loads,
  insufficient actual mesh refinement, false stability and bad residuals.
- Real Gmsh drilled STEP at three target resolutions, three independent
  volume meshes and true 3D tetra10 solves, bounded by v0.9's 1,400-input
  tetra limit.
- Streamlit AppTest ensures the mesh study starts only on user click and
  returns three evidence rows. Page load itself still runs zero CAD/FEA.
- Full existing modal/robust/ML/true-3D regression suite remains green.

v1.0 is a separate draft feature branch. Do **not** merge to main
before user Mac visual acceptance.
