"""Single-origin 2D+3D integration: routing, solver isolation and page bootstrap."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen
import json

from web_server import make_integrated_handler, WORKSPACE_VERSION


class FakeStudioHandler(BaseHTTPRequestHandler):
    """Stand-in for the real studio_server.StudioHandler in no-Gmsh CI."""

    def _json(self, obj, status=200):
        raw = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == '/api/catalog':
            return self._json({'modules': [{'id': 'solid'}, {'id': 'cad'}, {'id': 'lab'}]})
        if self.path == '/studio/styles.css':
            raw = b'/* real studio stylesheet route */'
            self.send_response(200)
            self.send_header('Content-Type', 'text/css')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        self.send_error(404)

    def do_POST(self):
        size = int(self.headers.get('Content-Length', '0'))
        request = json.loads(self.rfile.read(size))
        if self.path in ('/api/solve', '/api/cad/agent/preview'):
            return self._json({'solver': '3d', 'route': self.path, 'input': request})
        self.send_error(404)


def test_one_port_serves_both_real_api_namespaces(tmp_path):
    index = tmp_path / 'index.html'
    index.write_text('<!doctype html><html><head><title>3D Studio</title></head><body>3D</body></html>')
    handler = make_integrated_handler(FakeStudioHandler, studio_index=index)
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = 'http://127.0.0.1:' + str(server.server_port)
    try:
        with urlopen(base + '/') as response:
            html = response.read().decode()
            assert 'ForceForge AI | Make bold ideas.' in html
            assert 'href="/workspace"' in html
            assert 'id="integratedStudioFrame"' not in html
        with urlopen(base + '/workspace/') as response:
            html = response.read().decode()
            assert 'WORKSPACE v1.0' in html
            assert 'id="open3d"' in html
            assert 'id="integratedStudioFrame"' in html
        with urlopen(base + '/api/workspace') as response:
            info = json.load(response)
            assert info['workspace_version'] == WORKSPACE_VERSION
            assert info['spaces']['3d']['available'] is True
        with urlopen(base + '/api/3d/catalog') as response:
            data = json.load(response)
            assert [m['id'] for m in data['modules']] == ['solid', 'cad', 'lab']
        with urlopen(base + '/studio/') as response:
            html = response.read().decode()
            assert '3D Studio' in html
            assert "resource = '/api/3d' + resource.substring(4)" in html
            assert 'WORKSPACE V1.0 / SPATIAL ENGINEERING' in html
            assert 'new Request(url, resource)' in html
        with urlopen(base + '/studio/styles.css') as response:
            assert b'studio stylesheet' in response.read()

        def post(path, data):
            req = Request(base + path, data=json.dumps(data).encode(),
                          headers={'Content-Type': 'application/json'}, method='POST')
            with urlopen(req) as response:
                return json.load(response)
        planar = post('/api/solve', {'topology': 'Triangle'})
        assert planar['analysis']['topology'] == 'Triangle'
        assert planar['analysis']['max_displacement_mm'] > 0
        solid = post('/api/3d/solve', {'workspace': 'solid'})
        assert solid['solver'] == '3d'
        assert solid['route'] == '/api/solve'
        cad = post('/api/3d/cad/agent/preview', {'current': {}, 'prompt': 'make a bracket'})
        assert cad['route'] == '/api/cad/agent/preview'
        assert cad['solver'] == '3d'
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def test_3d_selector_has_internal_switch_not_external_port():
    root = Path(__file__).resolve().parents[1]
    html = (root / 'web/index.html').read_text()
    js = (root / 'web/spatial-shell.js').read_text()
    css = (root / 'web/spatial-theme.css').read_text()
    assert 'http://127.0.0.1:8765' not in html
    assert 'id="open3d"' in html
    assert "studioFrame.src = '/studio/'" in js
    assert "addTrussChoiceToStudio" in js
    assert 'in-3d-workspace' in css
    assert 'return-2d-studio' in css


def test_actual_3d_studio_uses_namespaced_solver_on_integration_branch(tmp_path):
    """Run a real 3D solid solve when the PR17 Studio modules exist."""
    import pytest
    try:
        from studio_server import StudioHandler
    except ImportError:
        pytest.skip('3D Studio is not part of this local standalone 2D checkout')

    root = Path(__file__).resolve().parents[1]
    assert (root / 'studio/index.html').is_file()
    handler = make_integrated_handler(StudioHandler)
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = 'http://127.0.0.1:' + str(server.server_port)
    try:
        with urlopen(base + '/api/3d/catalog') as response:
            catalog = json.load(response)
            assert catalog['ui_version'] == '0.2.1'
            assert {'solid', 'cad', 'lab'} == {m['id'] for m in catalog['modules']}
        req = Request(base + '/api/3d/solve', method='POST',
                      data=json.dumps({'workspace':'solid', 'resolution':'fast'}).encode(),
                      headers={'Content-Type': 'application/json'})
        with urlopen(req, timeout=30) as response:
            result = json.load(response)
            assert result['workspace'] == 'solid'
            assert result['tip_displacement_mm'] > 0
            assert len(result['mesh']['faces']) > 0
        with urlopen(base + '/studio/', timeout=15) as response:
            html = response.read().decode()
            assert '/studio/viewport3d.js' in html
            assert 'resource = \'/api/3d\' + resource.substring(4)' in html
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def test_workspace_v1_transition_and_history_are_in_same_page():
    root = Path(__file__).resolve().parents[1]
    html = (root / 'web/index.html').read_text()
    js = (root / 'web/spatial-shell.js').read_text()
    css = (root / 'web/spatial-theme.css').read_text()
    assert '<title>ForceForge X | Engineering Workspace v1.0</title>' in html
    for control in ('workspaceTransition', 'retry3D', 'cancel3DLoading',
                    'studioAvailability', 'return2D', 'integratedStudioFrame'):
        assert f'id="{control}"' in html
    assert "dest.pathname = '/workspace/'" in js
    assert "window.addEventListener('popstate'" in js
    assert 'studioFrame.contentDocument?.getElementById' in js
    assert 'appShell.inert = true' in js
    assert 'activeRequest' in js
    assert '.workspace-transition' in css
    assert 'z-index:100' in css
