# ForceForge X: 2D Spatial UI Parity

**Status:** standalone, reviewable 2D frontend update. The original numerical backend is unchanged.

## Relationship to the 3D interface

The 2D axial-truss workspace adopts the visual vocabulary of Spatial Engineering UI v0.2.1 (`ui/v0.2-adaptive-spatial`, PR #13): graphite and midnight-blue scene, off-white Manrope typography, pale ion-lime active controls (`#d7efa2`), transparent glass panels, a centered project selector, and model-anchored interaction markers. The engineering scene remains fully visible by default, with settings and full results available in dismissible drawers. The layout is responsive and prevents scrolling of the whole document.

### Control and model details

- **A visible physical XY reference grid and axes remain active**, including the exact reference geometry, supports, the applied load arrow, member force coloring, and exaggerated-displacement labeling.
- **Click or horizontally drag** the force and section markers. A compact numeric/range editor is available; edits dispatch through the original `updateConfig` function and trigger the original `/api/solve` process.
- **Click the movement marker or a real member/node** for results; hover exposes the existing true engineering fields (node displacement/reaction or member force/stress/buckling screening).
- **Bottom workspace rail:** Analyze, Optimize, Challenge, ML Verify, AI Brief. Each button preserves the corresponding original API workflow and displays its results on demand.
- **Small screens:** the section marker gives way to the settings drawer, avoiding obscuring the model; scrolling, if needed, stays *inside* a drawer rather than the whole page.
- The selector offers a link to the standalone 3D Spatial Studio at `http://127.0.0.1:8765`. This only works while the separate 3D server is running. The 2D backend stays on port 8000. Neither engine is silently substituted for the other.

## Scientific fidelity

The 2D module is the existing pin-jointed, small-strain, linear elastic axial-truss solver with FEA-based robust load/elasticity/area scenarios, a simplified Euler buckling screen, a Random Forest surrogate **rechecked by actual FEA**, and optional bounded language interpretation. The new overlay is presentation only; no calculated stress, displacement, force, or material response is invented in JavaScript. Nothing here represents physical measurements or certifies safety.

## Files changed

- `web/index.html`: Spatial scene and user interface markup.
- `web/spatial-theme.css`: additive shared visual language and responsive overlay behavior.
- `web/spatial-shell.js`: position/model-bound editor and drawer interactions only.
- `web/app.js`: minimal adapter and viewport framing; original engineering workflows remain in place.
- `web_server.py`: explicit static routes for the two new assets.
- `tests/test_web_api.py`: API regression and style/asset guards.

## Launch (macOS)

```bash
python3 -m pip install -r requirements.txt
python3 web_server.py
```

Open <http://127.0.0.1:8000>. To open the separate 3D Studio, run `python3 studio_server.py` from a branch containing those 3D files and then use <http://127.0.0.1:8765>. The 2D app works without an OpenAI key or the 3D Gmsh stack.

## Verification

- All current `tests/test_web_api.py` assertions pass; 2D FEA numerical benchmark and robust challenge remain intact.
- JavaScript syntax checks pass.
- Browser layout checks at 1440×900, 1280×800, 900×700, 430×790 and 390×640: no page-level overflow and no script errors.
- Browser interaction tests: editing force, expanding and dismissing settings/results, selecting a workspace, running optimization against the Python backend, and mobile drawer behavior.
- Browser rendering test uses an in-process bridge to the *real* Python API because this testing environment blocks headless browser navigation to local loopback. HTTP static routes were separately checked over loopback.
