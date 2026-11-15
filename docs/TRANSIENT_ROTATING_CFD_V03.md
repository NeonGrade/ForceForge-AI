# ForceForge X v0.3 - Actual rotating-blade CFD (development)

PR #16, branch feature/stress-local-validation-v11. All previous real STEP, tetra10 FEA, design copilot, hotspot verification and air volume meshing remain intact.

## Physical model

The old forceforge_actuator_air_*.msh has only two AIR domains and a rotor actuator zone, with no blade walls or coupled rotating AMI faces. It cannot directly produce resolved rotating-blade CFD.

The new OpenFOAM rotating-fan adapter uses the official rotatingFanInRoom tutorial, a real snappyHexMesh air grid, cyclic AMI interfaces and dynamic rotatingMotion cell-zone movement. The solver is pimpleFoam (transient incompressible Navier-Stokes). Source: https://doc.openfoam.com/2312/examples/tutorials/incompressible/pimpleFoam/ami-rotating-fan/

There are TWO DISTINCT geometry modes:
1. OFFICIAL_OPENFOAM_ROTATING_FAN_REFERENCE_GEOMETRY: the full tutorial fan and room. It is a real CFD demonstration but is not the user's STEP design.
2. USER_STEP_ROTOR_IN_OFFICIAL_REFERENCE_ROOM: actual source-STEP blades/hub are selected, tessellated into a closed ASCII STL, converted from mm to SI metres and used to replace the reference fan STL BEFORE remeshing. The room, AMI cylinder, ambient boundaries and fixed structures are still from the tutorial, NOT the user's own wall and guard. If replacement does not survive meshing, the run is rejected.

No custom-installation or wall-anchor physics is claimed.

## Run on Mac

Install/start Docker Desktop, then:

    docker pull opencfd/openfoam-default:2512
    cd ~/ForceForge-AI
    git status --short
    git fetch origin
    git switch feature/stress-local-validation-v11
    git pull --ff-only origin feature/stress-local-validation-v11
    source .venv/bin/activate
    python -m pip install -r requirements.txt 'gmsh>=4.12,<5'
    python -m streamlit run app.py --server.fileWatcherType none

The versioned opencfd/openfoam-default image contains real CFD executables AND tutorials; openfoam-run is insufficient because it omits tutorials.

In the NL engineering page, generate your fan STEP and select Extract actual rotating blades. The output has the exact STEP hash and independently meshed STL hash. Continue to the Transient Rotating CFD page to select the actual source-STEP rotor in the OpenFOAM reference room.

Or use the official reference-case mode for a separately labeled reference benchmark. Click Run genuine OpenFOAM rotating-mesh transient CFD. Real CFD executes in an isolated Docker worker with bounded 4 CPU/6GB/15min limits. The UI merely polls a persisted job. Nothing computes by opening the page.

Only genuine completed VTK results with actual finite velocity U [m/s] and kinematic pressure p [m²/s²] become 3D animated frames. The Plotly Play control replays SOLVED fields. No fabricated CFD contours, timestamps or pressures. The actual VTK files and solver logs are hashed in job evidence.

## Physical accuracy and validation limits

The model needs a robust AMI grid with an actual moving rotor wall, a confirmed CAD-to-STL SHA-256 chain, physically meaningful material/air properties, bounded Courant number, pressure-velocity residuals, continuity, mesh-size sensitivity and appropriate outlet boundaries. The reference room is not the actual wall-mounted environment. A 1500 RPM input is a boundary assumption, not measured fan performance. The source CAD currently represents conceptual flat blades rather than actual aerodynamic airfoils. Wall installation structural FEA, guards, bolts, fatigue and coupling loads are not validated.

Do not imply this work has achieved real CFD until the actual Docker solver and field-export CI finishes successfully. An offline video must use real precomputed solver outputs, never AI-generated velocity colors.

## Demo sequence (engineering-backed)

1. Natural language input -> genuine STEP and physical source hash.
2. Real rotor extraction -> closed manifold moving-blade STL (same source hash).
3. OpenFOAM dynamic mesh / AMI -> actual time-stepped incompressible flow solve.
4. Real U/p frames -> rotate 3D view, play/pause, inspect saved snapshots.
5. Conservative evidence export, unresolved physical assumptions displayed.

Sources: forceforge/rotating_cfd.py, forceforge/rotor_surface.py, pages/15_Transient_Rotating_CFD.py, tests/test_rotating_cfd.py, tests/test_rotor_surface.py, and .github/workflows/rotating-openfoam.yml.
