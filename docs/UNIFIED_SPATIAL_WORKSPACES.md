# ForceForge X — Unified 2D + 3D Spatial Workspaces (v1.0 foundation)

**Interface:** ForceForge X Workspace v1.0.0 (2D Spatial Parity + original 3D Spatial Engineering v0.2.1)  
**Engineering baseline:** Physics-verified 2D truss and the existing 3D/CAD/real-laboratory modules from the PR #17 integration branch.  
**State:** Independent review integration; do not merge until CI and Mac/Safari review are complete.

## One website and one local server

Run from the repository root on a supported Python installation:

```bash
python3 -m pip install -r requirements.txt
# Optional, for real STEP import / 3D CAD meshing:
python3 -m pip install 'gmsh>=4.12,<5'
python3 web_server.py
```

Open **http://127.0.0.1:8000/workspace/**. There is no requirement to launch `studio_server.py` or a second port. If port 8000 is already in use, stop the old server or launch with `python3 web_server.py --port 8001` and use the corresponding address.

For reproducible Mac environments, prefer Python 3.12 in a virtual environment; system/Anaconda 3.14 and native Gmsh combinations have not been accepted on the project demo machine. The original `python3 studio_server.py` remains an independent specialist entry point at port 8765.

## Interaction

1. The project homepage links to `/workspace/`, which opens the 2D Truss Engineering workspace, including its solver, optimization, load challenge, ML, AI brief, mesh grid and field probing.
2. Open the centered scene selector and select **3D Spatial Studio**.
3. The existing 3D WebGL interface appears directly in the same page. Its own project selector offers **Solid mechanics**, **Real CAD** and **Real laboratory** with their original engineering calculations.
4. Within that 3D project selector, **Truss engineering** switches back to the preserved 2D state; a compact **2D TRUSS** return control offers an additional reliable way back.
5. Switching modes does not coerce 2D bar/truss results into 3D tetrahedral results. Each workspace uses its own unchanged Python backend and units.

## Route isolation

| URL | Owner | Purpose |
| --- | --- | --- |
| `/` | Project | Main branch's independent project landing page |
| `/workspace/` | 2D | Main engineering SPA |
| `/api/solve` | 2D | Axial truss finite element solve |
| `/api/search`, `/api/challenge`, `/api/ml`, `/api/interpret` | 2D | Existing 2D workflows |
| `/studio/` | 3D | Original WebGL UI served in a same-origin iframe |
| `/studio/*.css`, `/studio/*.js` | 3D | Existing 3D interface assets |
| `/api/3d/catalog` | 3D | Scene list / readiness |
| `/api/3d/solve` | 3D | Real 3D tet10 solid or laboratory modal analysis |
| `/api/3d/cad/solve`, `/api/3d/cad/revise` | 3D | Original STEP / Gmsh / FEA / redesign pipeline |
| `/api/3d/cad/agent/*` | 3D | Original CAD brief and evidence review |
| `/download/*` | 3D | Original geometry download routes |

The embedded 3D index gets a tiny client-side `fetch` prefix adapter, applied only by this unified server. The standalone studio file and engine do **not** change. Existing `StudioHandler` performs request body caps, input validation, source hashing and origin checks; 3D solver calculations are not duplicated on the client. All routes are same-origin; opening the iframe does not need CORS exceptions, a proxy, or a second server process.

## Validation boundaries

- The full frontend routing and 2D FEA regression tests run in `tests/test_web_api.py` and `tests/test_unified_spatial.py`.
- `tests/test_unified_spatial.py` also runs a true 3D solid solve when the 3D integration modules exist, and intentionally skips that specific integration check for standalone 2D checkouts.
- Browser smoke checks cover 1440×900, 900×700, and 430×790 scene switching, two-way return, state preservation and no whole-page scrolling. In environments that block local HTTP browsing, those browser layout checks run with a 3D frame stub; real 3D numerical and integration checks remain separate.
- Real STEP stress colors and computed displacement are **numerical analyses under explicit assumptions**, not measured static physical loads or structural safety certification.
- Engineering v1.1 local stress-convergence work is a separate draft branch and is **not** silently claimed as merged into this v1.0-based integration.

## Source branches

- 2D visual parity: `ui/2d-spatial-parity` (PR #19).
- 3D engineering, original CAD and ML/Agent integration: `codex/ml-agent-upgrade` (PR #17).
- Both remain available for independent review. The unified review branch combines them without force-pushing either parent or altering `main`.

## v1.0 product polish

The canonical `/workspace/` route and integration refinements are documented in `docs/WORKSPACE_V1_0.md`. They do not alter the engineering solver release version or independently validate physical hardware.
