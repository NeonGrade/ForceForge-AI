# ForceForge X — Natural-Language Mechanical Engineering Platform v0.1

Implementation branch: **PR #16 / feature/stress-local-validation-v11**.
This is an additive architectural slice inside the ORIGINAL ForceForge X
Streamlit multipage application. Prior Real STEP, measured modal, Tetra10
FEA, hotspot convergence, Design Copilot and 2D workflows remain intact.

## What actually works

A person enters an ordinary Chinese or English engineering request, e.g.:

> 帮我做一个直径30厘米、转速1500 RPM的挂壁风扇，
> 想看气流分布，以及墙壁和固定架怎么受力。

The parser recognizes the registered **wall_fan** family, extracts only
**diameter=300 mm** and **speed=1500 RPM** and requests structural FEA +
fluid CFD. It will NOT invent blade geometry, wall anchors or air velocities.

**After explicit "approve concept assumptions" input**, the
\`wall_fan\` plugin generates a genuinely exported multi-solid
ISO-10303-21 STEP file using Gmsh OpenCASCADE in a disposable Python
subprocess. The conceptual assembly contains a flat-blade impeller,
guard ring, motor/standoff and wall mount plate. The returned SHA-256
and possible OCC-generated triangle preview are traceable. This is
NOT an aerodynamically verified fan assembly or an executable CFD/FEA
model. Both fluid and mounting-structure simulations remain BLOCKED.

A user can also say:

> 生成腹板厚度8毫米的L型支架，施加载荷250 N，
> 计算结构受力、应力和变形。

The registered **l_bracket** plugin regenerates the same real STEP
as the existing Real STEP page. If the user explicitly accepts labeled
DEMO material/fixture assumptions (E, nu, rho, yield, fixed minimum-Z,
+X force), the existing crash-isolated **Gmsh volume mesh / quadratic
tetra10 FEA** is invoked without changing the solver. The result is
from actual FEM including mesh/force/source-hash quality checks.
It remains preliminary linear elasticity, not a safety certificate.

## Architecture and boundaries

| Module | Contract | Current registered execution |
|---|---|---|
| \`engineering_schema.py\` | Pydantic v2 versioned strict \`EngineeringRequest\`; explicit mm, RPM, N, GPa, kg/m³, MPa | 2 families; deterministic Chinese/English pattern extractor |
| \`product_cad.py\` | Generator registry + \`CADProduct\`, STEP bytes/hash and optional ACTUAL CAD triangulation | existing bracket STEP + **concept fan multi-body STEP** |
| \`engineering_pipeline.py\` | Capability registry, dependency graph, reasons, blocked stages, real evidence audit | bracket tetra10 FEA only; fan and CFD blocked |
| \`pages/14_Natural_Language_Engineering.py\` | Review parsed parameters, opt-in demo assumptions, inspect plan, click to run | additive Streamlit page, linked from home and Real STEP |
| \`isolated_cad.py\` | Existing bounded child worker + real tetra10 FEM | reused unchanged for bracket FEA |

### Stage graph

\`\`\`mermaid
flowchart TD
    A["User plain-language engineering requirements"] --> B["Strict schema & units, missing-input checks"]
    B --> C{"Registered CAD family?"}
    C -->|L-bracket| D["Real parametric STEP, isolated Gmsh"]
    C -->|Wall fan| E["Concept multibody STEP, isolated Gmsh"]
    C -->|Unregistered| X["BLOCKED, add a schema and CAD adapter"]
    D --> F{"FEA fixture, loads and material supplied or explicitly approved?"}
    F -->|Yes| G["Existing real tetra10 FEA worker + QA"]
    F -->|No| H["BLOCKED, show missing inputs"]
    E --> I["BLOCKED: fan assembly contact and wall anchor FEA"]
    D --> J["CFD capability & fluid domain required"]
    E --> J
    J --> K["BLOCKED: real CFD solver not yet connected"]
    G --> L["Source SHA, real stress/displacement and provenance report"]
\`\`\`

Stage states are **READY, BLOCKED, NOT_REQUESTED, COMPLETED, FAILED**.
A run only executes READY stages. There are **no fabricated CFD fields,
fake wall-anchor reactions, surrogate stresses, or unverified approvals**.
CFD needs fluid region generation, boundary conditions, actual blade
geometry or pressure-flow curve, Navier–Stokes solver, verification and
physical load transfer before FSI can be enabled.

### JSON schema examples

\`\`\`json
{
  "schema_version": "1.0",
  "prompt": "做一个直径30厘米，转速1500RPM的壁挂风扇，分析气流和墙体受力",
  "family": "wall_fan",
  "geometry": {
    "family": "wall_fan",
    "diameter_mm": 300,
    "rpm": 1500,
    "blade_count": null,
    "hub_diameter_mm": null,
    "blade_pitch_deg": null
  },
  "analyses": {"structural_fea": true, "fluid_cfd": true, "thermal": false},
  "loads": {
    "force_n": null, "force_axis": null,
    "support_axis": null, "anchor_specification": null
  },
  "material": {
    "E_gpa": null, "poisson": null,
    "density_kg_m3": null, "yield_mpa": null
  },
  "mesh_size_mm": 12,
  "assumptions": [],
  "concept_assumptions_confirmed": false,
  "extraction_mode": "EXPLICIT_RULE_EXTRACTION"
}
\`\`\`

Generate the canonical OpenAPI-compatible typed JSON schema using:

\`\`\`python
from forceforge.engineering_schema import EngineeringRequest
schema = EngineeringRequest.model_json_schema()
\`\`\`

## Running in the SAME project

\`\`\`bash
git switch feature/stress-local-validation-v11
git pull --ff-only origin feature/stress-local-validation-v11
source .venv/bin/activate
python -m pip install -r requirements.txt 'gmsh>=4.12,<5'
python -m streamlit run app.py --server.fileWatcherType none
\`\`\`

From the original app sidebar, click
**Natural language → real CAD / FEA plan**. The original
**Real STEP → 3D FEA / CAD redesign** link stays available.

### Test gates

\`\`\`bash
python -m pytest -q tests/test_engineering_schema.py tests/test_engineering_pipeline.py tests/test_nl_ui.py
python -m pytest -q tests/test_nl_native_cad.py
\`\`\`

GitHub Actions runs these on Linux, and the same real CAD/FEA tests on
macOS ARM64. The original CAD/FEA regression remains mandatory.
The native fan worker has a hard timeout, bounded parameters, no path
injection or dynamically executed user source, and a strict STEP-size cap.

## Extension contract

To add a third mechanical product (pump, bicycle frame, impeller, gearbox):

1. Add a new discriminated geometry \`family\` schema with **units**, explicit
   domains, geometric cross-field constraints and nullable missing values.
2. Register the generator in \`product_cad.generate_product\`, using a
   disposable native CAD process; output a genuine STEP plus source SHA,
   source/mesh bounds and design-provenance metadata. Never infer unsupported
   topology from arbitrary prompts.
3. Declare the family's separate **CAD / structural / fluid / thermal**
   capabilities in \`FAMILY_REGISTRY\`. An unavailable solver returns BLOCKED,
   not a plausible-looking image or made-up output.
4. Provide physics adapters that identify independent **load cases, support
   surfaces, fluid domains, BCs, material models and solver verification**.
   Validate units, mesh quality, equilibrium, convergence and uncertain inputs.
5. Add native tests with independent reimport of STEP, true solver smoke,
   misleading/hallucinated numeric values, failure isolation and live UI
   regression before claiming a new capability is DONE.

## Future milestones not yet implemented

- Optional LLM-based semantic extraction and robust multilingual requirements
  normalization, while numbers remain source-grounded and user-confirmed.
- Generic editable CAD feature graph, BRep operations, part constraints and
  robust assembly topology; current fan geometry is a simplified concept.
- Real fluid-domain generation, OpenFOAM or independently verified CFD solver,
  pressure-flow/fan performance input, residual checks and streamline fields.
- Verified structural contacts/bolts/anchors; coupled aero loads to structure.
- Multi-objective redesign of **different product families**, uncertainty
  propagation, reproducible performance benchmarks and live Mac acceptance.
