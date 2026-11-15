"""End-to-end browser QA for original workspace + integrated 3D mode.

Run after: pip install playwright && python -m playwright install chromium
           python qa/browser_smoke.py
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import sync_playwright, expect


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "qa" / "artifacts"


def unused_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def main():
    port = unused_port()
    url = f"http://127.0.0.1:{port}"
    child = subprocess.Popen(
        [sys.executable, "web_server.py", "--port", str(port)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(100):
            if child.poll() is not None:
                raise AssertionError("Web server unexpectedly terminated during startup")
            try:
                with urlopen(url + "/api/health", timeout=1) as response:
                    assert json.load(response)["status"] == "ok"
                    break
            except (OSError, TimeoutError):
                time.sleep(.1)
        else:
            raise AssertionError("Web server failed to become healthy")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width":1440,"height":900}, device_scale_factor=1)
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            ARTIFACTS.mkdir(parents=True, exist_ok=True)
            try:
                response = page.goto(url, wait_until="domcontentloaded", timeout=20000)
                assert response is not None and response.ok
                expect(page.locator('button[data-panel="design"]')).to_be_visible()
                expect(page.locator('button[data-panel="solid3d"]')).to_be_visible()
                # Original five features must survive the 3D integration.
                for mode in ("design", "optimize", "challenge", "ml", "agent"):
                    target = page.locator(f'button[data-panel="{mode}"]')
                    target.click()
                    expect(target).to_have_attribute("aria-pressed", "true")
                page.locator('button[data-panel="design"]').click()
                original = page.locator("#input-span")
                original.evaluate(
                    "el => {el.value='2.5'; el.dispatchEvent(new Event('input',{bubbles:true}));}"
                )
                expect(original).to_have_value("2.5")

                button3d = page.locator('button[data-panel="solid3d"]')
                button3d.click()
                expect(button3d).to_have_attribute("aria-pressed", "true")
                expect(page.locator("#solidWorkspaceFrame")).to_be_visible()
                study = page.frame_locator("#solidWorkspaceFrame")
                expect(study.locator("#studyForm")).to_be_visible()
                expect(study.locator(".topbar")).to_be_hidden()
                study.locator("#solveButton").click()
                expect(study.locator("#nodesMetric")).not_to_have_text("—", timeout=70000)
                expect(study.locator("#tetMetric")).not_to_have_text("—")
                expect(study.locator("#stressMetric")).not_to_have_text("—")
                expect(study.locator("#dispMetric")).not_to_have_text("—")
                expect(study.locator("#statusMessage")).to_contain_text("Complete")
                study.locator("#amplification").evaluate(
                    "el => {el.value='180'; el.dispatchEvent(new Event('input',{bubbles:true}));}"
                )
                expect(study.locator("#amplificationValue")).to_have_text("180×")
                page.screenshot(path=str(ARTIFACTS / "integrated-3d.png"), full_page=True)

                # Switching back must preserve the original 2D model and controls.
                page.locator('button[data-panel="design"]').click()
                expect(page.locator("#solidWorkspaceFrame")).to_be_hidden()
                expect(original).to_have_value("2.5")
                expect(page.locator(".inspector")).to_be_visible()
                page.screenshot(path=str(ARTIFACTS / "original-2d-retained.png"), full_page=True)

                # Old standalone bookmarks must return into the full shell.
                page.goto(url + "/solid3d", wait_until="domcontentloaded", timeout=20000)
                page.wait_for_url(url + "/#solid3d", timeout=12000)
                expect(page.locator('button[data-panel="solid3d"]')).to_have_attribute("aria-pressed", "true")
                expect(page.locator("#solidWorkspaceFrame")).to_be_visible()

                # Parent HTTP service must remain alive after the 3D worker.
                with urlopen(url + "/api/health", timeout=4) as response:
                    assert json.load(response)["status"] == "ok"
                assert not errors, "JavaScript errors: " + "; ".join(errors)
                print("PASS: original five tools, embedded 3D solve, UI state and HTTP health")
            finally:
                browser.close()
    finally:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)


if __name__ == "__main__":
    main()
