"""Actual Chromium / Streamlit-WebSocket smoke for the Hack The Nest demo.

This DOES NOT replace Mac Safari acceptance. It verifies the same Real STEP
page through a real browser after native tetra10 worker operations, and
saves actual page screenshots as GitHub Actions artifacts.

Run:
  pip install -r requirements.txt 'gmsh>=4.12,<5' playwright
  python -m playwright install chromium
  python qa/real_step_browser_smoke.py
"""
from __future__ import annotations

import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT / "qa" / "artifacts"


def free_port():
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1",0))
        return int(sock.getsockname()[1])


def main():
    port=free_port()
    base=f"http://127.0.0.1:{port}"
    proc=subprocess.Popen(
        [sys.executable,"-m","streamlit","run",
         "pages/13_Real_STEP_Engineering.py",
         "--server.port",str(port),
         "--server.headless","true",
         "--server.fileWatcherType","none",
         "--browser.gatherUsageStats","false"],
        cwd=str(ROOT),stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(120):
            if proc.poll() is not None:
                raise AssertionError("Streamlit server died while starting")
            try:
                with urlopen(base+"/_stcore/health",timeout=1) as res:
                    if res.status==200:
                        break
            except OSError:
                time.sleep(.25)
        else:
            raise AssertionError("Streamlit health endpoint never became ready")
        OUTPUT.mkdir(parents=True,exist_ok=True)
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True,args=["--no-sandbox"])
            context=browser.new_context(
                viewport={"width":1440,"height":900},
                record_video_dir=str(OUTPUT),
                record_video_size={"width":1440,"height":900},
            )
            page=context.new_page()
            page_errors=[]
            page.on("pageerror",lambda exc:page_errors.append(str(exc)))
            try:
                res=page.goto(base,wait_until="domcontentloaded",timeout=20000)
                assert res is not None and res.ok
                expect(page.get_by_role("button",name="Run CAD import + 3D FEA")).to_be_visible(timeout=30000)
                page.get_by_role("button",name="Run CAD import + 3D FEA").click()
                expect(page.get_by_text(re.compile("FEA complete in"))).to_be_visible(timeout=110000)
                expect(page.get_by_text("Step 2B · Design Copilot",exact=False)).to_be_visible(timeout=15000)
                plot=page.locator(".js-plotly-plot").first
                expect(plot).to_be_visible(timeout=20000)
                plot.scroll_into_view_if_needed()
                page.wait_for_timeout(4000)
                page.screenshot(path=str(OUTPUT/"01_real_step_original.png"),full_page=True)

                page.get_by_role(
                    "button",name="Generate CAD proposals + verify every candidate with real 3D FEA"
                ).click()
                expect(page.get_by_text("RULE_BASED_FULL_SEARCH",exact=False)).to_be_visible(timeout=250000)
                expect(page.get_by_text("PHYSICS-VERIFIED DISCRETE SCREEN",exact=False)).to_be_visible(timeout=250000)
                expect(page.get_by_role(
                    "button",name=re.compile("Export auditable AI-to-CAD-to-FEA evidence")
                )).to_be_visible(timeout=15000)
                charts=page.locator(".js-plotly-plot")
                expect(charts.last).to_be_visible(timeout=20000)
                charts.last.scroll_into_view_if_needed()
                page.wait_for_timeout(4200)
                page.screenshot(path=str(OUTPUT/"02_real_cad_optimization.png"),full_page=True)

                # Re-renders/deformation changes cannot kill Streamlit's
                # parent server or silently convert real FEA to a fake cache.
                with urlopen(base+"/_stcore/health",timeout=4) as res:
                    assert res.status==200
                assert not page.get_by_text("Connection error",exact=False).is_visible()
                assert not page_errors, "Browser JS errors: "+"; ".join(page_errors)
                print("PASS: real browser solved original and 3 rewritten STEP solids; FEA screens rendered")
            finally:
                # Closing the context finalizes the unedited, no-audio
                # Chromium session recording for actual demo fallback.
                context.close()
                browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=8)


if __name__=="__main__":
    main()
