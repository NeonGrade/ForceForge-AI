"""Random-forest surrogate trained on FEM-generated design data.

Surrogate candidates are ALWAYS re-verified by the physics engine.
A random hold-out on a dense design grid may be optimistic for new topologies;
report that limitation and avoid claiming universal prediction accuracy.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.dummy import DummyRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupShuffleSplit

from .robust import Requirements, evaluate
from .design import TOPOLOGIES
from .provenance import context_id, truss_context

FEATURES = ["height_m", "area_mm2", "topology"]
TARGETS = ["worst_stress_util", "worst_displacement_util", "worst_buckling_util"]


def _features(df: pd.DataFrame, columns=None):
    X = pd.get_dummies(df[FEATURES], columns=["topology"], dtype=float)
    if columns is not None:
        X = X.reindex(columns=columns, fill_value=0.)
    return X


def train(df: pd.DataFrame, *, seed: int = 42, validation_strategy: str = "design"):
    context = df.attrs.get("forceforge_context")
    if not context or context != truss_context(Requirements(**context["requirements"])):
        raise ValueError("FEA context missing or stale; regenerate labels with grid_search(req)")
    if validation_strategy not in ("design", "height"):
        raise ValueError("Validation strategy must be design or height")
    samples = df.dropna(subset=FEATURES+TARGETS).copy()
    numeric = ["height_m", "area_mm2"] + TARGETS
    samples = samples[np.isfinite(samples[numeric]).all(axis=1)]
    if not samples.topology.isin(TOPOLOGIES).all():
        raise ValueError("Only the implemented 2D truss topologies are supported")
    if (samples[numeric] < 0).any().any():
        raise ValueError("Geometry and utilization labels cannot be negative")
    spread = samples.groupby(FEATURES)[TARGETS].agg(lambda x: x.max() - x.min())
    if (spread > 1e-10).any().any():
        raise ValueError("Conflicting FEA labels for the same design; do not mix engineering contexts")
    if len(samples) < 25:
        raise ValueError("Need at least 25 valid FEA samples to train a surrogate")
    # Hold out entire design combinations, not duplicate runs.
    group_columns = FEATURES if validation_strategy == "design" else ["height_m"]
    groups = samples.groupby(group_columns, sort=True).ngroup().to_numpy()
    minimum = 4 if validation_strategy == "design" else 3
    if len(np.unique(groups)) < minimum:
        raise ValueError(f"Need at least {minimum} distinct validation groups")
    train_ids, test_ids = next(GroupShuffleSplit(
        n_splits=1, test_size=0.25, random_state=seed
    ).split(samples, groups=groups))
    X = _features(samples)
    y = samples[TARGETS]
    model = RandomForestRegressor(n_estimators=130, min_samples_leaf=2,
                                  random_state=seed, n_jobs=-1)
    model.fit(X.iloc[train_ids], y.iloc[train_ids])
    model.forceforge_context_ = context
    model.forceforge_context_id_ = context_id(context)
    pred = model.predict(X.iloc[test_ids])
    baseline = DummyRegressor(strategy="mean").fit(X.iloc[train_ids], y.iloc[train_ids])
    baseline_pred = baseline.predict(X.iloc[test_ids])
    fitted_samples = samples.iloc[train_ids]
    model.forceforge_domain_ = {
        "height_m": (float(fitted_samples.height_m.min()), float(fitted_samples.height_m.max())),
        "area_mm2": (float(fitted_samples.area_mm2.min()), float(fitted_samples.area_mm2.max())),
        "topologies": sorted(fitted_samples.topology.unique()),
    }
    model.forceforge_validation_ = {
        "method": ("Grouped holdout by topology, height and area; interpolation only"
                   if validation_strategy == "design" else
                   "Whole-height-group holdout within known truss families; not new-topology validation"),
        "strategy": validation_strategy,
        "train_rows": len(train_ids), "test_rows": len(test_ids),
        "train_groups": sorted(set(groups[train_ids].tolist())),
        "test_groups": sorted(set(groups[test_ids].tolist())),
        "train_heights_m": sorted(samples.iloc[train_ids].height_m.unique().tolist()),
        "test_heights_m": sorted(samples.iloc[test_ids].height_m.unique().tolist()),
    }
    metrics = {}
    for i, target in enumerate(TARGETS):
        metrics[target] = {
            "mae": float(mean_absolute_error(y.iloc[test_ids,i], pred[:,i])),
            "r2": float(r2_score(y.iloc[test_ids,i], pred[:,i])),
            "baseline_mae": float(mean_absolute_error(y.iloc[test_ids,i], baseline_pred[:,i])),
        }
    return model, list(X.columns), metrics


def propose_and_verify(model, columns, req: Requirements, *, n: int = 300, seed: int = 99):
    """Stage 1 ML screens broad designs; Stage 2 exact FEA rechecks recommendations."""
    rng = np.random.default_rng(seed)
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 5000:
        raise ValueError("Candidate count must be an integer from 1 to 5000")
    req.validate()
    if getattr(model, "forceforge_context_id_", None) != context_id(truss_context(req)):
        raise ValueError("Surrogate context changed: retrain for the current load, material, limits and solver")
    domain = model.forceforge_domain_
    candidates = pd.DataFrame({
        "height_m": rng.uniform(*domain["height_m"], n),
        "area_mm2": rng.uniform(*domain["area_mm2"], n),
        "topology": rng.choice(domain["topologies"], n),
    })
    pred = model.predict(_features(candidates, columns))
    if not np.isfinite(pred).all():
        raise ValueError("Surrogate returned non-finite predictions; no candidates accepted")
    candidates["predicted_worst_util"] = pred.max(axis=1)
    # Lightweight proposals that the model predicts pass, plus fallback low-mass.
    mass_proxies = []
    for _, row in candidates.iterrows():
        from .design import make_truss
        t = make_truss(str(row.topology), req.span_m, float(row.height_m),
                       float(row.area_mm2), req.base_load_n, req.material)
        mass_proxies.append(float(np.sum([np.linalg.norm(t.nodes_m[b]-t.nodes_m[a])
                                         for a,b in t.elements]) * row.area_mm2*1e-6
                                  * req.density_kg_m3))
    candidates["estimated_mass_kg"] = mass_proxies
    candidates["predicted_feasible"] = candidates["predicted_worst_util"] <= 1.0
    ranked = candidates.sort_values(["predicted_feasible", "estimated_mass_kg"],
                                    ascending=[False, True]).head(12)
    verified = []
    for _, row in ranked.iterrows():
        result = evaluate(str(row.topology), float(row.height_m), float(row.area_mm2), req)
        result.update(predicted_worst_util=float(row.predicted_worst_util),
                      prediction_abs_error=abs(float(row.predicted_worst_util) - result["worst_utilization"]),
                      fea_verified=True, requirements_id=model.forceforge_context_id_)
        verified.append(result)
    return pd.DataFrame(verified).sort_values(["feasible", "mass_kg"],
                                               ascending=[False, True])

