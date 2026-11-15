# English Agent and ML adaptation for Workspace v1.0

Zihan's integration builds on UI PR #21 (`eb3dc6f`) and the unified-host CI fixes in PR #20 (`fcf7a19`). The original 2D/3D calculations, scene navigation, input persistence and study controls remain in their respective modules. This is a review branch, not a merged release.

## English questions and parameter changes

Open `python web_server.py --port 8000`, then `http://127.0.0.1:8000/workspace/` and **AI Brief**. The assistant works offline without an API key. It routes questions separately from input changes:

| Example | Behavior |
| --- | --- |
| Why does this design fail? | Explains the governing actual scenario utilization, including Euler buckling. |
| What is the displacement and stress? | Quotes the completed nominal axial-bar FEA result, distinct from worst-scenario checks. |
| What do uncertainty scenarios mean? | Explains the current load, modulus and area envelope and safety factors. |
| How can I make this 2 m truss lighter? | Describes the Optimize/ML→FEA workflow without inventing a candidate. |
| How accurate is the ML surrogate? | Explains available validation and applicability; does not invent a score or retrain. |
| Increase the load by 20% | Previews only the central load change using the current case. |
| Set span to 3 m and height to 1.1 m | Previews both explicit values; other inputs remain unchanged. |
| Set the section area to 230 mm² | Previews the uniform bar area; no solve before confirmation. |

Span: 0.5–4 m; load: 100–3000 N; height: 0.2–1.25 times span; section area: 60–800 mm²; displacement limit: 0.25–12 mm. Bounds use the same server validation as manual workspace inputs. A span change that makes the existing height invalid must include a valid height. Ambiguous, non-finite and unsupported requests fail without changing the case. Use controls for topology, material, uncertainty and safety-factor settings.

The existing `/api/interpret` remains available for legacy clients. The new UI uses `/api/agent/ask` and `/api/agent/confirm`; it does not silently insert the legacy parser's defaults into partial requests. Editing the request or model invalidates a preview. Applying a confirmed change saves inputs in the same tab and runs a fresh FEA; refresh restores inputs and recomputes results.

Questions require the ID of a completed, server-held 2D analysis matching all current inputs and the solver context. The cache is bounded to 32 reports. Client-supplied result fields are ignored; changed, missing, evicted or cross-workspace evidence is rejected. Answers identify the actual completed load/geometry, even when a question mentions another load. Asking a question never invokes FEA, optimization, ML or an external model. Unsupported topics receive a clarification response.

## ML evidence in the new website

**ML Verify** now exposes both grouped-design and whole-height holdouts. The latter holds out complete height groups and reports its limits; neither establishes new-topology or CAD generalization. Changing validation strategy clears old displayed metrics and rejects an older in-flight response. Requirement changes invalidate the displayed ML run.

The server exports the exact requirements and solver-source hashes, context ID, fitted domain, partition metadata, three-target MAE/R² and mean-baseline MAE, plus 12 shortlisted candidates re-solved after screening 300 proposals. Each candidate includes predicted and actual utilization, absolute prediction error, feasibility and an FEA-verification flag. The dedicated validation export and Workspace study export retain this evidence.

## 3D and v1.1 compatibility

The same host preserves `/api/3d/cad/agent/*`. Truss and CAD review caches and input schemas remain separate. A 2D review ID cannot answer a CAD question. Real CAD still uses the bounded isolated worker and actual tetra10 solver.

PR #16 (`4ab70e6`) introduces separate global-displacement, local-peak and fixed-physical-band stress evidence. The Agent review accepts those additional fields when supplied by that solver and reports them independently. For example, global displacement stability with `PEAK_STRESS_UNRESOLVED` remains `REVIEW_REQUIRED`, and a 17.52% sampled-stress change is reported as such. Without v1.1 evidence, local-stress status remains `NOT_EVALUATED`. This adaptation does not merge or claim execution of the v1.1 stress-remeshing engine.

## Verification and remaining acceptance

Run `python -m pytest -q` with Node and optional Gmsh installed. New regressions cover partial requests, atomic rejection, stale confirmations, actual-result answers without recomputation, forged/evicted evidence, context-bound whole-height exports, real unified HTTP 2D/3D Agent routing, and separate local-stress states. CI includes the unified branch family and UI-targeted review branches; Linux/macOS Gmsh jobs exercise the actual integrated routes.

Automated results and local browser checks are branch evidence. Final designated team Mac/Safari walkthrough and team demo acceptance remain separate. No structural certification, arbitrary English question coverage, physical static validation or 3D surrogate accuracy is asserted.
