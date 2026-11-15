# ForceForge X · bounded plain-language CAD catalog

## Supported product types (v0.4 development in PR #16)

- L-bracket: real drilled STEP; actual isolated tetra10 FEA when all demo
  material, load and support assumptions are approved or supplied.
- Wall fan: real simplified multibody STEP, actual rotor source extraction,
  idealized fluid-volume preprocessor, official reference OpenFOAM comparison.
  It is not a validated wall-anchor design.
- Hollow shaft: real concentric outer cylinder minus through-bore, defined
  by outer diameter, inner diameter, and length in mm.
- Rectangular mounting plate: single OCC solid with specified length, width,
  thickness and optional explicit four through-holes. Hole centres are defined
  by their edge offset. No invented hole geometry.

The generator catalog is fixed and typed; arbitrary products and unspecified
geometry remain BLOCKED. Requests for two holes or unsupported mechanics do
not silently generate some other shape.

### Quick examples

- Chinese: 设计一个空心轴，外径60mm，内径30mm，长度120mm。
- English: Build a hollow shaft outer diameter 60 mm inner diameter 30 mm length 120 mm.
- Chinese: 做一个矩形安装板，长度150mm，宽度100mm，厚度8mm，开4个孔，孔径6mm，孔中心距边缘15mm。
- English: Make a mounting plate length 150 mm width 100 mm thickness 8 mm with 4 holes, hole diameter 6 mm hole edge offset 15 mm.

### Validation requirements

Each new family receives a strict versioned Pydantic schema, explicit
unit/feature extraction, bounded Gmsh OpenCASCADE worker, source SHA-256,
native STEP export, independent STEP re-import, exact OCC solid-volume
comparison, and no-fake-physics execution gates.

Only registered geometry generators can be executed. A STEP export is not
an OpenFOAM field, an FEA stress, or a validated mechanical design.
Unsupported model types require implementing their geometry/BC/solver
adapters before claiming any physical analyses.

### Demo acceptance

- Schema/parser and unknown-model rejection tests pass.
- Real source STEP independently reimports as a solid with correct volume.
- Other product families do not regress bracket FEA or the fan workflow.
- Streamlit remains idle until an explicit Generate action; no native CAD
  is executed merely by typing, switching tabs or refreshing.
- Final Mac/Chrome interactive acceptance remains manual before contest
  demonstration.


## November 15 extension · actual FEA and wall load transfer

Actual CAD-derived volumetric Gmsh/tetra10 FEA is supported for
single-solid hollow shafts and mounting plates as well as brackets.
Real FEA only starts after explicit load, material and planar-support
assumptions are supplied or approved. The generic STEP upload workflow
can also solve *other* single-solid geometry with compatible flat
support/load boundary surfaces and manageable mesh size.

The Wall Mount Load Transfer page performs ideal rigid four-anchor
force and moment equilibrium with transparent source declarations.
It accepts user-measured inputs, and has a validation-gated CSV input
for a single physical OpenFOAM pressure-patch time, converting
kinematic pressure to SI pressure with user-supplied density.
This is NOT a verified automatic link to the existing reference case;
source surface correspondence and actual wall/bolt FE stresses
still require independent modeling.
