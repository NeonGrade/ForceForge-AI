"""Real Chromium end-to-end QA for the natural-language fan → STEP → air mesh.

This is a *real browser*, *real isolated OpenCASCADE CAD* and *real
tetrahedral Gmsh air mesh*, not a simulated physics plot. No CFD solver
is run. A failed native worker must not terminate the Streamlit server.
"""
from __future__ import annotations

import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"qa"/"artifacts_nl_fluid"


def available_port():
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1",0))
        return int(sock.getsockname()[1])


def main():
    port=available_port()
    base=f"http://127.0.0.1:{port}"
    server=subprocess.Popen(
        [sys.executable,"-m","streamlit","run","app.py",
         "--server.port",str(port),
         "--server.headless","true",
         "--server.fileWatcherType","none",
         "--browser.gatherUsageStats","false"],
        cwd=str(ROOT),stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(120):
            if server.poll() is not None:
                raise AssertionError("ForceForge Streamlit process exited on startup")
            try:
                with urlopen(base+"/_stcore/health",timeout=1) as response:
                    if response.status==200:
                        break
            except OSError:
                time.sleep(.25)
        else:
            raise AssertionError("Streamlit health endpoint did not start")
        OUTPUT.mkdir(parents=True,exist_ok=True)
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,args=["--no-sandbox"])
            context=browser.new_context(
                viewport={"width":1440,"height":900},
                record_video_dir=str(OUTPUT),
                record_video_size={"width":1440,"height":900},
            )
            page=context.new_page()
            js_errors=[]
            page.on("pageerror",lambda exc:js_errors.append(str(exc)))
            try:
                result=page.goto(
                    base+"/Natural_Language_Engineering",
                    wait_until="domcontentloaded",timeout=30000,
                )
                assert result is not None and result.ok
                form=page.get_by_role("button",name="Interpret engineering requirements")
                expect(form).to_be_visible(timeout=35000)
                form.click()
                consent=page.get_by_role(
                    "checkbox",
                    name=re.compile("I authorize explicitly labeled DEMO geometry"),
                )
                expect(consent).to_be_visible(timeout=20000)
                # Streamlit's checkbox INPUT is covered by a clickable
                # React-Aria LABEL. Click the visible label instead of using
                # Playwright input.check() (pointer is intercepted).
                page.locator("label").filter(
                    has_text="I authorize explicitly labeled DEMO geometry"
                ).click()
                expect(consent).to_be_checked(timeout=10000)
                plan=page.get_by_role(
                    "button",
                    name="Generate STEP and execute READY engineering stages",
                )
                expect(plan).to_be_enabled(timeout=15000)
                plan.click()
                expect(
                    page.get_by_text(re.compile("Real STEP export completed"))
                ).to_be_visible(timeout=110000)
                expect(
                    page.get_by_role(
                        "button",name="Download genuine CAD STEP",
                    )
                ).to_be_visible(timeout=20000)
                fig=page.locator(".js-plotly-plot").first
                expect(fig).to_be_visible(timeout=20000)
                fig.scroll_into_view_if_needed()
                page.wait_for_timeout(4500)
                page.screenshot(
                    path=str(OUTPUT/"01_real_fan_step.png"),full_page=True,
                )

                mesher=page.get_by_role(
                    "button",
                    name="Build real 3D Gmsh fluid mesh + tagged boundary regions",
                )
                expect(mesher).to_be_visible(timeout=15000)
                mesher.click()
                expect(page.get_by_text(
                    "Genuine 3D air mesh generated; blade-resolved CFD requires a separately launched real OpenFOAM job."
                )).to_be_visible(timeout=125000)
                expect(
                    page.get_by_role(
                        "button",
                        name="Download actual tagged 3D Gmsh mesh (.msh)",
                    )
                ).to_be_visible(timeout=20000)
                expect(page.get_by_text("Real fluid tetrahedra")).to_be_visible()
                # Streamlit st.dataframe is canvas-rendered; the physical
                # rotor_interface group is validated by the native MSH test.
                expect(page.get_by_text(re.compile(
                    "Actual source-STEP rotor OpenFOAM CFD is supported"
                ))).to_be_visible()
                mesh_plot=page.locator(".js-plotly-plot").last
                expect(mesh_plot).to_be_visible(timeout=25000)
                mesh_plot.scroll_into_view_if_needed()
                page.wait_for_timeout(4500)
                page.screenshot(
                    path=str(OUTPUT/"02_real_fan_air_tetra_mesh.png"),full_page=True,
                )
                with urlopen(base+"/_stcore/health",timeout=4) as response:
                    assert response.status==200
                assert not page.get_by_text("Connection error").is_visible()
                assert not js_errors, "Uncaught browser errors: "+"; ".join(js_errors)
                print(
                    "PASS: Live Chromium created actual fan STEP, real two-zone "
                    "Gmsh tetra air mesh with named patches; real CFD requires a separate OpenFOAM job."
                )
            finally:
                context.close()
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=8)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=8)


if __name__=="__main__":
    main()
