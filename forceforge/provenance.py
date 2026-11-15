"""Bind a truss surrogate to its exact solver sources and engineering inputs."""
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import json
import math


def context_id(value: dict) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode()).hexdigest()


def truss_context(req) -> dict:
    req.validate()
    requirements = {key: float(value) for key, value in asdict(req).items()}
    if not all(math.isfinite(value) for value in requirements.values()):
        raise ValueError("Engineering context must contain finite values")
    root = Path(__file__).parent
    source = sha256()
    for name in ("physics.py", "design.py", "robust.py"):
        source.update(name.encode() + b"\0" + (root / name).read_bytes())
    return {"solver": "2d-pin-truss", "solver_sha256": source.hexdigest(),
            "requirements": requirements}
