# ForceForge AI 2.0 | 24-hour three-person sprint

**Time zone: America/Detroit (EST)**. Target live demo: Sun Nov 15, 2026, 1:15 PM.
Final Devpost deadline: Sun 12:00 PM; draft: Sat midnight, as shown in the app.
Start time is assumed ~Sat noon. Shift intermediate milestones if later.

## Roles (subject to actual skill confirmation)

| Member | Owns | Can review independently |
|---|---|---|
| Engineering lead (Yusen) | `forceforge/physics.py`, `forceforge/robust.py`, analytical checks | Model limits, buckling assumptions, benchmark |
| Coding / AI lead (assigned by team) | `forceforge/surrogate.py`, `forceforge/agent.py`, API and integration | Leakage, held-out metrics, model outputs |
| Product / UX lead (assigned by team) | `app.py`, demo video, README, Devpost and Q&A | Layout, reproducibility, usability, submission |

## Gates (P0 cannot be skipped)

| Elapsed time | Gate | Owner | Acceptance |
|---|---|---|---|
| T+0:00 to T+1:00 | Environment and repository | All | Fresh install and `pytest` success |
| T+1:00 to T+3:00 | P0 numerical solver | Engineering | Analytical 3-bar reference matches, equilibrium |
| T+2:00 to T+5:00 | P0 UI + 3 preset truss families | Product | Load, dimensions, chart and metrics interact |
| T+3:00 to T+6:00 | P0 robust scenario optimizer | Engineering | Stress, nodal displacement and ideal buckling checks |
| T+5:00 to T+8:00 | P0 end-to-end result | All | Full design → challenge → FEA-verified redesign |
| T+6:00 to T+10:00 | P1 ML surrogate and evaluation | Coding/AI | Holdout MAE, FEA verification of recommendations |
| T+8:00 to T+11:00 | P1 LLM brief parser / explanations | Coding/AI | Typed, validated requirements; offline fallback |
| T+10:00 to T+12:00 | Submission draft | Product | Devpost draft saved and shared before midnight |
| T+12:00 to T+20:00 | Reliability, optional sensitivity, sleep/buffer | All | No numerical regression and recorded demo |
| Sun 09:00 to 11:30 | Finalization and submission | All | Repo README, screenshots, submitted Devpost |
| Sun 12:00 | Hard stop for submission | Captain | Submission already confirmed |
| Sun 13:15 | Live judging | All | 90-second sequence, fallback recording available |

## MVP stop line

When T+6 hours pass, stop adding features unless all P0 checks pass and
there is a reproducible live demo. The AI assistant is a P1 feature. If
there is only 1 competent developer, prioritize physics -> robust -> UI.

## Verifiable user story for judges

Given a 2 m truss under 1000 N with a 2 mm nodal displacement limit,
engineer selects material. System computes response and searches stable
family/section candidates. Judge increases load to 1200 N and lowers E
and member area. The system recomputes stresses, displacements, and ideal
buckling ratios. A surrogate model proposes additional candidates but
**the exact FEA solver decides feasibility**.

## Metrics for final presentation

- FEA regression numerical error on analytical 3-bar case
- Count of FEA evaluated candidates and feasible candidates
- Nominal mass change vs the same-topology starting baseline (if baseline exists)
- Robust worst scenario utilization of recommended design
- ML heldout MAE / R² by each output, and number of re-verified ML proposals
- End-to-end runtime on actual demo laptop; measure rather than assume

## Safety and integrity

No real-world safety certification. Buckling is a simplified ideal pinned-
pinned bar estimate. The script simulates all data; do not misrepresent
simulated designs as physical tests. Numerical performance, time-to-result,
and comparative improvements must be measured on the actual hardware.
