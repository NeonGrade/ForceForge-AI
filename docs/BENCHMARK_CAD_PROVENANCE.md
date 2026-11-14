# ForceForge X / laboratory beam: provenance and permitted reuse

**Original real experiment:** A physical laboratory steel beam, measured at
Leibniz University Hannover by Thurn, Jonscher, Hofmeister, Zorzi and Rolfes.

- Peer-reviewed source: Thurn et al. (2026), *Virtual sensing for strain estimation in wind turbine support structures based on a biaxial accelerometer*, *Wind Energy Science*, 11, 3359–3376. DOI: **10.5194/wes-11-3359-2026**. **CC BY 4.0**.
- Raw measured time series and authors' original Abaqus `.inp` / `.cae`:
  Thurn, Jonscher, Rolfes (2025), *A benchmark structure for virtual sensing on tower structures*. DOI **10.25835/lyav246d**. **CC BY 3.0**.
- Source dataset: https://data.uni-hannover.de/en/dataset/a-benchmark-structure-for-virtual-sensing-on-tower-structures
- Paper source: https://wes.copernicus.org/articles/11/3359/2026/index.html

## What is real versus recreated

**Actual lab measurements (transcribed from the paper, Table 2):**
1.569 Hz, 10.389 Hz and 29.619 Hz for the first 3 transverse bending
modes. Published updated Abaqus FE results: 1.698 Hz, 10.775 Hz and 30.590 Hz.
Published MAC comparisons for those mode shapes: 0.9989, 0.9999 and 0.9999.
Measured sensor heights (paper Table 1): MP1 1.462 m, MP2 1.098 m,
MP3 0.829 m, MP4 0.798 m, MP5 0.393 m.

**Reconstructed, NOT copied author CAD:** The included `.step` and `.stl`
files represent only the 1.524 m beam, 30 mm wide, 5.2 mm nominal thickness;
two 60 mm portions around strain gauge locations are thinned to 5.0 mm.
They are generated with CadQuery from open article dimensions, with modifications
so that the physical bar can be rotated and meshed locally without Abaqus.
They OMIT clamps, sensor bodies/masses, magnet, specific steel heat and detailed
sanding surface texture. They are educational geometry recreations of a *real*
physical test specimen, not the exact original FE assembly or source STEP.

**Our original solver:** 2D consistent-mass Euler–Bernoulli beam eigenvalue
analysis, user-adjustable Young's modulus, density and rotational base support.
No author Abaqus calculations are imported as our output; the published FE
frequencies are shown as a **separate reference**.

**Calibration and independent check:** Only the *measured first* eigenfrequency
is used to fit one effective rotational-support parameter. Modes 2 and 3 remain
untouched external measured frequencies, providing an independent validation
check at the chosen model fidelity. If a model parameter changes, the apparent
agreement must be recomputed; never claim the support spring is physically
measured or this implies qualification for engineering safety.

**License:** The original paper and data remain owned and licensed by the
credited authors under the respective CC BY licenses. Attribution and license
notices must be kept when redistributing derivative geometry or measurement
transcriptions. Our Python implementation is project source code.

**Optional raw data:** The university offers the full raw `.mat` measurements,
original Abaqus `.inp` and `.cae`. The Streamlit page permits user-provided
uploads, with cautious variable inspection. We have not yet established an
automatic raw time-series channel mapping and do not claim time-domain error
correlation until the original time-series channels and units are checked.
