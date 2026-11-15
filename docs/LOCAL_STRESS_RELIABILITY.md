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
