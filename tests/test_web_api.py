"""Integration checks for the standalone workspace API and the current physics engine."""
import math
import pytest

from web_server import InputError, handle_api, parse_config


def test_default_solver_returns_physics_and_member_state():
    payload = handle_api('/api/solve', {})
    analysis = payload['analysis']
    assert analysis['topology'] == 'Triangle'
    assert len(analysis['members']) == 3
    assert len(analysis['nodes']) == 3
    assert analysis['nodes'][2]['x_m'] == pytest.approx(1.0)
    assert analysis['nodes'][2]['y_m'] == pytest.approx(1.0)
    assert sum(n['ry_n'] for n in analysis['nodes'] if n['fix_y']) == pytest.approx(1000.0, abs=1e-5)
    assert analysis['equilibrium_residual_n'] < 1e-7
    assert analysis['mass_kg'] > 0
    assert analysis['max_displacement_mm'] > 0
    assert payload['robust']['worst_utilization'] >= 0


def test_reference_truss_matches_benchmark():
    r = handle_api('/api/solve', {'area_mm2': 100})['analysis']
    assert r['members'][0]['force_n'] == pytest.approx(500, abs=1e-7)
    assert r['members'][1]['force_n'] == pytest.approx(-707.106781, abs=1e-5)
    assert r['members'][2]['force_n'] == pytest.approx(-707.106781, abs=1e-5)
    assert r['nodes'][2]['uy_mm'] == pytest.approx(-0.095710678, abs=1e-7)


def test_search_finds_verified_optimum():
    result = handle_api('/api/search', {})
    assert result['total_count'] == 144
    assert result['feasible_count'] == 100
    assert result['best']['topology'] == 'Triangle'
    assert result['best']['height_m'] == pytest.approx(.8)
    assert result['best']['area_mm2'] == pytest.approx(180.)
    assert result['best']['mass_kg'] == pytest.approx(6.445045819, rel=1e-7)
    assert len(result['candidates']) == 144
    assert len(result['sensitivity']) >= 1


def test_challenge_detects_buckling_and_proposes_real_redesign():
    changed = handle_api('/api/challenge', {
        'topology': 'Triangle', 'height_m': .8, 'area_mm2': 180.,
        'challenge_multiplier': 1.6, 'redesign': True,
    })
    assert changed['check']['feasible'] is False
    assert changed['check']['worst_buckling_util'] == pytest.approx(1.132148387, rel=1e-5)
    assert changed['redesign']['best']['topology'] == 'Triangle'
    assert changed['redesign']['best']['area_mm2'] == pytest.approx(230)
    assert changed['redesign']['feasible_count'] == 89
    assert changed['redesign']['mass_change_pct'] == pytest.approx(27.7777778, rel=1e-5)


def test_ml_validation_and_candidate_fea_checks():
    data = handle_api('/api/ml', {'propose': True})
    assert len(data['metrics']) == 3
    assert data['validation']['train_rows'] > data['validation']['test_rows']
    assert 1 <= len(data['verified']) <= 12
    assert all('worst_utilization' in r for r in data['verified'])
    assert all(math.isfinite(r['mass_kg']) for r in data['verified'])


def test_offline_agent_and_reject_ambiguous_values():
    parsed = handle_api('/api/interpret', {'prompt': '2 m span, 1 kN load, 2 mm limit'})
    assert parsed['requires_review'] is True
    assert parsed['interpreted']['load_n'] == pytest.approx(1000)
    with pytest.raises(ValueError, match='Ambiguous'):
        handle_api('/api/interpret', {'prompt': '2 m bridge span, or 3 m bridge span, load 1000 N'})


def test_invalid_range_does_not_call_solver():
    with pytest.raises(InputError, match='span_m'):
        parse_config({'span_m': 15})
    with pytest.raises(InputError):
        parse_config({'material': 'not-real'})
    with pytest.raises(InputError):
        handle_api('/api/challenge', {'challenge_multiplier': 2.2})


def test_spatial_style_parity_assets_and_engineering_boundary():
    """The immersive 2D shell does not replace or fake the existing solver."""
    from pathlib import Path
    from web_server import STATIC_DIR

    html = (STATIC_DIR / 'index.html').read_text()
    js = (STATIC_DIR / 'spatial-shell.js').read_text()
    css = (STATIC_DIR / 'spatial-theme.css').read_text()
    solver_ui = (STATIC_DIR / 'app.js').read_text()

    for path in ('style.css', 'app.js', 'spatial-theme.css', 'spatial-shell.js'):
        assert (STATIC_DIR / path).is_file(), path
    assert 'href="/spatial-theme.css"' in html
    assert 'src="/spatial-shell.js"' in html
    assert 'id="spatialPinLoad"' in html
    assert 'id="spatialPinArea"' in html
    assert 'id="spatialPinResult"' in html
    assert 'id="sceneSelector"' in html
    assert 'LEVEL 02 · SPATIAL ENGINEERING' in html
    assert '--accent:#d7efa2' in css
    assert 'window.ForceForge2D' in solver_ui
    assert 'window.ForceForge2D' in js
    assert "api.updateConfig(" in js
    assert "api.state().config" in js
    assert "'/api/solve'" in solver_ui
    assert "'/api/search'" in solver_ui
    assert 'http://127.0.0.1:8765' in html
