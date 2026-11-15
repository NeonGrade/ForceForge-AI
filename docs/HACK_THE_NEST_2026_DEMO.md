# Hack The Nest 2026 — ForceForge X demonstration and honest scope

**This document applies only to the existing PR #16 branch**
`feature/stress-local-validation-v11`. Do not substitute the old-main
Streamlit 3D prototype or remove previous modes.

## The problem

AI can propose 3D designs instantly, but those proposals cannot be trusted
from appearance alone. Structural loads, mass penalties, moving local stress
maxima and poor mesh convergence must be evaluated by physical solvers before
an engineer uses the design.

## The working contribution to demo

1. **Real CAD**: original drilled L-bracket generated as STEP BRep.
2. **Real 3D FEM**: tetrahedral Gmsh volume mesh + independent quadratic
   tetra10 structural solution, support reaction equilibrium and von Mises
   stress at Gauss quadrature points.
3. **Failure insight**: sampled von Mises, tip displacement, stress hotspots,
   boundary-condition warnings and honest local mesh sensitivity screens.
4. **v1.1 dual-hotspot validation**: simultaneous Gmsh local-size fields at
   two frozen physical XYZ locations, separate FE solves, fixed-region
   volume-weighted mean and P90 comparisons. Both Mac and Linux work.
5. **CAD Design Copilot (hackathon feature)**: under 8/10/12/14 mm
   parametric constraints, an optional LLM chooses proposal priority and
   offers qualitative rationale. The algorithm then independently generates
   and re-solves EVERY available alternative STEP, accepts only genuine
   physical FEA outputs, and finds the lightest candidate meeting user-set
   modeled constraints. Without a usable API key, it is **explicitly labeled
   a rules-based exhaustive search, not AI-generated CAD**.
6. **Provenance**: original and revised STEP SHA-256, input material/load,
   3D mesh quality/reaction balance, numerical outcomes and exportable JSON.
   Results are not reused after the physical inputs change.

## 100-second live script (show the working product, not code)

1. **0–12 sec** — "Most AI-assisted CAD tools stop at a plausible shape.
   ForceForge tests whether the revised physical geometry actually behaves
   better under an assumed load."
2. **12–25 sec** — On **Real STEP → 3D FEA / CAD redesign**, show the
   original 8 mm drilled bracket at 250 N, real 3D mesh/stress contours,
   and baseline tip movement ~0.0358 mm.
3. **25–65 sec** — Use **Design Copilot** with illustrative limits:
   displacement **0.015 mm**, sampled stress **16 MPa**, mass increase
   **40%**. Click "Generate CAD proposals + verify every candidate with
   real 3D FEA". Say whether this run used an **actual LLM API** or
   **rules fallback**; do not call the latter AI. Point out 3 real STEP
   regeneration/FEA jobs and the evidence table.
4. **65–80 sec** — Show selected 12 mm bracket (reference manual revision
   previously measured **+20.0% mass, 0.0358→0.0116 mm tip motion,
   18.7→11.7 MPa sampled stress** under a particular mesh/load). These
   are reference results, not a promise that every new mesh gives identical
   values; read the live solver output.
5. **80–95 sec** — Show fixed physical hotspot validation:
   macOS reference **744→951 tetra**, maximum 7 mm sphere mean change
   ~**2.30%**, maximum P90 change ~**0.61%**, moving peak drift
   ~**0.556 mm**. Explicitly label this a **preliminary numerical screen**.
6. **95–100 sec** — One sentence: "AI suggests, CAD regenerates,
   FEM verifies, and we refuse to label unconverged stresses safe."

**Network or native worker fallback**: record a genuine, unedited live
session as backup. If the API is unavailable, disable the LLM toggle and
explain the working deterministic search. If a 3D solve fails or timeouts,
keep the previous valid traceable outputs, report the failure, and show the
recorded demo. Never replace a real solver call with fabricated metrics.

## QA gates before presenting

- [ ] Fresh repo checkout of the exact PR #16 commit on the demo Mac.
- [ ] `python -m pytest -q` and GitHub Linux/macOS CI green.
- [ ] App loads without automatically launching Gmsh; original Real STEP
      solver runs only after pressing the button.
- [ ] Run three independent candidate CAD → Gmsh → tetra10 FEA jobs
      in Design Copilot; every STEP SHA differs from baseline.
- [ ] With **no API key**, UI says rules-based and does not claim LLM use.
- [ ] With an actual API key, UI says `LLM_PRIORITIZED_WITH_REAL_FEA`
      only if structured output is valid. A hallucinated CAD value is rejected.
- [ ] Changing the force, source geometry, material, mesh size, design
      objective or modeled limits hides stale recommendations.
- [ ] 3D contour rotation/zoom, side-by-side color scales, downloads.
- [ ] Repeated solve, back/forward navigation, refresh and 5-minute idle
      without lost connection; test in the actual Mac browser.
- [ ] Live demo narrated and recorded; screenshot evidence backed up.
- [ ] Devpost project draft, team members and repository attribution
      verified before the event's official submission cutoff.

## Scope still missing (not allowed to imply it already works)

- Full Navier–Stokes CFD on imported STEP flow domains, thermal fluid coupling.
- General multi-part 3D assembly with contact, bolts, joints and preloads.
- Autonomous arbitrary BRep CAD editing: current Copilot modifies only
  a controlled bracket parameter, not an arbitrary STEP assembly.
- Plasticity, validated fatigue life, true peak stress mathematical
  convergence, verified material/yield values and physical bench tests.
- Cloud deployment/guaranteed uptime independent of the laptop.

## Competition eligibility and originality — resolve with the organizer

The official event describes a 24-hour hackathon where teams develop a
working project. The **ForceForge repository includes earlier research,
tooling and pre-event functionality**. Before submitting this project for
a prize, verify the event's exact reuse/disclosure rules with an organizer.
Disclose existing solver code/benchmark work and clearly identify the
features developed **during** the allowed event window (including the
dual-hotspot work, Copilot and integration tests, if they were completed
during that window). Do not claim the entire repository was started at
the hackathon if that is not true. Disclose any AI coding assistance,
library use and external data sources as required by the event.

## Submission copy (draft, adapt to actual demo)

**ForceForge X — The AI-to-CAD-to-FEA Verification Loop**

"CAD generation is fast, but physical trust is expensive. ForceForge X
lets engineers propose controlled geometry changes, regenerates real STEP
solids, performs independent 3D tetrahedral finite-element analyses, and
compares mass, deformation and stress under explicit constraints. Its
Design Copilot can use an optional language model to prioritize modifications
but cannot fabricate structural outcomes. Numerical evidence, source hashes
and design changes are exportable, and local stress hotspots are checked at
fixed physical locations across new meshes. Our prototype explicitly
reports unresolved contact, CFD, experiment and safety-certification gaps."

**Primary demo mode**: original physical L-bracket → candidate suggestions
→ changed STEP → independent quadratic FEM → parameter trade-off →
conservative evidence report.

This is an educational/research prototype, not a structural approval tool.
