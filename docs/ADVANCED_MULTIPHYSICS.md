# ForceForge X — Advanced Structural Mechanics Expansion

**Development branch:** `feature/advanced-structural-physics`
**Status:** computational modules + Streamlit page implemented; analytic/unit tests
passed locally; graphical page on the team's Mac is **not yet browser-verified**.

## 1. Coherent engineering use case

**Thermo-mechanical fatigue and reliability of a lightweight support bracket
with a semi-rigid mounting joint.**

We want to screen a design under combined:
- lateral/transverse mechanical loading;
- compressive pre-load and elastic geometric-stiffness/P–Δ effects;
- uniform temperature change and restrained thermal stress;
- support joint rotation compliance;
- user-supplied S–N data and cyclic stress exposure.

Geometry and stress visualization are based on a 2D beam/frame idealization;
local bolt contact, weld stresses, weld toes, fillets and local 3D geometry are
NOT captured. A frame model cannot certify local bolted-joint safety.

## 2. Implementation

### Euler–Bernoulli frame FEA
`forceforge/advanced_frame.py` has 3 DOF per node:
`[u_x, u_y, theta_z]`. Each 2-node element produces the classical
`6x6` stiffness, including axial and bending terms in the local frame,
transformed into global coordinates. Outputs: displacements, nodal reactions,
local member end forces, nominal extreme-fiber stress for a solid round section,
total mass and matrix conditioning.

### Semi-rigid support joint
Rotational spring `k_theta` (N m/rad) added at the support rotational DOF.
No bolts, contact, stick-slip, friction, local contact stresses or material
stiffness degradation. A true connection design requires an independently
characterized moment-rotation law or explicit 3D contact model.

### Thermoelasticity
Uniform temperature rise `Delta T` produces equivalent axial thermal nodal
loads. A separately prescribed thermal curvature parameter supports simple
cross-section temperature-gradient effects. There is **no heat equation solver
or temperature-dependent material law** at present.

### P–Δ analysis
An iterative linearized beam-column geometric stiffness `K_g(N)` is used to
estimate second-order response, including compressive softening. This is a
**small-displacement second-order approximation**: NOT Newton–Raphson
elastoplastic finite-rotation analysis. Nonconvergent calculations are
explicitly flagged.

### Fatigue
`forceforge/fatigue.py` computes a Goodman-corrected stress amplitude,
power-law S–N predicted cycle count and Palmgren–Miner linear cumulative
damage for an input load spectrum. The material S–N curve MUST be specific
to actual material, section and connection detail. These are screening
calculations, not certified life predictions.

## 3. Verification matrix

| Independent reference | Assertion |
|---|---|
| Cantilever transverse tip force | delta = P L^3 / (3 E I); theta = P L^2 / (2 E I) |
| Semi-rigid support spring | delta = P L^3/(3EI) + P L^2/k_theta |
| Freely expanding bar | delta = alpha DeltaT L; thermal support axial reaction ≈ 0 |
| Axially restrained heated bar | N = - E A alpha DeltaT |
| Compressed cantilever + lateral force | second-order transverse displacement magnitude > first-order |
| Unrestrained single beam rigid-body mechanism | singular/ill-conditioned system rejected |
| Fatigue example | at 50 MPa fully alternating, Sref=100 MPa @ 1e6 cycles, slope 3: Nf=8e6, D=0.125 for 1e6 cycles |
| Tension mean-stress correction | Goodman example yields D ≈ 0.2963 |

**Local test outcome:** 8 new tests passed; integrated with 14 earlier checks,
22 passed. Repeat on the demo Mac before claiming local device verified.

## 4. How to run

After fetching this branch, existing main app stays available. Run:

```bash
git fetch origin
git switch feature/advanced-structural-physics
python -m pip install -r requirements.txt
python -m pytest -q
python -m streamlit run app.py
```

The new **Advanced Structural Lab** appears as an additional Streamlit page.
Return to `main` with `git switch main` (stop Streamlit first).

## 5. Real nonlinear model, if time allows

Use **OpenSeesPy** as a specialist solver rather than reimplementing an
elastoplastic Newton iteration under hackathon time pressure.

- 2D `ndf=3` frame;
- nonlinear `forceBeamColumn` + fiber section (steel `Steel01` or `Steel02`);
- `Corotational` geometric transformation where compatible;
- `zeroLength` rotational material/spring joint;
- stepwise load control, documented convergence test and max iterations;
- extract force-displacement curves and residuals.

OpenSees official docs:
- https://opensees.github.io/OpenSeesDocumentation/user/manual/model/elements/forceBeamColumn.html
- https://opensees.github.io/OpenSeesDocumentation/user/manual/model/geomTransf/Corotational.html
- https://openseespydoc.readthedocs.io/en/stable/src/ZeroLength.html

This nonlinear integration is **planned but not included** in the above code.
OpenSeesPy platform support varies; verify on the exact macOS / Python setup.
The available macOS arm64 packaging claims newer support, but never risk
breaking the working main branch during the hackathon.

## 6. Thermal and fluid extension choices

**Priority A: sequential thermal→structural coupling.** Implement a 1D
steady-state or transient thermal conduction solution with convection/
radiation boundary conditions; transfer temperatures to frame thermal
strain, thermal bending, and fatigue operating cases. Mesh convergence and
energy balance must be checked.

**Priority B: fluid loading without full CFD.** Apply a documented drag/pressure
correlation as distributed mechanical loads, with pressure uncertainty.
This is NOT a Navier–Stokes CFD or FSI solver.

**Deferred: CFD / conjugate heat transfer / fluid-structure interaction.**
Use OpenFOAM for validated conjugate heat-transfer or CFD cases with
independent mesh quality checks; partitioned FSI needs physically consistent
interface transfer and coupling convergence. Adding an untested Fluid
tab would not improve model credibility.

## 7. Design-code credibility package vs certification

A `compliance_evidence.json` or report may include:
- model version hash, input units, material pedigree, loads and support cases;
- element formulation and assumptions;
- independent verification benchmarks and solver tolerances;
- mesh convergence/error estimates if using a mesh-refined model;
- uncertainty sampling and safety margin tables;
- selection of an actually applicable design code;
- explicit unresolved requirements, missing tests and third-party review.

**Never label this as 'ASME/AISC/FAA certified' without specific standards
compliance evidence and required independent approval.**
ASME V&V 10 guides solid mechanics verification, validation and uncertainty
quantification; it does not issue automatic safety certification.

https://www.asme.org/codes-standards/find-codes-standards/standard-for-verification-and-validation-in-computational-solid-mechanics/2019

## 8. Team assignments

- CAE lead: verify frame benchmarks, boundary conditions, section assumptions.
- AI lead: train multi-fidelity surrogate on verified solver outputs and quantify
  false-safe predictions; exact FEA always makes final feasibility decision.
- UI/Product lead: advanced page, clear failure-mode explanations, demo recorder,
  competition submission.

**Demo priority:** show joint stiffness and thermal effects, test compressive
load amplification, then explain predicted fatigue damage with documented
hypothetical S–N data. Never imply physically calibrated lifetime.
