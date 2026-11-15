# ForceForge X · Hack The Nest 2026

**Describe a mechanical product → Generate real STEP CAD → Verify FEA / rotating CFD → Inspect source-linked physics.**

**[Devpost project](https://devpost.com/software/neongarden)** ·
**[Full 75.6-second real demo MP4](https://github.com/NeonGrade/ForceForge-AI/actions/runs/43723778286/artifacts/14166096118)** ·
**[Full submission checklist](docs/FINAL_SUBMISSION_CHECKLIST.md)** ·
**[Project story and technical disclosure](docs/DEVPOST_SUBMISSION_2026.md)**

This is the independent **ForceForge X competition submission branch**, focused
on the mechanical engineering and physics work. Teammates' unrelated workspace
branches and the repository's older default `main` are left untouched.

## Judge-facing workflows

| Workflow | Genuine implementation | Explicit limitation |
| --- | --- | --- |
| **1. Natural-language CAD** | Chinese/English engineering requests become typed dimensions and actual Gmsh/OpenCASCADE STEP geometry. Four registered product families: drilled L-bracket, conceptual axial wall fan, hollow sleeve/shaft, and rectangular mounting plate (optional four holes). | Not an unrestricted automatic CAD generator; unknown products are rejected. |
| **2. Structural FEA** | Real single-solid STEP import → real 3D Gmsh volume mesh → isolated quadratic tetra10 small-strain FEA, equilibrium check, von Mises and displacement plots. Tested on brackets, hollow sleeves and rectangular plates with explicitly assumed planar fixtures/materials. Arbitrary **uploaded single-solid STEP** can also be evaluated when geometry and boundary planes qualify. | No bonded/contact assembly, bearing contact, real bolt clamp or mesh-converged certification. |
| **3. Rotating CFD** | Actual user-generated fan STEP rotor → source-derived STL → OpenFOAM reference-room rotating AMI mesh → genuine transient `pimpleFoam` U/p fields. | Surrounding room/AMI zones are reference geometry; real wall/guard/fasteners are not modeled. |
| **4. Continuous 3D rotor** | WebGL playback updates actual STL blade vertices in an endless, pausable rotation; the backdrop is a genuine CFD U/p snapshot. | Intermediate rotor positions are rigid kinematics, **not** additional CFD solutions. |
| **5. Mounting load transfer** | Explicit mass, eccentricity, aerodynamic loads and torque → balanced rigid four-anchor reactions. Optional user-supplied OpenFOAM surface-pressure CSV → density-scaled SI pressure force and moment → anchor static load transfer, with file SHA-256 and one-time patch checks. | User's uploaded patch is NOT independently verified against the source OpenFOAM mesh. Viscous traction, wall deformation, anchor pullout/contact and coupled CFD–FEA remain outside validated scope. |

## Quick demo from Mac

Use the *dedicated* competition entrypoint:

```bash
cd ~/ForceForge-AI
git status --short
git fetch origin
git switch hack-the-nest-2026-submission
git pull --ff-only origin hack-the-nest-2026-submission
source .venv/bin/activate
sh scripts/run_hackathon_demo.sh
```


If local modifications block branch switching, inspect them first; do **not**
run a hard reset or delete saved OpenFOAM results.

Open **http://localhost:8501**.

The judge home page provides one-click navigation to **Natural Language CAD,
Structural FEA, Rotating CFD, and Wall Mount Load Transfer**. It can enumerate
previously completed SHA-verified CFD jobs and replay them **without rerunning
Docker**. The Mac application is local, not publicly hosted.

New installation requires Python 3, `pip install -r requirements.txt 'gmsh>=4.12,<5'`,
and Docker Desktop with `opencfd/openfoam-default:2512` for new OpenFOAM solves.
The recorded Devpost video is downloadable even without local installation.

## What to show in 2 minutes

1. **Describe** a fan in plain language, approve clearly labeled concept
   parameters, generate real STEP and preview the geometry.
2. **Solve** structural mechanics of a bracket/shaft/plate (or import a real
   single-solid STEP), display numerical von Mises, deformation and force
   equilibrium.
3. **Replay** a previously computed custom STEP rotor OpenFOAM U/p solution;
   start continuous sourced blade animation. Explicitly distinguish real
   solver time snapshots from kinematic WebGL frames.
4. **Explain mounting loads** with the four-anchor equilibrium calculator and
   distinguish manual thrust inputs from measured or integrated CFD surfaces.
5. Show verifiable source hashes and automated test evidence.

## Independently verified evidence

- **Real source-STEP rotor CFD in OpenFOAM:** [full solver workflow and source provenance](https://github.com/NeonGrade/ForceForge-AI/actions/runs/43674796795).
- **Chromium source-STL looping animation:** [Play/Pause >one revolution](https://github.com/NeonGrade/ForceForge-AI/actions/runs/43675405969).
- **Extended real STEP / tetra10 FEA and wall statics on macOS + Linux:** [green regression](https://github.com/NeonGrade/ForceForge-AI/actions/runs/43723434487).
- **Full real browser CAD/FEA/CFD demo:** [download MP4 + evidence](https://github.com/NeonGrade/ForceForge-AI/actions/runs/43723778286/artifacts/14166096118).
- **Real fan STEP and Gmsh air-mesh browser integration:** [live browser smoke](https://github.com/NeonGrade/ForceForge-AI/actions/runs/43723778305).

New CSV surface-pressure load interface is separately tested and does
not yet provide certified automatic CFD-to-wall structural coupling.

## AI development disclosure and originality

ChatGPT/OpenAI assistance was used for coding, debugging, tests and
documentation; the optional OpenAI API prioritizes bounded candidate
designs. **FEA and CFD values come only from numerical solvers.**

The software builds on experimental engineering infrastructure that existed
before the event. Event work expanded the typed modeling workflow, source
STEP-derived rotor OpenFOAM integration, engineering load transfer, recovery,
visualization and CI. The official rules' event-period code requirement must
be confirmed with organizers; disclosure alone does not establish eligibility.

ForceForge X is a **research prototype**, not a certified product,
unrestricted AI CAD generator or validated full-wall multiphysics installation.
