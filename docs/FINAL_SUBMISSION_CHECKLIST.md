# Hack The Nest 2026 — Final submission checklist (Nov 15, noon ET)

**Hard cutoff: Sunday, November 15, 2026 at 12:00 PM EST.**
Reference: https://hack-the-nest.devpost.com/rules

Devpost project: https://devpost.com/software/neongarden
Public competition branch:
https://github.com/NeonGrade/ForceForge-AI/tree/hack-the-nest-2026-submission

## Required in the logged-in Devpost project

- [ ] **Project overview:** show correct product name **ForceForge X** (URL slug
  may still say `neongarden`).
- [ ] **Project details:** source branch linked explicitly (the repository's
  default `main` is a different team workspace).
- [ ] Project story / Built With / main track (Future of Intelligence) / AI
  tool implementation and disclosure fields all filled in.
- [ ] **A video of at most 3 minutes**, hosted on YouTube or Vimeo with an
  accessible embedded link. Verify by opening the video URL in a private
  browser window; it must play for judges without Devpost/YouTube login.
- [ ] All real teammates accepted Devpost invitations.
- [ ] Correct academic/sponsor award opt-ins, no unearned claims.
- [ ] Real prior-code reuse disclosed accurately. Event eligibility requires
  organizer confirmation because official rules require competition code
  written within the event period.
- [ ] Click **Submit project**, complete any missing required fields, then
  confirm **Submitted** (not DRAFT / INCOMPLETE SUBMISSION).
- [ ] Hack The Nest team app has project URL
  `https://devpost.com/software/neongarden` saved.

## Demo on the Mac — use the focused judge launcher

Open a new Terminal in the repository checkout. First stop any old Streamlit
server using Control+C in the terminal that launched it (do **not** stop the
Docker daemon or delete numerical output). Then run:

```bash
cd ~/ForceForge-AI
git status --short
git fetch origin
git switch hack-the-nest-2026-submission
git pull --ff-only origin hack-the-nest-2026-submission
source .venv/bin/activate
sh scripts/run_hackathon_demo.sh
```


If Git reports modified local files or diverged history, do **not** use
`reset --hard` or delete local results. Inspect the error first.
The completed OpenFOAM case stays at
`~/.forceforge_x/transient_cfd/2e9aefe6c51efd9d`.

In the browser use http://localhost:8501. Confirm:
1. Natural Language CAD opens; describe and generate one real STEP product.
2. Structural FEA opens and shows real stress/displacement, not invented values.
3. Existing CFD job auto-lists as completed and passes output integrity.
4. Click **Open verified CFD replay**; the blades rotate continuously over a
   genuine held U/p snapshot and discrete solver field frames remain separate.

## Recommended 2-minute recording (no long CFD rerun)

- 00:00–00:15: ForceForge X engineering problem, dedicated app homepage.
- 00:15–00:45: Natural-language product description → validated CAD parameters
  → actual STEP model.
- 00:45–01:20: Replay already-solved OpenFOAM fan fields, pan/zoom source
  geometry and show Play/Pause. **Say reference room**, distinguish blade
  kinematics from actual flow snapshots.
- 01:20–01:48: 3D bracket FEA, stress/displacement and a newly generated
  alternative STEP model.
- 01:48–02:00: Evidence/logs, concise limitations and GitHub link.

Mac screen recording: Shift + Command + 5. Upload recording to YouTube
as **Unlisted**, finish publishing, then enter that URL into Devpost's
mandatory Video demo field. Unlisted must still permit anyone with the
link to watch. Use exact team source code branch above.

An optional CI-generated approximately 30-second reference CFD clip is
available in the `Devpost backup CFD footage from genuine OpenFOAM fields`
GitHub Actions artifacts. It is **a reference case only** and should be
labeled accordingly if used as part of the full demo.

## What cannot be honestly claimed

- Arbitrary unrestricted English-to-any-CAD (four registered families).
- The complete custom wall, grille, bolts, support FEA, or coupled CFD-FEA.
- 49 real OpenFOAM flow snapshots from 3 computed snapshots (the continuous
  rotor position is rigid-body geometry animation).
- Certified accuracy or mesh convergence of the custom fan CFD.

## Evidence links

- Actual custom STEP rotor / moving-mesh OpenFOAM U/p:
  https://github.com/NeonGrade/ForceForge-AI/actions/runs/43674796795
- Chromium continuous geometry Play/Pause loop:
  https://github.com/NeonGrade/ForceForge-AI/actions/runs/43675405969
- Native Linux + macOS CAD/FEA:
  https://github.com/NeonGrade/ForceForge-AI/actions/runs/43675409014
- Hackathon-specific landing and replay smoke:
  https://github.com/NeonGrade/ForceForge-AI/actions/runs/43721821071
