# ForceForge X | CAD-to-Simulation roadmap from supplied 260-second engine demo

This file records a user-provided visual and workflow reference and preserves a strict distinction between *animation of results* and *verifiable engineering simulation*. Uploaded video was inspected on November 14, 2026. The video shows a detailed 3D engine assembly in motion with load/speed gauge overlays, changing viewpoint and colored high-response zones during a ramp toward 15,000 RPM. The written user narration describes Siemens NX 2306, AI-assisted CAD, FEA, CFD, and failure regions. The video by itself does not provide independent mesh/BC/convergence/reproducibility evidence.

## Current v0.5 delivered slice

- Published steel beam (L=1524 mm, width 30 mm, thickness 5.2 mm, two 5.0-mm reduced zones) already has source-attributed STEP/STL reconstructed CAD and **real measured modal vibration data** in v0.4.
- Added **static Euler-Bernoulli FEM**, bending stress recovery, physical load/units, support force/moment equilibrium, member mass, parametric thickness revision and solver-backed design search.
- New Streamlit `3D CAD Simulation` page lets a non-engineer drag a simulated load, inspect FE-derived surface stress/deformation, expose an illustrative deflection limit, click to regenerate a thinner/thicker section and re-solve. Original measured modal data homepage and previous industry/ML pages remain untouched.
- Portable offline HTML slider gives a presentation preview of **precalculated** bending-stress fields across applied loads. It does not claim to execute new finite element solutions in the browser.
- Six new unit tests verify beam equilibrium, thickness scaling, approximate piecewise beam curvature integral, force linearity, stress sign and FEA-verified selection. Further independent validation is still needed.

## Boundaries (avoid false claims)

**Not yet implemented:** arbitrary STEP solid mesh import, 3D solid tetra/hex FEA, stress concentration at actual bolt holes, contact nonlinearities, plasticity, Navier-Stokes CFD, conjugate heat transfer, moving fluid-structure coupling, RPM assembly dynamics, learned autonomous CAD redesign, certification.

**Experiment vs simulation:** The laboratory supplies measured natural frequencies, not a static tip load/stress experiment. The new *static* FEA uses assumptions E=210 GPa, density=7850 kg/m³, yield=250 MPa and a user-defined service movement limit (2 mm by default). The stress colors are computed from the model, not measured. The displayed 3D surface is a render of a beam-section stress field; **the underlying solver is 1D beam FEM, not 3D solid FEM**.

## Next research-grade steps

1. **Actual STEP → tetra/hex volumetric mesh** with Gmsh + meshio and validity/element-quality checks. Match mesh coordinate units with CAD metadata. Gmsh is GPL, so review redistribution/license conditions before bundling.
2. **3D linear elastic FEA** using scikit-fem or CalculiX; set actual clamps, distributed loads and material law. Recover *element* von Mises at Gauss points, expose hotspots directly on CAD; include force equilibrium, mesh convergence, independent reference and uncertainty.
3. **Complex model:** use a licensed open source industrial bracket or suspension control-arm geometry plus credible fixture/force data. Avoid pretending a random CAD model is experimentally validated; maintain the real beam benchmark separately.
4. **AI iteration:** proposals should alter parameterized CAD dimensions / fillet radii / wall thickness, regenerate a genuine STEP, remesh, re-solve; compare mass, stress, deformation and manufacturing constraints with original FEA. Reject proposed geometries without valid meshes or verified solver results.
5. **CFD** requires its own geometry (fluid domain), inlet/outlet, fluid material and discretization; solve with OpenFOAM/similar. Only couple to structures when the fluid pressure/temperature boundary has been transferred and independently verified.
6. **Presentation:** record a 60–90-second screen capture from the running app with a stable camera, a visible load progression, stress legend *with physical units*, failure explanation, redesigned geometry and before/after FEA. Do not use a cinematic animation to represent unimplemented CFD.

## Useful upstream technical references

- scikit-fem 3D elasticity examples: https://scikit-fem.readthedocs.io/en/stable/listofexamples.html
- Gmsh 3D CAD/tetra meshing API: https://gmsh.info/doc/texinfo/
- CAD / gmsh / PyVista interop: https://github.com/pyvista/pyvista-cad
- Hannover modal experimental specimen: https://doi.org/10.5194/wes-11-3359-2026
- Hannover raw data + Abaqus source: https://doi.org/10.25835/lyav246d

## Screenshot-driven visual comparison corrections (November 14, 2026)

A Mac screenshot at force 0.26 N and source thickness factor 1.10 showed
a 1.30× reference-thickness redesign with 3.158 → 1.913 mm displacement
and 2.422 → 1.734 MPa stress, while the member mass increased by 18.2%.
Two presentation issues were fixed without altering the FE solver formulation:

1. **Same absolute stress color scale** is now shared by the before/after
   surfaces. For example, teal at the same legend position now means the same
   computed MPa in both views; independent auto-scaling is forbidden.
2. **Same camera and transverse-axis range** are used on both meshes. The
   long 1,524 mm specimen uses a manually enhanced display aspect ratio
   while retaining real mm coordinate labels; zoom and deformation are
   explicitly visualization-only.
3. **Clear design references:** 1.10× and 1.30× are relative to the documented
   nominal specimen, whereas +18.2% mass is relative to the current 1.10×
   design. A numerical pass/fail banner identifies the specific 2.00 mm
   displacement target.
4. **Stale scenario safety:** changing load or geometry after a redesign hides
   the prior comparison until the finite element search is rerun. Old numbers
   must not be presented as if they belong to new inputs.
5. Added UI regression and shared-color-range tests to the existing CI gate.

Remaining engineering limitation: This visual comparison remains stress
recovery from a 1D Euler–Bernoulli beam FEM over a 3D surface reconstruction,
not a true volumetric 3D solid mesh solution.
