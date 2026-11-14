# ForceForge X v0.3 — A coherent engineering decision workflow

**Problem:** When loads or operating conditions change, what limit governs a structural design, and what section/connection changes improve its modeled response? Without one workflow, engineering teams must run disconnected models and manually interpret results.

## Three clicks for a non-engineer

1. Select a real-life **problem** (roof-truss load path, machine bracket, suspension-link proxy).
2. Challenge operating load and **analyze** the current design; show the controlling model limit.
3. **Find an FEA-verified improvement**; compare current and redesigned member mass and model-limit use. Export numerical evidence if requested.

## Three distinct physical models

| Industry | Implemented analysis | Model limits |
| --- | --- | --- |
| Building | 2D axial pin-jointed truss FEM with ideal bar Euler screening | Not an adopted Michigan building-code load combination; no gussets, welds, lateral bracing |
| Industrial | 2D Euler–Bernoulli beam/frame FEM, P–Δ approximation, thermoelastic strain and equivalent rotational spring | No real anchor/bolted joint, contact pressure or fatigue qualification |
| Automotive | 2D planar projected suspension-link proxy with assumed thermal/mechanical loads | No 3D suspension geometry, bushings, measured road spectrum or OEM approval |

The same CaseInputs/CaseReport/trace structure routes three independent calculations. Never imply the same engineering standards apply to all industries.

## Redesign integrity

- Uniform member **radius ratio** changes area as r² and bending inertia as r⁴.
- For Industrial and Automotive, the search may also alter an **assumed** joint rotational spring (factors 1, 2.5, 5).
- Each candidate is solved by FEA for all three illustrative load cases.
- Among candidates meeting model utilization <= 1.0, the app selects the **lowest modeled member mass**, then smallest stiffness increase. Joint hardware, reinforcement and manufacturing cost are NOT modeled or optimized.
- No feasible candidate → explicit failure, never a fabricated redesign.
- Original results stay associated with exact parameters and are marked stale when controls change; results persist independently for each industry.

## Reproducible example results, load +60% (local Python tests)

| Industry | Initial utilization | Original member mass | Redesigned member mass | Redesigned utilization | Design action |
| --- | ---: | ---: | ---: | ---: | --- |
| Building | 0.4907 | 164.85 kg | 119.10 kg | 0.9401 | radius 0.85x |
| Industrial | 1.793 | 26.63 kg | 32.23 kg | 0.9946 | radius 1.10x, joint spring 2.5x |
| Automotive | 0.1100 | 5.10 kg | 2.50 kg | 0.2158 | radius 0.70x; default deltaT=0K |

These are **example model outputs**, not physical experiments, independent validation, actual safety clearances or globally optimal geometry.

## Previous work preserved

- Advanced Structural Lab: pages/5_Advanced_Structural_Lab.py
- Detailed three-industry FEM scenarios: pages/6_Cross_Industry_Platform.py
- Latest original main-branch FEA, robust optimization, RandomForest surrogate and optional structured-input agent: pages/7_Engineering_Workbench.py

Do not merge the new PR before Mac/browser acceptance. Run all 48 unit/regression tests, verify all three flows, and archive a demo recording. Automated CI runs on each PR.

## Explicit scope of AI

The inherited Engineering Workbench includes a physics-trained truss ML surrogate and natural-language parsing. **The new shared cross-industry redesign is a deterministic FEM-verified design search**, not a trained cross-industry ML model. Later research may add a properly validated physics-specific surrogate with hold-out testing, without changing the single user flow.
