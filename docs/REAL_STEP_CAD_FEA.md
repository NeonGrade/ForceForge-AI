# ForceForge X v0.8 — Real STEP → Solid FEA → CAD Revision

## Physical source and licensing/provenance

NIST AM-Bench 2022 AMB2022-01 individual bridge-structure specimen, DOI **10.18434/mds2-2607**. The NIST Public Data Repository publishes a STEP geometry file, a matching STL file and SHA-256 checksum. Data are publicly available; cite the NIST dataset and confirm all downstream usage rights/conditions on its landing page.

- Dataset: https://doi.org/10.18434/mds2-2607
- Official STEP: https://data.nist.gov/od/ds/ark:/88434/mds2-2607/CAD_Geometry/AMB2022-01-AMMT-PartCAD.STEP
- Official checksum: above URL plus .sha256
- Published artifact is an additively manufactured IN718 bridge with fine geometry and measured AM residual strain/deformation data.
- **This project currently does not compare its new static-force results against measured NIST static loading data.** The proposed clamp, transverse force, material numbers and assumed yield threshold are illustrative.

## User workflow

The new sidebar link **Real STEP → 3D FEA / CAD redesign** opens the optional CAD module.

1. Select the real NIST STEP (button downloads original from NIST), upload a permission-cleared STEP, or choose a **newly generated** L bracket with three drill holes.
2. Verify coordinate units (mm by default), choose tetra mesh target, check that the imported CAD solid volume matches the tetrahedral mesh within 20% and no tetrahedron is degenerate. More mesh convergence is required for quantitative local stresses.
3. Select the base-to-tip axis. Nodes on its minimum planar face are fixed; a transverse force is distributed as a consistent quadratic face traction over the maximum planar face. **These are not inferred physical fixtures.**
4. Compute 3D small-strain isotropic elastic FEM using 10-node quadratic displacement tetrahedra and four volumetric Gauss points. Show full stress tensor-derived sampled von Mises field on external tetra faces.
5. Change the CAD geometry (editable sample bracket 8 / 10 / 12 / 14 mm vertical web, or upload your actual revised STEP), reimport the **different** STEP, remesh and re-solve. Both before/after plots use a common absolute MPa color range.
6. Export both STEP geometry and a JSON record that includes source hashes, assumptions, exact mass, deflection, and stress.

## Install/launch on Apple Silicon Mac

Stop Streamlit with Control+C. Keep local uncommitted code; inspect git status before switching.

```bash
cd ~/ForceForge-AI
git status --short
git fetch origin
git switch --track origin/feature/real-step-import-fea-v8
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install 'gmsh>=4.12,<5'
python -m pytest -q
python -m streamlit run app.py
```

If local branch already exists use `git switch feature/real-step-import-fea-v8 && git pull --ff-only`.

For Gmsh library errors on macOS, install the current native Gmsh package or wheel for your architecture; do not delete earlier functional Python environments. If the institutional network blocks NIST, download the official STEP in a browser and use Upload your STEP instead.

Local optional source acquisition:

```bash
python -m scripts.fetch_nist_step
```

It records the exact SHA-256 and optionally validates NIST's own checksum. The NIST file is NOT committed to the source repository.

## Numerical method, what is / is not solved

- OpenCASCADE reads actual STEP BRep surfaces. Gmsh produces **straight-sided linear tetra** approximation of the CAD domain; each mesh is geometrically faceted. Midside nodes are then added to give tet10 **quadratic displacement approximation**, not curvilinear isoparametric CAD geometry.
- Full 3D isotropic 6×6 elasticity tensor and three displacements per node.
- 4-point tetrahedral Gauss quadrature for K, von Mises max sampled over 4 integration points.
- Quadratic face consistent tractions; sparse SPD displacement solution, reaction force residual and modeled member mass.
- CAD volume vs tetrahedral volume error, mesh positivity / shape proxy, raw source hash guard.
- **A max sampled quadrature-point von Mises stress is not necessarily the true maximum surface/fillet stress**, particularly near fully fixed edges. Mesh convergence, material plasticity and fixture modeling are prerequisites for actual structural approval.
- No contact between bodies, multi-body assembly solve, thermal CFD, plasticity, actual measured strain data or real-life certification.
- Gmsh FEM runs on Mac are capped at 5,000 tet4 input elements to bound memory/time. CAD models that exceed it are **explicitly rejected**, never truncated.

## Existing tools preserved

Prior functionality is in the same repository and has NOT been replaced:
- Real experimental modal beam calibration and held-out frequencies.
- Source-attributed 1D beam FEM with 3D stress mapping.
- Eight-corner robust optimization under uncertain load/E/thickness.
- v0.7 independently verified parametric 3D tetra10 specimen.
- Cross-industry Building / Industrial / Automotive, Advanced Structural Lab and legacy ML surrogate.

## Engineering acceptance gates for this PR

1. Basic full existing pytest regression succeeds in GitHub Actions on Python 3.11 + 3.12.
2. Separate Gmsh integration test imports a true STEP of a prismatic solid, generates volume elements, computes reactions and compares mass; also checks a bracket geometry revision.
3. Actual NIST file acquired and source SHA verified; geometry volume/mesh tested with a realistic mesh budget. If its thin walls defeat the 5k cap, explicitly report this limitation and do not fake stress plots.
4. User confirms Mac Streamlit UI and three actions: original STEP → FEA → revised STEP → re-solve.
5. Before any safety-related use, independent geometry/mesh convergence, real material and load/fixture characterization and experimental correlation are mandatory.

## Demo speech in one sentence

'We import a **real CAD file** or a parameterized engineering bracket, create a genuine 3D volume mesh, run a 3D elastic solve, then change the STEP geometry and independently remesh/recompute—while recording which engineering assumptions remain unverified.'
