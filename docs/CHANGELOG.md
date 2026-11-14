# ForceForge X — Change Log and Non-Regression Policy

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
