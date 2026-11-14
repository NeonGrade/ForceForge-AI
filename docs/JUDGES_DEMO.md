# 90-second judge demo — ForceForge X

**0–15 s: Problem.** When a load changes, a seemingly optimized support can exceed its modeled displacement or stress limit. Engineers need fast FEA-supported alternatives, but most interfaces require deep solver familiarity.

**15–30 s: Pick an example.** Choose **Machine mounting bracket**. Explain that the simplified model has a flexible base joint and a cantilever beam.

**30–45 s: Challenge.** Choose **Heavier load (+60%)**, then **Analyze the current design**. The sample FEA reports model utilization ~**179%** of a specified *illustrative limit*.

**45–70 s: Improve.** Click **Find an FEA-verified improvement**. It searches candidate radius and assumed joint-stiffness options, then reruns the FEM: example modeled member mass **26.63 -> 32.23 kg**, modeled utilization **1.793 -> 0.995**. The latter assumes **2.5x joint rotational stiffness**, NOT a designed or tested connection. Explain the mass tradeoff and the unresolved connection hardware.

**70–80 s: Cross-sector reuse.** Switch to roof truss or planar suspension link. Same interaction; different solver and different qualification gaps. Avoid comparing absolute masses between unrelated structures.

**80–90 s: Credibility.** Open engineering evidence to show exact solver outputs, assumptions, missing experimental/code checks and reproducible JSON. GitHub shows the tests and preserved advanced ML/physics tools.

**FAQ: Is this safe/certified?** No. The checks are model examples, not physical certification. Actual approval needs adopted engineering standards, real loads/materials and proper signoff.

**FAQ: Is the entire redesign AI?** No. This cross-sector version searches deterministic, FEA-rechecked alternatives. An existing RandomForest surrogate and optional language-model requirement parser remain in the specialist truss workbench. Do not conflate them with the FEA solver.
