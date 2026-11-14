# Stable CAD runtime — ForceForge X v0.9

This version keeps all of v0.8's genuine source-attributed NIST STEP
workflow, geometry revision, quadratic tetra10 3D FEM, model assumptions,
and prior published modal work. It changes **when and where** heavy work runs.

## Why the browser had become unreliable

Previous `pages/13_Real_STEP_Engineering.py` generated a STEP model,
meshed it with the **native C++ Gmsh library**, solved the sparse 3D
elasticity system, and even generated a proposed revised STEP immediately
on page load. Streamlit re-executes page source on many widget changes.
This can lead to repeated expensive native work, huge in-process
allocations, and a disconnect if the Streamlit Python server is killed.

This is a plausible mechanism for the observed instability; a single
screenshot cannot establish which native operation, memory limit, or
network condition terminated the user's local server.

## Design

- **Zero Gmsh/FEA work when the page opens.**
- Explicit buttons start original and revised STEP computations.
- Gmsh and the 3D sparse FEM run only in a **short-lived separate Python
  subprocess**, using the same `.venv` interpreter. Mac Streamlit threads
  do not initialize native Gmsh.
- Every worker has a **35-second CAD generation timeout** or **85-second
  CAD+FEA timeout**. If Gmsh segfaults or runs out of memory, its worker
  exits and the main Streamlit process can display the error.
- An input cap of **1,400 first-order tetrahedra** bounds the cost of
  converting them to quadratic FE elements and running the sparse solver.
  This limit may reject very detailed STEP parts and does **not** imply
  a sufficiently converged mesh for engineering certification.
- For memory conservation, BLAS/OpenMP threads are limited to one in
  workers, and there are **no large unbounded Streamlit cached FEM
  copies**. At most one current and one redesigned solution live in the
  session.
- Mesh, source SHA-256, physical load inputs and FE results are exchanged
  through JSON and `.npz` with `allow_pickle=False`.
- Changing any physical, mesh or CAD input **hides stale FEA results**.
  Changing only display exaggeration redraws the *existing* solution.

## Mac runbook

Stop the old server with **Control+C** in Terminal, then check for local
uncommitted changes:

```bash
cd ~/ForceForge-AI
git status --short
git fetch origin
git switch --track origin/feature/stable-cad-runtime-v9
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install 'gmsh>=4.12,<5'
python -m pytest -q
python -m streamlit run app.py --server.fileWatcherType none
```

If this branch already exists locally:

```bash
git switch feature/stable-cad-runtime-v9
git pull --ff-only origin feature/stable-cad-runtime-v9
```

Do **not** reset/clean the repository or delete the `.agents/` directory.

Open http://localhost:8501, then click
**Real STEP → 3D FEA / CAD redesign**.

1. The page should open **without** running Gmsh or FEA.
2. In default **Editable 3D L-bracket**, use default 8 mm / 12 mm tetra
   target. Press **Run CAD import + 3D FEA**.
3. Check tip displacement, von Mises, reaction residual, geometry hash and
   tetra count.
4. Set revised web to 12 mm, press
   **Re-mesh revised CAD and re-run 3D FEA**.
5. Changing the load afterward should hide both old numerical results
   until the solver is explicitly run again.

For a stable public demonstration, keep the server running and use the
interactive slider only for visual exaggeration. The native worker will
not rerun on those changes.

## Recovery / debugging

To inspect your local runtime:

```bash
cd ~/ForceForge-AI
source .venv/bin/activate
python -c "import sys,platform,gmsh; print(sys.executable,platform.machine(),gmsh.__file__)"
git branch --show-current
```

If a compute button fails, copy the **Isolated CAD/FEA job failed safely**
message (exit code or Python exception). Unlike a Streamlit crash, it
should not disconnect the whole web app. If the whole server still dies,
capture the Terminal traceback and macOS crash-report process name to
distinguish OOM, bad native DLL, browser websocket and app bugs.

## Correct engineering interpretation

The externally published NIST geometry is real. The loads, fixture
planes and material yield values are assumed for a demonstration;
numerical reaction balance and geometry-volume checks do not prove
independent physical verification, mesh convergence or certification.
