# Real Laboratory Workstation UI (v0.5 preview)

This UI is built on the existing v0.4 real laboratory benchmark branch and keeps the original `app.py` intact.

## Launch (macOS)

```bash
git fetch origin
git switch --track origin/ui/v5-real-lab-workstation
python3 -m pip install -r requirements.txt
python3 -m streamlit run app_ui_v5.py
```

If the branch already exists locally, use `git switch ui/v5-real-lab-workstation` followed by `git pull --ff-only`.

## Desktop experience

- Compact single-screen engineering cockpit (desktop viewport >= 1120 x 735 px).
- Four selectable workspaces: 3D Specimen, Frequency Match, Calibration, Data & Sources.
- Live FE frequency/mode visualization powered by the original `forceforge/modal_benchmark.py` solver.
- Calibration using measured Mode 1 only, with Modes 2 and 3 reported as independent holdout checks.
- Source citation, STEP/STL downloads, optional original Abaqus and MATLAB metadata imports.
- The previous Building/Industrial/Automotive explorer and specialist pages remain reachable from the sidebar.
- Smaller displays intentionally fall back to scrolling rather than clipping essential controls.

## Engineering integrity

Our CAD is reconstructed, not an exact original mesh. Published measurements, the authors' Abaqus benchmark and our independently calculated FEM values must stay distinct. Assumed Young modulus and density are not physical certificates. No actual structural safety certification is claimed.

## Checks

```bash
python3 -m compileall -q app_ui_v5.py
python3 -m pytest -q tests/test_ui_v5.py tests/test_real_lab_ui.py
```

Mac browser inspection and repository CI are required before merging.
