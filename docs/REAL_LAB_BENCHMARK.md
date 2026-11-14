# ForceForge X: From Public Experiment to Calibrated Digital Twin

## The real engineering question

Can a reduced-order FE model reproduce the modal frequencies measured in a
physical steel support beam, and which model assumption most affects mismatch?

The physical test specimen, laboratory sensors and measured frequencies are
documented by Thurn et al. (2026) and an openly licensed dataset. Unlike earlier
ForceForge demonstrations, this workflow uses **external real measurements**.

## Run

Run `python -m streamlit run app.py` in the new feature branch.
On the landing page, rotate the 3D reconstructed beam. The sensor pins are
located at the measured heights. Change the beam's equivalent base support
stiffness. The program re-solves the generalized eigenproblem `K phi = lambda M
phi`; the 3 predicted frequencies and deformed mode shapes update live.

Click **Calibrate using measured Mode 1**. Only the measured 1.569 Hz mode is used
to fit support stiffness. Modes 2 and 3 are held out and tested against
independent 10.389 and 29.619 Hz experimental references. The default
simplified model with E=210 GPa and density=7850 kg/m3 yields approximately
k=471 N m/rad, 10.242 Hz and 29.423 Hz on the held-out modes, i.e. ~1.42%
and ~0.66% relative errors. Do not treat those assumed material values as
specimen-specific tests, or our fit as a measured joint property.

The page can download reconstructed STEP and STL files and link to the actual
official Abaqus `.inp`/`.cae`. Optionally import the official `.inp` to preview its
nodes/beam elements, or the official `.mat` to inspect channels. The original
raw .mat is not bundled (14.4 MB).

Switch to Building, Industrial and Automotive **Industry Explorer** using the
sidebar to see separate forward-looking examples. Their original FEA and
redesign/ML tools are preserved in Engineering Workspace. **Only this laboratory
benchmark currently uses published physical measurements**.

## Verification

- Consistent mass and stiffness beam matrix, modal eigenproblem
- Analytical cantilever frequencies with ideal clamped support
- Model sensitivity to support stiffness
- One-mode calibration, two-mode holdout
- Static linearity, mesh geometry, imported Abaqus node parser
- CI and Streamlit interaction regression tests in GitHub

## Cautions

The authors' Abaqus model uses Timoshenko beam elements, includes acceleration
sensor and magnet masses, and explicitly reduces section around sanded strain
gauges. Our reconstructed beam includes approximate gauge regions but currently
omits attached masses and shear effects. Do not compare the two as if the
models were identical. The published ABAQUS model is shown as a labeled
reference. This is validation of modal frequencies in the specific laboratory
setting, **not** certification of structural safety or prediction of damage.
