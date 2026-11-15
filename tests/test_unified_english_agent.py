"""Current-case English assistance through the real single-origin host."""
import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

import web_server as web
from forceforge.engineering_agent import is_parameter_request
from forceforge.provenance import context_id, truss_context


@pytest.mark.parametrize("prompt,changes", [
    ("Increase the load by 20%", {"base_load_n":1200}),
    ("Could you halve the load?", {"base_load_n":500}),
    ("Please apply a 1.2 kN load", {"base_load_n":1200}),
    ("Set span to 3 m and height to 1.1 m", {"span_m":3, "height_m":1.1}),
    ("Use a 300 cm bridge with displacement limit 1.5 mm", {"span_m":3, "max_displacement_mm":1.5}),
    ("Set the section area to 230 mm²", {"area_mm2":230}),
    ("Reduce deflection limit by 25 percent", {"max_displacement_mm":1.5}),
])
def test_partial_english_changes_preserve_current_case(prompt, changes, monkeypatch):
    monkeypatch.setattr(web, "analysis_payload", lambda *a, **k: pytest.fail("Preview must not solve"))
    current = web.canonical_config({"height_m":1.2, "area_mm2":230, "material":"aluminum"})
    preview = web.handle_api('/api/agent/ask', {"current":current, "prompt":prompt})
    assert preview['kind'] == 'proposal'
    assert preview['proposal']['changes'] == changes
    confirmed = web.handle_api('/api/agent/confirm', {"current":current, "proposal":preview['proposal']})
    assert confirmed['parameters'] == {**current, **changes}


@pytest.mark.parametrize("prompt", [
    "load 1 kN or load 2 kN", "load -100 N", "load 1e999 N", "load 5 kg",
    "Increase load by -20%", "Reduce load by 200%", "load 5000 N", "height 4 m",
    "apply a distributed load 1000 N/m", "load 1200 N and material aluminum",
    "span 3 m and height 1 m and deflection limit 20 mm",
])
def test_unsupported_or_ambiguous_changes_fail_atomically(prompt):
    current = web.canonical_config({})
    with pytest.raises(ValueError):
        web.handle_api('/api/agent/ask', {"current":current, "prompt":prompt})
    assert current == web.canonical_config({})


def test_confirmation_rejects_stale_or_unrecognized_changes():
    current = web.canonical_config({})
    preview = web.handle_api('/api/agent/ask', {"current":current, "prompt":"load 1200 N"})
    with pytest.raises(ValueError, match="changed"):
        web.handle_api('/api/agent/confirm', {"current":{**current,"area_mm2":230}, "proposal":preview['proposal']})
    preview['proposal']['changes']['material_E_pa'] = 1
    with pytest.raises(ValueError, match="Unsupported"):
        web.handle_api('/api/agent/confirm', {"current":current, "proposal":preview['proposal']})


@pytest.mark.parametrize("question,topic", [
    ("Why does this design fail?", "diagnosis"),
    ("What is the displacement at 3000 N?", "results"),
    ("How can I make this 2 m truss lighter?", "next_steps"),
    ("What do the uncertainty scenarios mean?", "scenarios"),
    ("Can this 2D model predict plasticity?", "validation_scope"),
    ("How accurate is the ML surrogate?", "ml_scope"),
    ("What does my drawing show?", "clarification"),
])
def test_answers_use_completed_evidence_without_any_new_solve(question, topic, monkeypatch):
    current = web.canonical_config({"base_load_n":3000})
    result = web.handle_api('/api/solve', current)
    assert not is_parameter_request(question)
    monkeypatch.setattr(web, "analysis_payload", lambda *a, **k: pytest.fail("Questions must not solve"))
    monkeypatch.setattr(web, "evaluate", lambda *a, **k: pytest.fail("Questions must not recompute scenarios"))
    data = web.handle_api('/api/agent/ask', {"current":current,"prompt":question,"review_id":result['review_id'],
                                           "analysis":{"max_displacement_mm":99999}})
    assert data['kind'] == 'answer'
    assert data['answer']['language'] == 'en'
    assert data['answer']['topic'] == topic
    assert "99999" not in data['answer']['text']
    if topic == 'diagnosis':
        assert 'fails' in data['answer']['text']
        assert f"{result['robust']['worst_buckling_util']:.3f}" in data['answer']['text']
    if topic == 'results':
        assert f"{result['analysis']['max_displacement_mm']:.5f}" in data['answer']['text']


def test_questions_reject_forged_changed_and_evicted_evidence():
    web._REVIEWS.clear()
    current = web.canonical_config({})
    solved = web.handle_api('/api/solve', current)
    for inputs, review_id in ((current,'invented'), ({**current,'area_mm2':230},solved['review_id'])):
        with pytest.raises(ValueError, match="missing or stale"):
            web.handle_api('/api/agent/ask', {"current":inputs,"prompt":"What is the mass?","review_id":review_id})
    for load in range(1001,1034):
        web.handle_api('/api/solve', {"base_load_n":load})
    assert len(web._REVIEWS) == 32
    with pytest.raises(ValueError, match="missing or stale"):
        web.handle_api('/api/agent/ask', {"current":current,"prompt":"What is the mass?","review_id":solved['review_id']})


def test_height_holdout_export_is_context_bound_and_reverified():
    data = web.handle_api('/api/ml', {"validation_strategy":"height"})
    assert data['requirements_id'] == context_id(truss_context(web.parse_config({})[0]))
    assert data['validation']['strategy'] == 'height'
    assert set(data['validation']['train_heights_m']).isdisjoint(data['validation']['test_heights_m'])
    assert len(data['verified']) == 12
    assert all(r['fea_verified'] and r['requirements_id'] == data['requirements_id'] for r in data['verified'])
    assert all(abs(r['prediction_abs_error'] - abs(r['predicted_worst_util']-r['worst_utilization'])) < 1e-10 for r in data['verified'])
    changed = web.handle_api('/api/ml', {"base_load_n":1200,"propose":False,"validation_strategy":"height"})
    assert changed['requirements_id'] != data['requirements_id']
    with pytest.raises(ValueError, match="strategy"):
        web.handle_api('/api/ml', {"validation_strategy":"arbitrary"})


def test_real_unified_http_keeps_2d_and_3d_agents_separate():
    from studio_server import StudioHandler
    server = ThreadingHTTPServer(('127.0.0.1',0), web.make_integrated_handler(StudioHandler))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def post(path, data):
        request = Request(f'http://127.0.0.1:{server.server_port}'+path, json.dumps(data).encode(),
                          {'Content-Type':'application/json'})
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    try:
        current = web.canonical_config({})
        solved = post('/api/solve', current)
        answer = post('/api/agent/ask', {'current':current,'prompt':'What is the displacement?', 'review_id':solved['review_id']})
        assert answer['answer']['topic'] == 'results'
        assert post('/api/agent/ask', {'current':current,'prompt':'load 1.2 kN'})['proposal']['changes'] == {'base_load_n':1200}
        cad = post('/api/3d/cad/agent/ask', {'current':{'source':'generated','force_n':250},'prompt':'Increase load by 20%'})
        assert cad['proposal']['changes'] == {'force_n':300}
        with pytest.raises(HTTPError) as exc:
            post('/api/3d/cad/agent/ask', {'current':{'source':'generated','force_n':250},
                                         'prompt':'What is the displacement?', 'review_id':solved['review_id']})
        assert exc.value.code == 400
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
