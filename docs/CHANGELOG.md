# ForceForge X — Change Log and Non-Regression Policy

## v0.4 (draft feature/real-lab-benchmark-v4, 2026-11-14)
- Primary landing is now a physical laboratory steel beam with published CC-BY measurements and downloadable STEP/STL reconstruction.
- Real specimen: L=1.524 m; 30×5.2 mm section with reduced 5.0 mm regions; exact reported MP1..MP5 sensor elevations.
- New custom 2D modal beam FEA, support stiffness slider, 3D mode animation/deformation viewer, experimental frequency comparison, first-mode calibration and held-out mode 2/3 checks.
- Original Abaqus .inp and measurement .mat can be uploaded; parsed output is descriptive only until measurement channels and unit conventions are confirmed.
- Cross-industry v0.3 mission flow preserved in Industry Explorer, old FEA/ML workbench retained; no false claims about real 3D bracket or automotive validation.
- Added source/license attribution and regression tests. The Mac must still test the deployed UI and downloaded CAD files.


## v0.3 (draft branch feature/decision-studio-v3, November 14, 2026)
- A coherent **3-step** product landing: Choose the engineering problem -> Challenge the load -> Compare solver-verified improvement.
- Uniform cross-industry candidate interface with physically consistent member radius scaling; connection-spring alternatives explicitly labeled as assumed and unpriced.
- Added per-industry session history and stale-input warning, so a later run cannot silently re-label an earlier calculation.
- Restored all advanced physical and AI modules in dedicated Engineering Workspace pages, taking the latest *main* workbench version rather than older forked UI code.
- Added 3 golden-case numerical baselines, source syntax tests, and GitHub Actions pytest checks. 48 local tests passed before PR.
- **No new code certification, experimental qualification, plasticity, contact, 3D suspension or fluid solver claims.**

## v0.2 (cross-industry draft PR #3)
Typed industry case routing and 3 simplified scenarios per sector, audit trace and evidence gates.

## v0.1 (advanced-physics draft PR #2)
Euler–Bernoulli frame, semi-rigid spring, thermal expansion, approximate second-order P–Δ, illustrative S–N fatigue.

## Stable main before v0.3
2D truss FEA, validated three-bar benchmark, robust search, FEA challenge/reoptimization, RandomForest surrogate and structured design brief parsing.

**Definition of Done:** User can show a concrete problem, numerical calculation, failed constraint or remaining margin, engineering revision and evidence. All existing numerical tests remain green. A new feature may not silently revert earlier solver/UI fixes.
