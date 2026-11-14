# ForceForge X v0.7 — Genuine 3D Solid FEA

## Why this was added

The v0.5 laboratory stress visualization used 1D Euler–Bernoulli beam FEM
and mapped computed axial stress onto a 3D mesh surface. That remains a useful
well-labeled simplified model, but is NOT a 3D solid finite-element solution.

This version adds an **independent volume-element solver**, without replacing
the source-attributed 1.524 m Hannover laboratory beam, its measured modes,
or the v0.6 eight-corner uncertainty challenge.

## What is actually computed

- Original parametric rectangular **solid**: 120 × 30 × 12 mm.
- Small-strain, linear isotropic 3D elasticity.
- Ten-node quadratic tetrahedral elements (tet10) with 3 displacement DOFs/node.
- Engineering strains (xx, yy, zz, xy, yz, xz), isotropic 6×6 Hooke tensor.
- Four-point tetrahedral Gaussian integration of element stiffness.
- Uniform transverse shear traction on the tip face, consistently integrated
  on quadratic triangular boundary faces (three mid-edge contributions).
- Clamped entire opposite end face.
- Sparse linear-elastic displacement solution, reaction force equilibrium,
  full stress tensor at element center and **von Mises sampled at all four
  Gauss points per element**.
- Piecewise constant external facet rendering of max-Gauss sampled element
  von Mises stress. No interpolation to invented smooth hotspot values.
- Dimensions and thickness can be regenerated as a new 3D volume mesh.
  Optimizer reruns real 3D FE for nine candidate thickness values.

## Independent verification

The 120×30×12 mm specimen with E=210 GPa, nu=0.30, density=7850 kg/m3,
and F=100 N under an assumed transverse uniform end traction:

| Model | Tip movement |
| --- | ---: |
| Independent Euler–Bernoulli cantilever formula PL^3/(3EI) | 0.06349 mm |
| 3D quadratic tetra FEM, 2×2×12 structured hexa subdivisions split to tetrahedra | 0.06237 mm |
| Difference (3D vs beam reference) | −1.8% |

Additional verification: 3D affine patch test, positive volume check,
material law and dimensions validation, root reaction equilibrium, load
linearity, coarse→refined mesh comparison. The quadratic tetra15? **No**:
the element has exactly ten geometric nodes and four integration points.

At F=200 N, displacement target 0.120 mm:

| Output | Original 12mm | Remeshed 13mm |
| --- | ---: | ---: |
| 3D volume-element tip movement (mm) | 0.12473 | 0.09829 |
| Max sampled Gauss-point von Mises (MPa) | 27.74 | 23.63 |
| Solid mass (kg) | 0.33912 | 0.36738 |
| Assumed movement limit | FAIL | PASS |

*Note:* the max at integration points underestimates the outer-fibre stress
at some geometrical boundaries compared with nodal extrapolation. Stress
near the fully clamped end is mesh sensitive. Mesh convergence is needed
for every specific peak quantity, not just displacement.

## CAD and geometry provenance

The modeled rectangular 120×30×12 mm cantilever is **original generated
geometry** for the numerical verification of this solver. No experimental
measurement of this solid was supplied. It is NOT the 1524 mm Hannover beam
nor a manufactured real industrial bracket.

Optional exported STEP/STL reproduces the same simple prismatic solid:

```bash
python -m pip install cadquery
python scripts/export_solid_step.py --thickness 12 --out ./cad-out
```

The current FEM mesher works from parameterized dimensions. It does not yet
**import an arbitrary STEP solid and tetrahedralize its BRep**; this is the
separate V09 goal, and remains open.

## How to run on the team's Mac

```bash
cd ~/ForceForge-AI
git status --short
git fetch origin
git switch --track origin/feature/3d-solid-tet10-v7
python -m pytest -q
python -m streamlit run app.py
```

If branch already exists locally:
`git switch feature/3d-solid-tet10-v7` and
`git pull --ff-only origin feature/3d-solid-tet10-v7`.

The sidebar offers **True 3D solid FEA · tetra10**. Keep the previous
1D laboratory stress view and its robust what-if analysis for comparison.

## Still not included

Arbitrary STEP import and multi-body assembly, real bolt/fillet contact,
elastic–plastic material response, CFD, thermal FSI, dynamic vehicle loads,
real physically measured solid deflections, safety or service certification.

This scope is deliberate: verification of a fully volumetric solver comes
before adding complex CAD or nonlinear multi-physics claims.
