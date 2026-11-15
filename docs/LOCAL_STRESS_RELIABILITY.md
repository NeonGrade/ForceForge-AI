
## Next engineering milestone: synchronize mesh refinement at BOTH competing hotspots

The v1.1 audit identified two distinct physical stress peaks in the same
unchanged 8 mm drilled-bracket STEP, approximately **19.27 mm apart**.
The earlier refinement placed each new local Gmsh Box field only around the
*original* peak, then compared two fixed 7 mm stress spheres afterwards.
That comparison did not ensure **both spheres had locally refined tetrahedra
in both solutions**.

The continuation on this exact branch now provides a second explicit action,
**Run dual-hotspot re-mesh + 2 independent 3D FEA solves**, directly under
Step 3 on the existing Real STEP page:

1. Finish Step 1 and the existing single-hotspot Step 3 first; two distinct
   physical XYZ peaks must have been found from genuine tetra10 Gauss stresses.
2. Freeze the two reported physical centers **before** launching the next
   solves. Do not re-select the centers in hindsight using new results.
3. Reimport the **identical** STEP bytes twice. Each Gmsh mesh uses a
   `Min` of **two simultaneous 3D Box size fields** at the frozen centers
   (target factors 0.80 and 0.65; radius fraction 0.18). Neither new mesh
   omits the other physical hotspot.
4. Independently solve both quadratic tetra10 systems in crash-isolated,
   85-second bounded workers under the same load, material and fixture.
5. Compare actual tetra count growth, FEM equilibrium, CAD/mesh volume,
   sampled peak drift, and *each fixed 7 mm sphere's* Gauss-weighted mean
   and P90. A <=5% fixed-region screen is only a **preliminary numerical
   trend**. Global peak convergence is reported separately, and real
   contact, clamp corners, yield/fatigue, material certificates and
   experimental stress/strain correlation remain outside the model.
6. Export the dual-hotspot evidence as an independent JSON record;
   a failed additional run must not erase the earlier completed CAD/FEA
   and local stress evidence.

**Computational bounds:** one imported closed STEP solid; no assembly contact;
at most 1,400 input tetrahedra per mesh. If two physical refinement boxes
create too many tetrahedra or fail the >=10% actual growth screen, the study
is explicitly INSUFFICIENT/UNRESOLVED rather than promising a false pass.

CI includes unit tests for source and physical center locking, multi-site
stress regression, clamp risk and fixed-site drift, plus a real Gmsh/
OpenCASCADE STEP -> two 3D remeshes -> tetra10 FEM test on Linux and
macOS ARM64. These tests do not replace interactive Mac Safari acceptance.

---
# ForceForge X v1.1 — Local Stress Validation + Genuine Hotspot Refinement

## Corrected numerical diagnosis (user's actual Mac screenshot)

The originally displayed sampled maximum stresses were:

| Actual tetrahedra | Target edge (mm) | Tip displacement (mm) | Max sampled von Mises (MPa) |
| ---:|---:|---:|---:|
| 413 | 15 | 0.0352 | 19.2361 |
| 583 | 12 | 0.0358 | **18.6683** |
| 701 | 10 | 0.0360 | 22.6327 |

The earlier ChatGPT response incorrectly read the middle stress as 18.8683. The UI's 17.52% stress difference was **correct**:

```
abs(22.6327 - 18.6683) / abs(22.6327) * 100 = 17.516% → 17.52%
```

The issue is engineering interpretation: the global tip displacement stabilizes (0.46% fine/medium) but the moving peak von Mises changes by 17.52%. Displacement stability does not establish stress-convergence, physical support validity, or safe use.

## What actually changed in the FE code

1. The imported-STEP **tetra10 solver** recovers the true 4 Gauss point positions (XYZ, m), von Mises stresses (Pa) and volume-integration weights (m³) in every tetrahedron. Their weights must sum to the real tetrahedral mesh volume. The globally maximal sampled Gauss stress gets an actual physical coordinate, rather than a colored surface-only location.
2. The unchanged physical material region **5–30% of the support-to-tip CAD span** is evaluated by weighted volume mean and weighted 90th percentile von Mises, plus the within-band sampled maximum. The region is fixed in XYZ space; no changing set of top stressed element IDs is compared. Insufficient samples/volume leads to an explicit error.
3. The original three independently solved CAD volumes are now assessed under **separate** statuses:
   - global displacement numerical stability (3% screen, heuristic)
   - finite physical-band stress stability (5% screen, heuristic)
   - moving sampled peak stability (5% screen plus physical hotspot movement)
   - a peak within 5% of the ideal fully clamped face is **NOT verified** as a physical hotspot even if consecutive sampled maxima look alike.
4. The UI reports **LOCAL STRESS NOT VERIFIED** prominently when global displacement looks stable but local stress still changes. It explicitly shows the formula denominator and graphs displacement and three distinct stress quantities versus **actual element counts**, not target sizes or a meaningless unlabeled curve.
5. The new **Run two local hotspot refinements** button:
   - reuses exactly the original STEP SHA and load/material/support conditions
   - reimports the same STEP BRep with real Gmsh 3D `Box` size fields centered on the originally sampled Gauss hotspot in millimetres
   - runs separate quadratic-tetra 3D FEM for local element-size factors 0.60 then 0.45 (relative to baseline, bounded) with independent reaction/volume checks
   - shows the local stress trend, physical peak movement, actual tetra element count and a conservative status
   - rejects over-limit (>1,400 tetra) models; no silent mesh truncation; actual solve stays inside the same crash-isolated macOS-compatible child process with timeouts.
6. All old modal, 3D solid, CAD redesign, robust optimization, uncertainty and ML modules remain intact.


## Competing physical hotspots: two fixed 3D region comparison

The verified Mac FEA of the actual 8 mm L-bracket, 250 N transverse load
identified two competing high-stress sites across the final two
independently re-meshed quadratic-tetra solids:

- Mesh A global maximum: **(6.894, 12.383, 9.155) mm**.
- Mesh B global maximum: **(6.894, 31.651, 9.110) mm**.
- Separation: **19.27 mm**. The *magnitude* of the sampled maximum
  changed only 2.03%, while the physical location switched.

ForceForge therefore no longer uses a moving maximum position as the
sole location-sensitive convergence check. A site is treated as a
**fixed 7 mm spherical physical region**, centered on one of the two
candidate XYZ stress locations, and independently sampled from real
3D Gauss-point stresses in both meshes. Each region has:

- actual Gauss sample count from each mesh and finite sample volume
- volume-weighted stress mean and weighted P90 in MPa in both solutions
- percent change in *that same XYZ region* under real CAD remeshing.

Both spatial regions must pass the numerical <=5% heuristic for a
`PRELIMINARY_COMPETING_HOTSPOT_STABILITY` result. If either physical
region cannot be sampled adequately or exceeds the threshold, the
status is `MULTIPLE_HOTSPOTS_NOT_CORRELATED` and the app displays
an unresolved stress assessment. The global maximum remains
**spatially nonunique** and the tool reports BOTH regions, not a
misleading single "best" hotspot.

This is a quantitative **finite region stress screen** under assumed
loads and *idealized fully fixed* conditions. It does NOT validate
engineering strength, actual fatigue, bolt contact or safety.

---

## What the verdict means

- **PRELIMINARY_LOCAL_STRESS_SCREEN_MET**: multiple independently remeshed numerical samples meet *heuristic* stress and peak-location checks. Does NOT certify safety or independently validate actual material/fixtures.
- **LOCAL_STRESS_NOT_CONVERGED**: at least one stress metric or hotspot position moves too much.
- **SUPPORT_SINGULARITY_RISK**: sampled maximum lies near ideal, fully constrained support. Refinement cannot mathematically guarantee a finite peak here; actual bolts/contact/fillets or regularized stress evaluation may be necessary.
- **REFINEMENT_INSUFFICIENT**: actual element count did not grow meaningfully, regardless of target edge size.

Even if the finite-region mean converges, the global peak at an idealized clamp **cannot** be interpreted as certified local strength. Real measured deflections/strains, material certificates and actual mounting/load paths remain external qualification prerequisites.

## Run on your Mac

```bash
cd ~/ForceForge-AI
git status --short
git fetch origin
git switch --track origin/feature/stress-local-validation-v11
source .venv/bin/activate
python -m pip install -r requirements.txt 'gmsh>=4.12,<5'
python -m pytest -q
python -m streamlit run app.py --server.fileWatcherType none
```

If your local branch already exists:

```bash
git switch feature/stress-local-validation-v11
git pull --ff-only origin feature/stress-local-validation-v11
```

Navigate to the **Real STEP → 3D FEA / CAD redesign** page. The page still does **zero** 3D FE work on loading. Use the original drilled L-bracket at 8 mm, tetra target 12 mm, +X 250 N and support-to-tip Z. Click **Run CAD import + 3D FEA**. Expand the three-mesh screen, run it, and confirm the global displacement and local stress verdicts are separately reported. Then expand **Physically localized stress refinement** and click **Run two local hotspot refinements**.

Every computational step is opt-in. The original CAD step and numerical result remain visible if refinement fails.

## CI engineering gates

- Independently recover 4 Gauss points/tetra and integrate exact mesh volume.
- Recompute screenshot 17.52% to avoid false bug reports.
- Reject changed source SHA, material, force or support.
- Reject a manufactured "pass" for stress at an ideal hard clamp.
- Real 3D Gmsh Box refinement and independent tetra10 FEM with reacted loads on **macOS Python 3.13** and Linux.
- Streamlit acceptance: page loads without solver, explicit buttons trigger actual subprocess FE work, and previous FEA modules still load.

This PR remains draft until CI passes and user Mac visual validation.
