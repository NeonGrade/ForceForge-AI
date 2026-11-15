# ForceForge X | Engineering Workspace v1.0

**Status:** Review candidate; independent integration branch, not yet merged to `main`.
**Release type:** Product workspace interface, not a claim that the numerical engineering engine has changed version.
**Source baseline:** Unified 2D/3D integration (PR #20), backed by the existing 2D truss FEM and the original 3D Spatial Studio and CAD/ML integration (PR #17).

## Product placement and identity

ForceForge X has a standalone engineering workspace at `/workspace/`. It is deliberately not the future public marketing, onboarding or account home page. The legacy root `/` remains a backwards-compatible entry point while the future site navigation is designed.

The interface is **Workspace v1.0.0**. This does not relabel the underlying 3D UI v0.2.1, 3D engineering v1.0 or draft engineering v1.1 as a finished new solver release. The current 3D CAD pipeline has its own sources, numerical assumptions and acceptance process.

## User-facing improvements

- One full-screen product workspace retains the graphite, alabaster and ion-lime spatial design language of the accepted 3D interface. Clear XY axes and reference grid remain visible in 2D.
- The center scene selector opens the original 3D WebGL Studio in-page and allows a return to the real 2D truss solver. The underlying 3D project selector still offers Solid mechanics, Real CAD and Real laboratory; its added Truss engineering item returns to 2D.
- A dedicated loading/failed-state overlay makes a missing 3D module, unusable 3D document or loading timeout recoverable using **Try again** or **Back to 2D**. There is no blank simulated 3D result on failure.
- The browser address reflects the active scene: `/workspace/` for the 2D workspace and `/workspace/?space=3d` for the 3D workspace. Browser Back/Forward navigation restores the selected scene.
- The 2D design persists only validated user parameters within the current browser tab. After reload, all FE results are recomputed; no prior numerical result is treated as fresh evidence. A Reset study action restores default inputs.
- The solver status distinguishes computing, transport failure, invalid inputs, solver error and computed FEA. The inspector provides a Retry action when analysis fails.
- While FEA is pending, hover identifies geometric nodes and members without incorrectly presenting placeholder zero forces or displacements as calculated results.
- On compact displays, the scene header, selected result controls, brand and primary actions remain readable without scrolling the whole document. Engineering data panels can scroll internally.
- The Export study JSON records the workspace interface version, scene, UTC generation timestamp, assumptions, active inputs, computed FE results and a non-certification notice. The complete JSON export remains accessible from the Results inspector on narrow screens.

## Verified functionality retained

**2D:** Actual linear axial truss FEA, node/member hover values, equilibrium and support reactions, robust optimization over a bounded 144-candidate grid, challenge load and FEA-verified redesign, ML surrogate review with exact FE verification, offline/optional API brief interpretation, chart and evidence exports.

**3D:** Original WebGL real 3D tetra10 solid model, CAD STEP source/import/revision/meshing, bounded engineering Agent/CAD features and experimental modal laboratory workspaces. The integrated shell delegates to those existing numerical services and does not fabricate results or substitute a browser-side FEM solver.

## URL and service contract

| Route | Meaning |
| --- | --- |
| `/workspace/` | Canonical engineering workspace; default 2D scene |
| `/workspace/?space=3d` | Same workspace with embedded 3D Spatial Studio |
| `/` | Project homepage; launch the workspace through its studio links |
| `/api/workspace` | Workspace v1.0.0 capability metadata (3D availability flag) |
| `/api/solve`, `/api/search`, `/api/challenge`, `/api/ml`, `/api/interpret` | Unchanged 2D physical/numerical service contract |
| `/api/3d/catalog`, `/api/3d/solve`, `/api/3d/cad/*` | Original 3D service contract, namespaced without changing the underlying solver |
| `/studio/` | Original 3D Studio assets and user experience |

## Local launch (macOS)

Run on the **Workspace v1.0 integration branch** from a real repository checkout. Prefer Python 3.12 within an isolated virtual environment for reproducibility.

```bash
python3 -m pip install -r requirements.txt
# Required only for the real STEP/Gmsh CAD workflows:
python3 -m pip install 'gmsh>=4.12,<5'
python3 web_server.py
```

Open `http://127.0.0.1:8000/workspace/`. For another available port, run `python3 web_server.py --port 8001` and browse to port 8001. The original `studio_server.py` and Streamlit specialist pages remain independent options.

## Verification and release gates

- Standalone local tests: **12 passed, 1 skipped**. The single skip is the genuine 3D integration smoke test, because the reduced local staging copy contains no `studio_server.py` and cannot honestly claim a real 3D solve. This test should run unskipped on the combined GitHub branch.
- `node --check` succeeded for both 2D JS modules; Python compilation and 2D numerical regressions passed.
- Static layout checks with real Python 2D FEA payloads: **1440, 1280, 900, 430, 390px** wide with no global page overflow or JavaScript errors. Browser transport in the test environment is restricted, so those screenshots are not proof of a live Mac browser or a real 3D WebGL/Gmsh session.
- Before merging: run the complete repo CI matrix on Python 3.11/3.12, run Mac Python 3.13/Gmsh checks where relevant, open both scenes on the team demo Mac and verify imported STEP, camera orbit, controls, hover, two-way switching and exports; confirm network/3D failure recovery and browser Back/Forward.

## Engineering and security boundary

Results are numerical solutions of idealized boundary conditions and material properties, not automatically measured material behavior, real product certification, or a warranty of structural safety. Measured laboratory modal evidence stays distinct from assumed static CAD loading. The 2D solver and 3D CAD have different meanings for `/api/solve`; that collision is resolved by an explicit 3D route namespace. Input caps, STEP source hashes and original solver checks are preserved.

No previous PR was overwritten, rebased or force-pushed by this workspace release candidate.
