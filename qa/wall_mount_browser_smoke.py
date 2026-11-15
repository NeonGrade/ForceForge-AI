"""Actual Chromium video of the four-anchor free-body equilibrium page.

All loads in this recording use explicitly labeled UNVERIFIED demo numbers.
This does not depict wall deformation/contact FEA or actual measured thrust.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"qa"/"artifacts_wall_mount"


def free_port()->int:
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1",0))
        return int(sock.getsockname()[1])


def main():
    port=free_port()
    base=f"http://127.0.0.1:{port}"
    proc=subprocess.Popen([
        sys.executable,"-m","streamlit","run",
        "pages/16_Wall_Mount_Loads.py","--server.port",str(port),
        "--server.headless","true","--server.fileWatcherType","none",
        "--browser.gatherUsageStats","false"
    ],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
       stderr=subprocess.STDOUT)
    try:
        for _ in range(110):
            if proc.poll() is not None:
                raise RuntimeError("Four-anchor Streamlit page quit during startup")
            try:
                with urlopen(base+"/_stcore/health",timeout=1) as response:
                    if response.status==200:
                        break
            except OSError:
                time.sleep(.3)
        else:
            raise RuntimeError("Four-anchor browser failed health check")
        OUT.mkdir(parents=True,exist_ok=True)
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True,args=["--no-sandbox"])
            context=browser.new_context(
                viewport={"width":1440,"height":900},
                record_video_dir=str(OUT),
                record_video_size={"width":1440,"height":900},
            )
            page=context.new_page()
            errors=[]
            page.on("pageerror",lambda e:errors.append(str(e)))
            try:
                page.goto(base,wait_until="domcontentloaded",timeout=30000)
                title=page.get_by_role(
                    "heading",name="Wall-Mounted Fan · Four-Anchor Load Transfer"
                )
                expect(title).to_be_visible(timeout=35000)
                button=page.get_by_role(
                    "button",name="Calculate actual 4-anchor static reactions"
                )
                expect(button).to_be_visible(timeout=15000)
                button.click()
                expect(page.get_by_text(
                    "6-degree-of-freedom force and moment equilibrium verified"
                )).to_be_visible(timeout=25000)
                expect(page.get_by_text("Maximum anchor tension")).to_be_visible()
                expect(page.get_by_text("Maximum anchor shear")).to_be_visible()
                chart=page.locator(".js-plotly-plot").first
                expect(chart).to_be_visible(timeout=20000)
                chart.scroll_into_view_if_needed()
                page.wait_for_timeout(5800)
                page.screenshot(path=str(OUT/"four_anchor_static_equilibrium.png"),
                                full_page=True)
                assert not errors, "Browser JS errors: "+str(errors[:3])
                with urlopen(base+"/_stcore/health",timeout=4) as response:
                    assert response.status==200
                print("PASS actual Chromium four-anchor free body, signed reaction "
                      "and visible chart with clearly labeled demo inputs",flush=True)
            finally:
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
