# ForceForge X — Record your own 2:30 Devpost demo

**Goal:** authentic Mac screen recording, spoken English, maximum 3 minutes.
**Target runtime:** 2 minutes 35 seconds; record six short clips and combine
in iMovie. Physical simulations must be recorded from ACTUAL completed runs.

**Do not claim:** arbitrary text-to-any-CAD, fully coupled wall material
CFD-FEA, CFD fields invented between saved frames, measured anchor capacity,
or full wall/grille/bolt geometry in OpenFOAM reference-domain CFD.

## Before recording: refresh and prepare, then record

First stop the existing Streamlit process in its Terminal with Ctrl+C.
Do not stop Docker or delete local CFD job data.

```bash
cd ~/ForceForge-AI
git status --short
git fetch origin
git switch hack-the-nest-2026-submission
git pull --ff-only origin hack-the-nest-2026-submission
source .venv/bin/activate
sh scripts/run_hackathon_demo.sh
```


If Git stops because of uncommitted local changes, inspect them and do
not force reset. Visit http://localhost:8501 in Chrome and hard-refresh
with Command+Shift+R. Set browser zoom to 90% if needed.

Pre-run the expensive steps BEFORE recording:
- **CAD:** Natural Language CAD, choose the **Wall fan (Chinese)** sample,
  press **Interpret engineering requirements**, select the explicitly
  labeled **DEMO defaults** checkbox for missing geometry, press
  **Generate STEP and execute READY engineering stages**, verify STEP and
  real 3D OCC geometry; optionally **Extract actual rotating blades
  from my STEP (real STL)**.
- **FEA:** Structural FEA, choose **Editable 3D L-bracket** in its SIDEBAR,
  press **Run CAD import + 3D FEA**, wait until von Mises and tip
  displacement genuinely appear. Do not relaunch if live recording.
- **CFD:** The verified local reference job on this machine is
  `2e9aefe6c51efd9d`. On the NEW homepage select its verified
  entry and click **Play real CFD & rotating blades** to see the finished
  fields. If switching browser sessions loses a selected job, use
  **Recover an existing real CFD job after browser reconnect**, paste
  the job ID and press **Restore existing CFD results**. DO NOT click
  **Run genuine OpenFOAM** for a brief demo.
- **Wall loads:** Open Wall Load Transfer, keep explicitly labeled
  demonstration inputs or enter independently known real values, press
  **Calculate actual 4-anchor static reactions** and show the
  force/moment equilibrium plus per-anchor chart.

**Recording:** macOS Shift+Command+5 → Record Selected Portion / Entire
Screen → Options → Microphone → MacBook Microphone → Record. Enable Do Not
Disturb before recording. Alternatively capture silent clips and record
narration into iMovie after importing them. Avoid private files, tabs and
identifiers. Trim out loading/spinner time; do not replace a solver result
with a static fabricated rendering.

## Exact scene plan and narration (about 2:35 total)

### Clip 1 — 0:00–0:14 | Engineering problem and home

Screen: show polished ForceForge X landing screen, briefly point at the
four supported workflows. No random browser tabs.

**Speak:**
"Most AI tools can generate a three-dimensional model. But engineers
need evidence that a design will actually work. This is ForceForge X,
our natural-language engineering workbench."

### Clip 2 — 0:14–0:48 | Real natural-language CAD

Screen: click **Open Natural Language CAD**. Choose the existing sample
**Wall fan (Chinese)**; display the user's dimensional description.
Click **Interpret engineering requirements**, show typed schema and
explicit assumption consent. Press **Generate STEP and execute READY
engineering stages** or cut to a previously completed result. Rotate
the 3D OCC surface mesh, briefly show **Download genuine CAD STEP**.

**Speak:**
"First, I describe a wall-mounted fan in ordinary language. ForceForge
extracts dimensions into an explicit engineering schema. After I approve
clearly labeled conceptual assumptions, it generates a real STEP model
using OpenCASCADE. I can rotate the actual geometry, inspect its dimensions,
and export it for another engineering tool. This is geometry, not an
AI-generated picture."

### Clip 3 — 0:48–1:19 | Real 3D FEA

Screen: navigate **Open Structural FEA**. In the SIDEBAR choose
**Editable 3D L-bracket**, then show the precomputed output from
**Run CAD import + 3D FEA**. Zoom the actual stress/displacement
visualization; point at tetrahedral mesh, peak sampled von Mises and
reaction residual. Keep numerical values visible and do not invent
material validation.

**Speak:**
"Next, we verify the structure. ForceForge generates a real three-
dimensional tetrahedral mesh and solves a quadratic finite-element
model. Here I can inspect deformation, sampled von Mises stress,
and force equilibrium. These values come from the numerical solver,
with declared material and loading assumptions, and are linked to
the exact CAD source."

### Clip 4 — 1:19–1:59 | Actual OpenFOAM and rotor animation

Screen: return to the ForceForge X home; use **Play real CFD &
rotating blades** for the already finished job or restore it in
**Open Transient CFD**. This specific example is the official
reference rotor, **600 RPM** and **three real U/p frames**. Show
**Play continuous rotor**, pause briefly, orbit 3D, then show the real
time-snapshot slider. NEVER rerun OpenFOAM during recording.

**Speak:**
"Now we inspect real computational fluid dynamics. This recording
replays a completed OpenFOAM reference-room simulation with actual
transient velocity and pressure fields. We have also tested the
insertion of a custom STEP-derived rotor into this reference domain.
The rotating blade is the physical rotor geometry shown in motion;
the smooth intermediate positions are kinematic animation, not new
CFD solutions. That distinction is important for trustworthy results."

### Clip 5 — 1:59–2:23 | Wall mounting load transfer

Screen: **Open Wall Load Transfer**, use clearly labeled demonstration
inputs, click **Calculate actual 4-anchor static reactions**,
display individual tension/shear demand and small equilibrium errors.
Do not call it full wall/bolt FEA.

**Speak:**
"Installation loads also matter. Given the fan mass, its offset from
the wall and externally supplied aerodynamic forces, our four-anchor
model balances forces and moments and shows the tension and shear
demand at each connection. This is a transparent static load-transfer
calculation, not a validated wall-contact finite-element simulation."

### Clip 6 — 2:23–2:36 | Evidence and closing

Screen: return to the homepage engineering evidence and public GitHub
branch, ending with ForceForge X header.

**Speak:**
"ForceForge X connects an engineering idea to real CAD geometry and
independently computed physical evidence. We also show the assumptions
and the limits of every result. Thank you."

## Export and submit

- In iMovie, start **New Movie**, import clips 1–6, arrange in order,
  trim empty time, normalize recorded speech, and keep music below the
  narrator (or omit music). Export 1080p MP4.
- YouTube Studio → Create → Upload videos → Visibility **Unlisted** →
  Publish. Open the actual watch URL in a private browser window.
- Devpost project: https://devpost.com/software/neongarden
- Project code:
  https://github.com/NeonGrade/ForceForge-AI/tree/hack-the-nest-2026-submission
- Check project title **ForceForge X**, collaborators, AI disclosure and
  valid watch link. Click **Submit project** and verify **Submitted**
  before the Nov 15, 2026 12:00 PM ET final deadline.

*If the live browser view fails to display a verified model, do not
represent an offline thumbnail or placeholder as a successful live
simulation. Use the already independently checked real recording and
explain the scope transparently.*
