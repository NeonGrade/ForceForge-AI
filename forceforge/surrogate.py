"""Random-forest surrogate trained on FEM-generated design data.

Surrogate candidates are ALWAYS re-verified by the physics engine.
A random hold-out on a dense design grid may be optimistic for new topologies;
report that limitation and avoid claiming universal prediction accuracy.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

from .robust import Requirements, evaluate
from .design import TOPOLOGIES

FEATURES = ["height_m", "area_mm2", "topology"]
TARGETS = ["worst_stress_util", "worst_displacement_util", "worst_buckling_util"]


def _features(df: pd.DataFrame, columns=None):
    X = pd.get_dummies(df[FEATURES], columns=["topology"], dtype=float)
    if columns is not None:
        X = X.reindex(columns=columns, fill_value=0.)
    return X


def train(df: pd.DataFrame, *, seed: int = 42):
    samples = df.dropna(subset=FEATURES+TARGETS).copy()
    if len(samples) < 25:
        raise ValueError("Need at least 25 valid FEA samples to train a surrogate")
    # Hold out entire design combinations, not duplicate runs.
    train_ids, test_ids = train_test_split(np.arange(len(samples)), test_size=0.25,
                                           random_state=seed)
    X = _features(samples)
    y = samples[TARGETS]
    model = RandomForestRegressor(n_estimators=130, min_samples_leaf=2,
                                  random_state=seed, n_jobs=-1)
    model.fit(X.iloc[train_ids], y.iloc[train_ids])
    pred = model.predict(X.iloc[test_ids])
    metrics = {}
    for i, target in enumerate(TARGETS):
        metrics[target] = {
            "mae": float(mean_absolute_error(y.iloc[test_ids,i], pred[:,i])),
            "r2": float(r2_score(y.iloc[test_ids,i], pred[:,i])),
        }
    return model, list(X.columns), metrics


def propose_and_verify(model, columns, req: Requirements, *, n: int = 300, seed: int = 99):
    """Stage 1 ML screens broad designs; Stage 2 exact FEA rechecks recommendations."""
    rng = np.random.default_rng(seed)
    candidates = pd.DataFrame({
        "height_m": rng.uniform(.35*req.span_m, .85*req.span_m, n),
        "area_mm2": rng.uniform(100, 800, n),
        "topology": rng.choice(TOPOLOGIES, n),
    })
    pred = model.predict(_features(candidates, columns))
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
    verified = [evaluate(str(row.topology), float(row.height_m), float(row.area_mm2), req)
                for _, row in ranked.iterrows()]
    return pd.DataFrame(verified).sort_values(["feasible", "mass_kg"],
                                               ascending=[False, True])
