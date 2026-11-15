# ForceForge 3D Solid FEA — isolated web workspace (experimental)

## Preferred local launch — integrated engineering UI

```bash
git switch feature/step-solid-fea
git pull --ff-only origin feature/step-solid-fea
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-3d.txt
python -m pytest -q
python web_server.py
```

Open **http://127.0.0.1:8000/** for all six tools. Select **3D Solid FEA** in the original left rail, or navigate to **http://127.0.0.1:8000/#solid3d**. The original 2D modules stay mounted and their current input state is retained when switching to 3D. Old /solid3d bookmarks redirect into the integrated view.

This 3D page is a normal HTTP/Canvas application **without Streamlit
WebSockets or external JavaScript libraries**. The long-running web server
does not import Gmsh. Each simulation runs in a disposable Python subprocess
(`forceforge/solid3d_worker.py`) with a 65-second timeout, a serialized
worker queue, 6,000-tetrahedron / 10,000-node limits and a 4 MB STEP file
limit. A worker Python exception, native crash or timeout is returned as an
error; it does not terminate the parent HTTP server. Browser health status
checks `/api/health` every 15 seconds.

For legacy compatibility, `python -m streamlit run app_3d.py` also uses the
isolated worker, but **the HTTP workspace is preferred for live demos**.
If the machine sleeps, the server is stopped, or the HTTP port changes, no
local web app can remain connected; restart the local server.

## Supported calculations

- Native rectangular 3D solid and uploaded STEP closed-solid import through
  Gmsh OpenCASCADE.
- Explicit STEP coordinate unit selection (mm, m, inch).
- Linear isotropic small-strain 4-node tetrahedra, static stiffness solve.
- Fixed minimum-axis face and equal nodal point-load distribution on the
  maximum-axis face; choose X, Y or Z.
- Nodal displacement, element von Mises stress, stress-to-node average and
  exterior surface triangles.
- Rotatable Canvas contour display with adjustable deformation amplification,
  result export, reaction equilibrium check.
- Patch, repeat-meshing, lifecycle, worker crash/timeout and HTTP smoke tests.

**STEP geometry import is not assembly/contact FEA.** Multiple disconnected
solids without supported interfaces may produce a singular system. The current
solver does not automatically assign contacts, tie surfaces or boundary
conditions to imported assemblies.

## Limits and validation

- Boundary loads are simplified; nodal stress concentrations may be highly
  mesh-dependent. Displayed colors use averaged nodal stress, and the reported
  peak von Mises is computed at elements.
- No plasticity, real stress/strain material data, fatigue, failure model,
  thermal coupling, CFD or automatic CAD modification yet.
- Mesh convergence and comparison against independent reference solvers are
  **still acceptance gates** before claiming reliable physical accuracy.
- Strongly avoid describing this as a verified safety/design-certificate tool.

## Checks

```bash
python -m pytest -q
# Run test suite and native smoke tests through GitHub Actions
# `Solid 3D FEA checks` workflow on the feature branch
python web_server.py
# In another terminal:
curl http://127.0.0.1:8000/api/health
```

## Stability diagnosis

- If `/api/health` stays online but the solve shows an error, the isolated
  FEA worker encountered a CAD, mesh, numerical or timeout problem. Try a
  coarser mesh, reduce geometry complexity, and inspect the terminal message.
- If `/api/health` is offline, the parent web server was stopped, the device
  slept, or the local port is unavailable. Restart `python web_server.py`.
- If the old `localhost:8501` page shows a Streamlit **Connection error**,
  use `http://127.0.0.1:8000/` then open the sixth 3D tool to avoid the Streamlit/WebSocket stack.
- Multiple solver button clicks are guarded by a single-worker semaphore.
  A second request gets a safe busy error without overloading memory.

## Demo scenario

Rectangular block 100 × 20 × 20 mm, mesh size 8 mm, E=200 GPa, nu=0.3,
+1000 N along X. Rotate colored surface. Confirm finite stress/displacement,
check the force balance residual, then rerun or vary deformation amplification
without a Streamlit reconnect.

The HTTP version is intentionally additive to the existing 2D browser app.
