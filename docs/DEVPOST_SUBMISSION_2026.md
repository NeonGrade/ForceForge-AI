# Hack The Nest 2026 — ForceForge X Devpost draft packet

Prepared for **Nov 14, 2026 11:xx PM ET** draft deadline. Official event:
https://hack-the-nest.devpost.com/

- Draft cutoff: Sun Nov 15, 2026, **12:00 AM ET** (Saturday midnight).
- Final cutoff: Sun Nov 15, 2026, **12:00 PM ET**.
- Demo: Sun 1:15–2:15 PM ET.
- Every submission needs public repo, demo video <=3 minutes, teammates,
  AI usage disclosure and track selection.
- **Eligibility red flag:** official rules say all project code is written
  during the event. Existing ForceForge foundation predates the event;
  disclose it explicitly and confirm permitted code reuse with an organizer.
- Official rules: https://hack-the-nest.devpost.com/rules

## Devpost fields

**Name**: ForceForge X

**Tagline**: Describe a mechanical product. Generate real CAD. Test designs with actual FEA and rotating-flow CFD.

**Project URL / source code (public; use exact branch, main is older)**:
https://github.com/NeonGrade/ForceForge-AI/tree/feature/stress-local-validation-v11

**Technical validation branch head at preparation**: f1396ff4813fc03419d53c961110c1fc7bb062ab

**Main track**: Future of Intelligence (OpenAI, with Exa).

**Opt-ins available if team criteria are met**:
Department of Computer Science Track; Best Beginner (majority first-time).
The formerly listed GameAbove College of Engineering track is not visible
on the currently published Devpost official event track list.

**Built with**: Python, Streamlit, Gmsh, OpenCASCADE, STEP CAD, SciPy,
NumPy, OpenFOAM v2512, pimpleFoam, AMI rotating mesh, VTK, Docker,
Pydantic, Plotly, GitHub Actions, optional OpenAI API.

## Full project description — paste into Devpost

### Inspiration

Generative AI can make a mechanical design look convincing in seconds. But
a polished 3D model cannot tell an engineer where it deforms, how stresses
redistribute, or what happens when real airflow passes rotating blades.
Engineering decisions need reproducible numerical evidence beyond a
plausible-looking rendering.

### What it does

**ForceForge X is a natural-language-to-CAD-and-physics engineering
prototype.** A user describes a supported mechanical product in ordinary
English or Chinese. The system extracts explicit dimensions and physical
analysis intent into a typed engineering schema, builds a real STEP solid,
then routes supported physics tasks to independent numerical solvers.

Our working workflows include:

- **Natural-language CAD:** a parametric drilled L-bracket, conceptual
  wall-mounted fan assembly, hollow shaft/sleeve, and rectangular mounting
  plate with optional four through-holes. Each generator produces an actual
  OpenCASCADE STEP file, not a mesh screenshot.
- **True structural FEA:** the supported bracket workflow builds a real
  Gmsh tetrahedral mesh, performs quadratic tetra10 finite-element analysis,
  and reports displacement, sampled von Mises stress, reaction equilibrium,
  mass and design constraints.
- **Physics-checked redesign:** the CAD Design Copilot can prioritize
  a bounded set of bracket thickness alternatives with an optional LLM.
  Each candidate is independently regenerated and solved; missing API
  access falls back to a clearly labeled deterministic exhaustive search.
- **Rotating flow CFD:** a user-generated fan rotor can be extracted from
  its STEP as real STL geometry, inserted into an OpenFOAM reference-room
  rotating mesh, and simulated using transient pimpleFoam with sliding AMI.
  We validate and display real velocity U and kinematic pressure p fields.
- **Continuous 3D rotor playback:** source-STL blades rotate continuously
  in the browser at the solver's specified RPM. A verified real CFD
  snapshot appears behind the blades. Intermediate blade animation
  positions are kinematics; they are explicitly **not invented CFD frames**.

Users can inspect 3D outputs, compare evidence, and download generated
CAD or offline visualization files.

### How we built it

The web application uses Streamlit and Plotly. Pydantic schemas restrict
product families, units and inputs. Gmsh/OpenCASCADE produces true STEP
solids in isolated workers. NumPy/SciPy handle numerical structural
calculations. Docker runs the official OpenCFD/OpenFOAM v2512 environment
with dynamic meshes and pimpleFoam. Python VTK reads real VTK polyhedron
cells and extracts solver-derived U/p values. GitHub Actions tests the
parser, native CAD, FEA, OpenFOAM job recovery, the custom-source rotor,
and browser Play/Pause looping.

For traceability, CAD exports, solver logs and recovered CFD outputs
carry SHA-256 provenance; unsupported physics tasks remain blocked.

### Challenges we ran into

The main difficulty was integration, not rendering. Real rotating-mesh
CFD can complete its time stepping and still fail during field export.
On an ARM64 Mac, OpenFOAM foamToVTK with polyhedral decomposition crashed.
We restored already computed U/p snapshots using Python VTK instead of
claiming that a failed postprocessor meant the physics solve had failed.
We also addressed duplicate jobs, stale status overwrites, container
cleanup and looped 3D browser animation.

### Accomplishments

We linked ordinary-language product specifications to real STEP geometry,
preserved genuine FEA and CFD provenance, and ran custom STEP-derived
rotor geometry through a real rotating AMI OpenFOAM case. Independent
CI checks on Linux and macOS validated native CAD and FEA paths, while
Chromium browser tests verified continuously updating 3D rotor vertices,
Play/Pause controls and a full animation loop.

### What we learned

Engineering AI is only credible if its outputs remain tied to geometry,
loads, boundary conditions and actual numerical solvers. We learned to
separate an LLM's design suggestion from independently verified physics,
and an animated rotor's geometrical motion from genuinely computed
time-dependent fluid data.

### What's next

Expand the registered parametric product catalog; add validated flow
domains that include the actual wall, grille and mount; connect fluid
tractions to structural supports; improve mesh convergence and
reproducibility; and move beyond a local Mac/Docker prototype toward a
reliably deployed engineering workspace.

### AI assistance and reuse disclosure

We used ChatGPT/OpenAI coding assistance for implementation, debugging,
test generation and documentation. The optional design-language model
helps prioritize **bounded** CAD options; engineering numbers are
produced by solvers, not by language models.

ForceForge X builds on an experimental engineering codebase and solver
infrastructure that existed before this hackathon. During this event,
we expanded the natural-language product pipeline, integrated actual
STEP-derived rotating-fan OpenFOAM CFD, improved recovery and continuous
3D playback, and added regression testing. We disclose the pre-existing
foundation and are confirming eligibility with organizers.

### Technical scope

ForceForge X is an educational/research prototype, not a certified
mechanical design package. The custom fan uses its actual STEP-derived
rotor within the **official reference-room** flow geometry; the real
wall/guard/anchors, their contact/loads, fully coupled CFD-FEA and
mesh-convergence claims are not validated. Only registered product
families run; arbitrary products and unsupported analyses are rejected.

## 2-minute demo recording shot list (record REAL working UI)

0–15s: Introduce the CAD gap ("How do we know the design works?").
15–38s: Enter natural-language 300-mm wall-fan description; show schema
and actual multi-solid STEP download/preview. Label conceptual assumptions.
38–75s: Open Transient Rotating CFD; **restore a previously computed, genuine**
job (do not rerun minutes-long solve live); show actual U/p fields,
solved time labels, source geometry SHA and continuous rotating blades.
Explain the difference between physical CFD snapshots and smooth geometry.
75–110s: Open real drilled L-bracket 3D FEA / Design Copilot; show
stress/deformation, one physically checked revised STEP, trade-off.
110–130s: Show hollow sleeve and mounting plate registered products.
130–145s: Cite tests, provenance and limitations; show GitHub code.
Record voice and screen (not static slides) for <=3 minutes; ensure
project code and video are accessible before the FINAL cutoff.

## Verification links

- Open PR #16: https://github.com/NeonGrade/ForceForge-AI/pull/16
- Latest all-green branch CI (commit f1396ff): available on the PR Checks tab.
- Real custom source STEP rotor + genuine pimpleFoam U/p:
  https://github.com/NeonGrade/ForceForge-AI/actions/runs/43674796795
- Chromium Play/Pause/loop test:
  https://github.com/NeonGrade/ForceForge-AI/actions/runs/43675405969
- True imported STEP/FEA regression:
  https://github.com/NeonGrade/ForceForge-AI/actions/runs/43675409014

## Do-not-miss at Devpost

1. Sign in and **Join hackathon**.
2. Create project **ForceForge X**; choose **Future of Intelligence**.
3. Paste tagline, description and correct PUBLIC branch URL.
4. Add all three teammates and only actually eligible extra awards.
5. Add actual demo video <=3 minutes when required by the form. Upload
   to YouTube as unlisted or use the permitted Devpost video method;
   make sure judges can watch without login.
6. Explicitly disclose external/pre-existing code and AI coding
   assistance. Ask an organizer for a definitive ruling on eligibility.
7. Click **Save draft** / equivalent **before midnight**. Confirm it
   appears in My hackathon projects; don't assume a saved project equals
   final submitted status.
8. Replace draft with complete video by Sun Nov 15 noon ET; verify
   final submit/complete confirmation before the final cutoff.

**This packet is not a Devpost submission receipt.**
