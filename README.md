## Hack The Nest 2026 — Live CAD Design Copilot (experimental)

**One workflow, one existing app**: Real STEP CAD → Gmsh volume mesh → real
quadratic tetra10 FEA → bounded AI proposal / rules fallback → **new STEP
solids** → independent FEM rechecks → trade-off visualization and
traceable downloads. All original ForceForge X v1.1 modules remain.

### Run the upgraded Real STEP demo

```bash
git fetch origin
git switch feature/stress-local-validation-v11
git pull --ff-only origin feature/stress-local-validation-v11
source .venv/bin/activate
python -m pip install -r requirements.txt 'gmsh>=4.12,<5'
python -m pytest -q
python -m streamlit run app.py --server.fileWatcherType none
```

In **Real STEP → 3D FEA / CAD redesign** select the original 8 mm drilled
bracket under the default 250 N transverse load and click **Run CAD import +
3D FEA**. Immediately below the real 3D stress visualization, find
**Step 2B · Design Copilot**. Default illustrative criteria are maximum
tip displacement 0.015 mm, sampled peak stress 16 MPa and mass increase
40%. Click **Generate CAD proposals + verify every candidate with real 3D
FEA** to regenerate and analyze all three alternative STEP thicknesses.
Download a resulting STEP and the complete evidence JSON.

If a language model is desired, explicitly enable the LLM toggle and
provide an API key locally (or set `OPENAI_API_KEY` in the local shell).
AI only proposes a **bounded order and qualitative rationale**. Without a
valid model result, the page explicitly labels the exhaustive search
`RULE_BASED_FULL_SEARCH`. **No API key** is placed in reports/commits;
**no stress or safety value comes from an LLM**.

See [Hack The Nest 2026 demo and product/eligibility checklist](docs/HACK_THE_NEST_2026_DEMO.md)
and [Physical hotspot reliability evidence](docs/LOCAL_STRESS_RELIABILITY.md).

**Unimplemented:** true STEP fluid-domain CFD, general multipart
contact/tie, arbitrary AI CAD BRep regeneration, plasticity, verified
fatigue, proven global peak convergence and physical certification. Model
constraints are illustrative, not design approval.

---

# ForceForge X v1.1 — Reproducible Local Stress Validation

The 3-mesh STEP study now distinguishes **global displacement stability**, **fixed-region volume-weighted von Mises stability**, and **moving peak stress sensitivity**. Stable displacement no longer appears as a global engineering "PASS" when the local peak stress is unresolved. The original screenshot's 17.52% stress difference is correctly calculated from **18.6683 → 22.6327 MPa**.

The tetra10 solver retains all real integration-point physical locations, stress and Gauss weights. The **Run two local hotspot refinements** button uses actual Gmsh BRep remeshing near the measured peak position and independently reruns 3D FEM in isolated Mac-safe processes under identical loads; an ideal-clamp stress singularity is explicitly rejected as an engineering verification.

[Read the physical stress-reliability specification](docs/LOCAL_STRESS_RELIABILITY.md) · [Stable Mac setup](docs/STABLE_CAD_RUNTIME.md)

```bash
cd ~/ForceForge-AI
git status --short
git fetch origin
git switch --track origin/feature/stress-local-validation-v11
source .venv/bin/activate
python -m pip install -r requirements.txt 'gmsh>=4.12,<5'
python -m pytest -q
python -m streamlit run app.py --server.fileWatcherType none
```

If the branch already exists locally: `git switch feature/stress-local-validation-v11 && git pull --ff-only`.

All previous modes, the genuine NIST STEP source, true tetra10 SOLID FEA, CAD redesign, ML and robustness screens are retained. Numerical mesh checks do **not** replace actual hardware fixture/material correlation or structural safety certification.

---

# ForceForge X v1.0 — Source-Locked Mesh Evidence

The same **actual STEP CAD** is now checked at **three independently generated 3D tetra mesh resolutions**. ForceForge reuses the active FEM solution, runs exactly two additional crash-isolated solves, and reports how actual element counts, global displacement, strain energy, sampled local von Mises, volume preservation and reaction balance vary with mesh refinement.

**Importantly:** three-mesh comparisons are a *preliminary numerical sensitivity screen*, **not** proof that local peak stress has converged or that an engineering product is certified safe.

**New user action:** open the **Real STEP → 3D FEA / CAD redesign** page, click **Run CAD import + 3D FEA**, then expand **Mesh-sensitivity evidence · 3 independent volume meshes** and click **Run mesh-sensitivity study (2 additional FE solves)**. Nothing computationally expensive runs on page load.

[3D mesh evidence / engineering limits](docs/MESH_SENSITIVITY_EVIDENCE.md) · [Stable Mac runtime](docs/STABLE_CAD_RUNTIME.md)

Development branch: `feature/mesh-evidence-v10`. Earlier NIST geometry, modal benchmark, thermal/joint, robust optimization, ML and CAD redesign modules are preserved.

---

# ForceForge X v0.9 — Stable CAD Studio

**New: click-to-run real STEP → tetra10 3D FEA → CAD redesign**, with native Gmsh and sparse FEA isolated in bounded Python subprocesses so a native worker failure does not automatically terminate the Streamlit server.

The previous v0.8 CAD tools, real published NIST geometry, experimental modal benchmark, robust optimization, industry demos and ML tools are retained.

[Stable CAD runtime / Mac setup and recovery](docs/STABLE_CAD_RUNTIME.md)

```bash
cd ~/ForceForge-AI
git status --short
git fetch origin
git switch --track origin/feature/stable-cad-runtime-v9
source .venv/bin/activate
python -m pip install -r requirements.txt 'gmsh>=4.12,<5'
python -m streamlit run app.py --server.fileWatcherType none
```

If the local branch already exists: `git switch feature/stable-cad-runtime-v9 && git pull --ff-only`.

In the sidebar choose **Real STEP → 3D FEA / CAD redesign**. Page opening should not invoke Gmsh or solve FEM. Click **Run CAD import + 3D FEA** to compute the current case, then **Re-mesh revised CAD and re-run 3D FEA** to compare a changed real STEP.

---

# ForceForge X v0.8 — Real STEP → 3D Solid FEA → CAD Redesign

**This is the current development branch, preserving all earlier numerical, real modal, robust, ML and cross-industry modules.**

- Import a **real published NIST STEP** (AMB2022-01 / DOI 10.18434/mds2-2607), or upload a single-solid STEP.
- Audit the STEP BRep against an actual Gmsh 3D tetrahedral mesh (CAD solid volume, mesh volume, source SHA-256, mesh limit).
- Solve isotropic small-strain 3D FEA with genuine **quadratic tetra10 displacement elements**, and display Gauss-point von Mises stress and reaction residuals.
- Revise an actual CAD solid and independently remesh/recompute. A parametric L-bracket with bolt holes is an **original demonstration design**; it is not NIST experimental geometry.
- NIST original specimen geometry is genuine. Our **static loading is assumed**, and is NOT independently validated by the NIST additive-manufacturing experimental data.

## Mac terminal

Stop Streamlit with Control+C, then check for uncommitted work before switching branches:

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

Already have that local branch? Instead use `git switch feature/real-step-import-fea-v8 && git pull --ff-only`.

Open the new left-sidebar **Real STEP → 3D FEA / CAD redesign** page. For immediate testing, use the editable drilled L-bracket; for genuine published source geometry download the NIST original directly on the same page. Large/thin-wall source files may exceed the 5,000-tet compute limit, which is flagged without invented results.

Technical, licensing and engineering limitations: [Real STEP CAD and FEA guide](docs/REAL_STEP_CAD_FEA.md).

---

# ForceForge X v0.5 — CAD Surface, FE Stress and Redesign

Video-inspired **interactive engineering design** without simulated or fabricated solver claims.

Run on your Mac (Ctrl+C to stop the previous Streamlit server):

```bash
cd ~/ForceForge-AI
git fetch origin
git switch --track origin/feature/cad-simulation-loop-v5
python -m pip install -r requirements.txt
python -m pytest -q
python -m streamlit run app.py
```

Existing local branch? `git switch feature/cad-simulation-loop-v5` instead.

On the existing **real laboratory benchmark homepage**, click **3D stress / failure / redesign** in the sidebar.

* Apply an assumed lateral tip force to the documented 1524 mm steel beam and rotate the 3D stress surface.
* See bending stress in **MPa**, predicted tip displacement in **mm**, support reactions, and a clearly user-defined 2 mm displacement limit.
* Press **Find the lightest design that meets the modeled limits**. The app changes the beam section thickness and runs **new finite element solutions** for every candidate.
* The side-by-side before/after comparison exposes mass, displacement and stress; experimental provenance is documented.

**Unambiguous fidelity labels:** The source beam and its published *modal frequencies* are real measured laboratory data. Static loading and stress are **not** measured here. Stress is computed with a 1D Euler–Bernoulli bending finite-element model and recovered over a **3D CAD-dimension surface reconstruction**. It is *not* a three-dimensional solid element model, CFD, transient engine simulation, contact/plasticity or structural certification.

The previously working v0.4 real experimental modal calibration, v0.3 industry explorer, FEA, robust optimization and ML tools remain in the same application.

For the next engineering-grade steps (licensed high-complexity STEP assembly, quality-checked 3D solid mesh, elastic/plastic FEA, genuine CFD, CAD regeneration and independent validation), see [Video Reference Implementation](docs/VIDEO_REFERENCE_IMPLEMENTATION.md).

**Experiment attribution:** Thurn et al., *Wind Energy Science* (2026), DOI: 10.5194/wes-11-3359-2026; raw measurements and Abaqus source DOI: 10.25835/lyav246d.


---

# ForceForge X v0.4 — Real Laboratory Benchmark + Interactive CAD

**Current working focus: real physical data, a documented 3D specimen, and a reproducible FEA/experiment comparison.** The previous simulated-only three-industry scenarios remain available as the **Industry Explorer**; none has been misrepresented as experimentally validated.

## Launch on the team Mac

Stop any running Streamlit with Ctrl+C. Then:

```bash
cd ~/ForceForge-AI
git fetch origin
git switch --track origin/feature/real-lab-benchmark-v4
python -m pip install -r requirements.txt
python -m pytest -q
python -m streamlit run app.py
```

If this branch is already present locally, run `git switch feature/real-lab-benchmark-v4` instead.

### 90-second demonstration

1. Open the homepage. **Rotate the real-dimension reconstructed steel beam** and inspect published sensor locations at 0.393–1.462 m.
2. Change the base rotational stiffness slider: the 2D finite-element generalized eigenvalue solution updates all 3 natural frequencies and the rendered 3D mode shape.
3. Compare against **real measured laboratory frequencies** (1.569, 10.389, 29.619 Hz) and published Abaqus FE results (1.698, 10.775, 30.590 Hz).
4. Click **Calibrate using measured Mode 1**. One equivalent support stiffness parameter is fitted using only 1 physical reference; Modes 2 and 3 are evaluated as independent holdout measurements.
5. Download the **STEP/STL** reconstruction; open the traceability panel to access the actual institutional original Abaqus `.inp`/`.cae` and raw `.mat` data.
6. Open **Industry Explorer** to show how the same platform's FEA workflows can extend to buildings, industrial brackets and automotive suspension. These three scenarios remain *simulation-only*.

### Model/measurement pedigree

- Physical source: J. Thurn et al., *Wind Energy Science*, 11, 3359–3376 (2026), DOI **10.5194/wes-11-3359-2026**, CC BY 4.0.
- Raw physical data and original Abaqus model: Thurn, Jonscher & Rolfes (2025), DOI **10.25835/lyav246d**, CC BY 3.0.
- `assets/benchmark/*.step` and `*.stl` are **our simplified reconstructed geometry**, made from published 1524×30×5.2 mm physical beam dimensions and 5.0 mm gauge regions. We do **not** claim they are the author's original mesh, sensor assembly or measured geometry survey.
- `data/benchmark/*.csv` contains only the published numerical reference values, not simulated measurements.
- `forceforge/modal_benchmark.py` is our own 2D consistent-mass Euler–Bernoulli FE solver; it does not implement the author's Timoshenko or sensor/magnet mass assumptions.
- User-adjustable E and density are engineering assumptions, *not* certified test properties. A first-mode fitted stiffness is a model parameter, not a measured joint property.

**The validated comparison is modal frequency correlation on a specific laboratory beam—not fatigue-life qualification or structural safety certification.** Time-domain comparison requires original `.mat` signal channel mapping and properly matched units.

For implementation, reproduction and licensing, see [Real Lab Benchmark Guide](docs/REAL_LAB_BENCHMARK.md) and [Geometry/Data Provenance](docs/BENCHMARK_CAD_PROVENANCE.md).

---

# ForceForge X — Engineering Decision Studio (v0.3)

**One product problem, three industry examples:** What happens when a structure faces a higher load, and which design changes improve its modeled performance?

The primary app now guides a non-engineer through **Choose a problem → Challenge the conditions → Find an FEA-verified improvement**. Every numerical candidate is re-solved with the corresponding physical solver. The original advanced FEM, robust truss optimizer, machine-learning surrogate, and AI requirement-parser are preserved in separate Engineering Workspace pages rather than deleted.

## Launch the new version (Mac)

Stop the previous Streamlit instance with Ctrl+C, then:

    cd ~/ForceForge-AI
    git fetch origin
    git switch --track origin/feature/decision-studio-v3
    python -m pip install -r requirements.txt
    python -m pytest -q
    python -m streamlit run app.py

If this branch already exists locally, use `git switch feature/decision-studio-v3` instead of the track command. Expected test count for this version: **48** (local verification; GitHub CI/Mac acceptance may still be pending).

The browser opens a single decision workflow with three examples:
- **Building:** Steel roof-truss load path and ideal axial/buckling limits
- **Industrial:** Machine bracket, semi-rigid connection, second-order frame response
- **Automotive:** Planar suspension-link *proxy* and projected road loads

**Illustrative model screening does not establish actual safety, code compliance or certification.** Domain-specific loads, joint geometry, materials, manufacturing and physical test evidence are missing. The interface exposes these evidence gaps.

For traceability see [Product Scope](docs/PRODUCT_V3.md), [Version History](docs/CHANGELOG.md), [90-Second Demo](docs/JUDGES_DEMO.md).

---

## Previous technical reference (preserved for engineering work)

# ForceForge AI 2.0 — Physics-Verified Generative Truss Design

Hack the Nest 2026 | Eastern Michigan University | Computer Aided Engineering

A working Python hackathon starter. It generates simple 2D trusses, solves the
linear-elastic finite-element equations, searches robust designs under bounded
uncertainty, trains an ML surrogate on FEA results, and **always** FEA-checks
ML-recommended candidate designs. Optional OpenAI API enables structured
natural-language requirement interpretation; the offline path works without it.

## 1. Quick Start (macOS)

```bash
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

Future work for a more defensible ML claim:
- Group-based holdout by height intervals or by topology, with appropriate
  domain-matching feature encoding;
- cross-validation / learning curves / comparisons with a simple baseline;
- uncertainty-aware candidate rejection and active-learning next-candidate choice.

Optional LLM calls interpret a design request into **bounded**, typed values.
The model cannot write directly into a solver state or declare a structure safe.

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

## 9. Official technical references

- SciPy: https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.differential_evolution.html
- scikit-learn RandomForestRegressor: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestRegressor.html
- Streamlit: https://docs.streamlit.io/develop/api-reference/charts/st.plotly_chart
- OpenAI Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs

## Cross-industry unified platform (development branch)

The `Cross-Industry Platform` Streamlit page provides one shared model request
schema, solver orchestration, typed output, numerical evidence records, and
traceable JSON export for **three deliberately simplified examples**:

| Domain | Current solved case | Key physical omissions |
| --- | --- | --- |
| Building | Steel truss / hypothetical point loads / bar-buckling screen | Roof-specific adopted code, snow/wind/seismic loads, bracing and joints |
| Industrial | Planar beam bracket, rotational joint spring, thermoelastic, P–Δ | Anchor bolts, contact, shock history, actual bracket geometry |
| Automotive | Planar triangular suspension-link surrogate and fatigue screen | 3D ball joints/bushings, multi-axis strain history, actual OEM data |

The application includes a **verification/evidence inventory** separate from
solver execution and an exportable trace ID. Every generated example is
explicitly **NOT CERTIFIED**. Code checks, contact FEA and actual fatigue
qualification are not currently implemented, and cannot be represented by an
AI-generated approval stamp.

For demo: `python -m streamlit run app.py` → sidebar page **Cross Industry
Platform**. The previously working main FEA and Advanced Structural Lab pages
are retained. See `docs/CROSS_INDUSTRY_PLATFORM.md` for model scope and tests.
