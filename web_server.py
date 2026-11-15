"""ForceForge Workspace: no-build web UI backed by the existing physics engine.

Run from the ForceForge-AI repository root with ``python web_server.py``.
The original Streamlit application remains available as ``app.py``.
"""
from __future__ import annotations

import argparse
import json
import math
import mimetypes
from dataclasses import replace
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
import pandas as pd

from forceforge.agent import interpret
from forceforge.design import TOPOLOGIES, make_truss
from forceforge.physics import solve
from forceforge.robust import Requirements, best_feasible, evaluate, grid_search, pareto_front
from forceforge.sensitivity import elasticities
from forceforge.surrogate import propose_and_verify, train

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "web"
WORKSPACE_VERSION = "1.0.0"
WORKSPACE_NAME = "ForceForge X / Engineering Workspace"


def workspace_manifest(*, studio_available: bool = False) -> dict:
    """Report capability boundaries; never imply physical certification."""
    return {
        "product": WORKSPACE_NAME,
        "workspace_version": WORKSPACE_VERSION,
        "workspace_path": "/workspace/",
        "default_space": "2d",
        "spaces": {
            "2d": {"available": True, "method": "2D linear elastic axial truss FEA"},
            "3d": {"available": studio_available,
                   "method": "Separate volumetric, CAD and modal solvers"},
        },
        "evidence": "Numerical analysis under stated assumptions; no structural certification",
    }
MATERIALS = {
    "steel": (200e9, 7850.0, 250e6),
    "aluminum": (70e9, 2700.0, 150e6),
}


class InputError(ValueError):
    """Validation failure that can be safely shown to the user."""


def number(data: dict, key: str, default: float, low: float, high: float) -> float:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{key} must be a number")
    out = float(value)
    if not math.isfinite(out) or not low <= out <= high:
        raise InputError(f"{key} must be between {low:g} and {high:g}")
    return out


def parse_config(data: dict) -> tuple[Requirements, str, float, float]:
    if not isinstance(data, dict):
        raise InputError("Expected a JSON object")
    material_key = data.get("material", "steel")
    if material_key not in MATERIALS:
        raise InputError("Material must be steel or aluminum")
    topology = data.get("topology", "Triangle")
    if topology not in TOPOLOGIES:
        raise InputError("Unknown topology")
    span = number(data, "span_m", 2.0, 0.5, 4.0)
    height = number(data, "height_m", span * 0.5, span * 0.2, span * 1.25)
    area = number(data, "area_mm2", 180.0, 60.0, 800.0)
    E, density, sy = MATERIALS[material_key]
    req = Requirements(
        span_m=span,
        base_load_n=number(data, "base_load_n", 1000.0, 100.0, 3000.0),
        material_E_pa=E,
        density_kg_m3=density,
        yield_pa=sy,
        max_displacement_mm=number(data, "max_displacement_mm", 2.0, 0.25, 12.0),
        yield_safety_factor=number(data, "yield_safety_factor", 2.0, 1.0, 4.0),
        buckling_safety_factor=number(data, "buckling_safety_factor", 2.0, 1.0, 4.0),
        load_uncertainty=number(data, "load_uncertainty", 0.2, 0.0, 0.5),
        e_uncertainty=number(data, "e_uncertainty", 0.1, 0.0, 0.35),
        area_uncertainty=number(data, "area_uncertainty", 0.1, 0.0, 0.25),
    )
    req.validate()
    return req, topology, height, area


def clean(value):
    """Convert NumPy/Pandas results to strict, finite JSON values."""
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        v = float(value)
        return v if math.isfinite(v) else None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.ndarray, list, tuple)):
        return [clean(x) for x in value]
    if isinstance(value, pd.DataFrame):
        return [clean(row) for row in value.to_dict(orient="records")]
    if isinstance(value, pd.Series):
        return clean(value.to_dict())
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if value is None or isinstance(value, (int, str)):
        return value
    return str(value)


def analysis_payload(req: Requirements, topology: str, height: float, area: float,
                     *, load_factor: float = 1.0, e_factor: float = 1.0,
                     area_factor: float = 1.0) -> dict:
    truss = make_truss(topology, req.span_m, height, area, req.base_load_n, req.material)
    result = solve(truss, load_factor=load_factor, e_factor=e_factor, area_factor=area_factor)
    support_map = {int(node): (bool(fx), bool(fy)) for node, fx, fy in truss.supports}
    nodes = []
    for idx, (x, y) in enumerate(truss.nodes_m):
        sx, sy = support_map.get(idx, (False, False))
        u = result.disp_m[idx] * 1000.0
        nodes.append({
            "id": idx, "x_m": float(x), "y_m": float(y),
            "ux_mm": float(u[0]), "uy_mm": float(u[1]),
            "displacement_mm": float(np.linalg.norm(u)),
            "load_x_n": float(truss.forces_n[idx, 0] * load_factor),
            "load_y_n": float(truss.forces_n[idx, 1] * load_factor),
            "rx_n": float(result.reactions_n[idx, 0]),
            "ry_n": float(result.reactions_n[idx, 1]),
            "fix_x": sx, "fix_y": sy,
        })
    members = []
    for idx, (a, b) in enumerate(truss.elements):
        force = float(result.force_n[idx])
        critical = float(result.buckling_critical_n[idx])
        members.append({
            "id": idx, "a": int(a), "b": int(b),
            "length_m": float(result.lengths_m[idx]),
            "force_n": force, "stress_mpa": float(result.stress_pa[idx] / 1e6),
            "pcr_n": critical,
            "yield_util": float(abs(result.stress_pa[idx]) * req.yield_safety_factor / req.yield_pa),
            "buckling_util": float(abs(force) * req.buckling_safety_factor / critical if force < 0 else 0),
            "state": "compression" if force < -1e-10 else "tension" if force > 1e-10 else "neutral",
        })
    residual = float(np.linalg.norm(np.sum(result.reactions_n, axis=0) +
                                    np.sum(truss.forces_n, axis=0) * load_factor))
    return {
        "topology": topology, "span_m": req.span_m, "height_m": height, "area_mm2": area,
        "load_n": req.base_load_n * load_factor,
        "nodes": nodes, "members": members,
        "mass_kg": result.mass_kg, "max_displacement_mm": result.max_disp_m * 1000,
        "max_stress_mpa": result.max_stress_pa / 1e6,
        "equilibrium_residual_n": residual,
        "condition_number": result.condition_number,
        "material_E_gpa": req.material_E_pa / 1e9,
        "yield_mpa": req.yield_pa / 1e6,
        "nominal": load_factor == 1.0 and e_factor == 1.0 and area_factor == 1.0,
    }


@lru_cache(maxsize=12)
def cached_grid(req: Requirements) -> pd.DataFrame:
    return grid_search(req)


@lru_cache(maxsize=4)
def cached_surrogate(req: Requirements):
    return train(cached_grid(req))


def handle_api(route: str, data: dict) -> dict:
    if route == "/api/interpret":
        prompt = data.get("prompt", "")
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 1600:
            raise InputError("Enter a design brief (1-1600 characters)")
        use_api = data.get("use_api", False)
        if not isinstance(use_api, bool):
            raise InputError("use_api must be a boolean")
        parsed = interpret(prompt, use_api=use_api)
        return {"interpreted": parsed.model_dump(), "requires_review": True}

    req, topology, height, area = parse_config(data)
    if route == "/api/solve":
        return {
            "analysis": analysis_payload(req, topology, height, area),
            "robust": evaluate(topology, height, area, req),
            "requirements": {
                "max_displacement_mm": req.max_displacement_mm,
                "yield_safety_factor": req.yield_safety_factor,
                "buckling_safety_factor": req.buckling_safety_factor,
                "load_uncertainty": req.load_uncertainty,
            },
        }
    if route == "/api/search":
        designs = cached_grid(req)
        best = best_feasible(designs)
        return {
            "feasible_count": int(designs.feasible.sum()),
            "total_count": len(designs),
            "best": clean(best),
            "candidates": clean(designs),
            "pareto": clean(pareto_front(designs)),
            "sensitivity": clean(elasticities(str(best["topology"]), float(best["height_m"]),
                                             float(best["area_mm2"]), req)) if best else [],
        }
    if route == "/api/challenge":
        multiplier = number(data, "challenge_multiplier", 1.2, 1.0, 1.6)
        expanded = replace(req, load_uncertainty=max(req.load_uncertainty, multiplier - 1.0))
        check = evaluate(topology, height, area, expanded)
        challenged = analysis_payload(
            req, topology, height, area, load_factor=multiplier,
            e_factor=1.0 - req.e_uncertainty,
            area_factor=1.0 - req.area_uncertainty,
        )
        redesign_requested = data.get("redesign", False)
        if not isinstance(redesign_requested, bool):
            raise InputError("redesign must be a boolean")
        response = {
            "challenge_multiplier": multiplier,
            "expanded_load_uncertainty": expanded.load_uncertainty,
            "check": clean(check),
            "challenged_analysis": clean(challenged),
            "redesign": None,
        }
        if redesign_requested:
            designs = cached_grid(expanded)
            best = best_feasible(designs)
            response["redesign"] = {
                "best": clean(best),
                "feasible_count": int(designs.feasible.sum()),
                "total_count": len(designs),
                "mass_change_pct": (float(best["mass_kg"]) / check["mass_kg"] - 1) * 100 if best else None,
            }
        return response
    if route == "/api/ml":
        model, columns, metrics = cached_surrogate(req)
        proposed = data.get("propose", True)
        if not isinstance(proposed, bool):
            raise InputError("propose must be a boolean")
        verified = propose_and_verify(model, columns, req, n=300) if proposed else pd.DataFrame()
        return {
            "metrics": clean(metrics),
            "validation": clean(model.forceforge_validation_),
            "domain": clean(model.forceforge_domain_),
            "verified": clean(verified),
            "note": "Interpolation under current requirements only; every proposed candidate is re-solved using FEA.",
        }
    if route == "/api/sensitivity":
        return {"elasticities": clean(elasticities(topology, height, area, req))}
    raise InputError("Unknown endpoint")


class Handler(BaseHTTPRequestHandler):
    server_version = "ForceForgeWorkspace/1.0.0"

    def _reply(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        encoded = json.dumps(clean(payload), separators=(",", ":"), allow_nan=False).encode("utf-8")
        self._reply(status, encoded, "application/json; charset=utf-8")

    def do_GET(self) -> None:
        route = urlsplit(self.path).path
        if route == "/api/health":
            self._json(200, {"status": "ok", "backend": "forceforge", "topologies": TOPOLOGIES})
            return
        if route == "/api/workspace":
            self._json(200, workspace_manifest())
            return
        if route in ("/", "/index.html", "/workspace", "/workspace/"):
            path = STATIC_DIR / "index.html"
        elif route in ("/style.css", "/app.js", "/spatial-theme.css", "/spatial-shell.js"):
            path = STATIC_DIR / route.lstrip("/")
        else:
            self._json(404, {"error": "Not found"})
            return
        if not path.is_file():
            self._json(404, {"error": "Web files missing"})
            return
        self._reply(200, path.read_bytes(), mimetypes.guess_type(path.name)[0] or "text/plain")

    def do_POST(self) -> None:
        route = urlsplit(self.path).path
        if route not in {"/api/solve", "/api/search", "/api/challenge", "/api/ml",
                         "/api/interpret", "/api/sensitivity"}:
            self._json(404, {"error": "Unknown endpoint"})
            return
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if origin and origin not in {f"http://{host}", f"https://{host}"}:
            self._json(403, {"error": "Cross-origin requests are not allowed"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 1 <= size <= 65536:
                raise InputError("Request must contain up to 64 KB of JSON")
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise InputError("Expected a JSON object")
            payload = handle_api(route, data)
            self._json(200, payload)
        except (InputError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
        except Exception:
            self.log_error("Unhandled error for %s", route)
            self._json(500, {"error": "Solver failed. Check server logs and model inputs."})


# The 2D and 3D applications have different meanings for /api/solve.
# Keep their physics engines unchanged and expose the 3D API under /api/3d/*.
# The embedded 3D page is served from the same origin and given a lightweight
# fetch prefix adapter; the standalone studio_server.py remains fully usable.
STUDIO_API_BOOTSTRAP = r"""<script>
(function () {
  'use strict';
  const studioFetch = window.fetch.bind(window);
  window.fetch = function (resource, options) {
    if (typeof resource === 'string' && resource.startsWith('/api/')) {
      resource = '/api/3d' + resource.substring(4);
    } else if (resource instanceof Request) {
      const url = new URL(resource.url);
      if (url.origin === window.location.origin && url.pathname.startsWith('/api/')) {
        url.pathname = '/api/3d' + url.pathname.substring(4);
        resource = new Request(url, resource);
      }
    }
    return studioFetch(resource, options);
  };
  document.addEventListener('DOMContentLoaded', function () {
    // The integrated shell is v1.0; underlying 3D engineering version is unchanged.
    const subtitle = document.querySelector('.brand-words small');
    if (subtitle) subtitle.textContent = 'WORKSPACE V1.0 / SPATIAL ENGINEERING';
  });
})();
</script>"""


def make_integrated_handler(studio_handler, studio_index: Path | None = None):
    """Compose independent, real 2D/3D solvers without altering their endpoints.

    /                -> 2D Truss Workspace
    /studio/         -> existing WebGL Spatial Studio
    /api/solve       -> 2D truss solver
    /api/3d/solve    -> 3D solid or modal solver
    /api/3d/cad/... -> original isolated STEP/Gmsh solver
    """
    studio_index = studio_index or ROOT / 'studio' / 'index.html'

    class IntegratedHandler(Handler, studio_handler):
        server_version = 'ForceForgeUnifiedSpatial/1.0.0'

        def _json(self, *args, **kwargs):
            if getattr(self, '_studio_dispatch', False):
                return studio_handler._json(self, *args, **kwargs)
            return Handler._json(self, *args, **kwargs)

        def _dispatch_to_studio(self, operation, translated_path=None):
            original_path = self.path
            self._studio_dispatch = True
            try:
                if translated_path is not None:
                    self.path = translated_path
                return operation(self)
            finally:
                self.path = original_path
                self._studio_dispatch = False

        def do_GET(self):
            route = urlsplit(self.path).path
            if route == '/api/workspace':
                return self._json(200, workspace_manifest(studio_available=True))
            if route in ('/studio', '/studio/'):
                if not studio_index.is_file():
                    return self._json(404, {'error': '3D Studio files missing'})
                html = studio_index.read_text(encoding='utf-8')
                if '</head>' not in html:
                    return self._json(500, {'error': '3D Studio HTML invalid'})
                html = html.replace('</head>', STUDIO_API_BOOTSTRAP + '\n</head>', 1)
                return self._reply(200, html.encode('utf-8'), 'text/html; charset=utf-8')
            if route == '/api/3d/catalog':
                return self._dispatch_to_studio(studio_handler.do_GET, '/api/catalog')
            if route.startswith('/studio/') or route.startswith('/download/'):
                return self._dispatch_to_studio(studio_handler.do_GET)
            return Handler.do_GET(self)

        def do_POST(self):
            route = urlsplit(self.path).path
            if route.startswith('/api/3d/'):
                # The 3D handler validates body length, origin, source SHA and input.
                translated = '/api/' + route[len('/api/3d/'):]
                return self._dispatch_to_studio(studio_handler.do_POST, translated)
            return Handler.do_POST(self)

    return IntegratedHandler


def main() -> None:
    parser = argparse.ArgumentParser(description="ForceForge immersive engineering workspace")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    integrated = False
    handler = Handler
    try:
        from studio_server import StudioHandler
    except ImportError as exc:
        print(f"3D Studio unavailable: {exc}. Starting 2D only.", flush=True)
    else:
        handler = make_integrated_handler(StudioHandler)
        integrated = True
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"ForceForge X Engineering Workspace v{WORKSPACE_VERSION}", flush=True)
    print(f"Open http://{args.host}:{args.port}/workspace/", flush=True)
    if integrated:
        print("Integrated 2D and 3D workspaces on the same port; Real CAD requires optional Gmsh.", flush=True)
    print("Press Ctrl+C to stop. Existing Streamlit UI: python -m streamlit run app.py", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
