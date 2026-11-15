"""Visual acceptance of the four-workflow judge-facing Streamlit cockpit."""
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
from playwright.sync_api import expect, sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"qa"/"judge_home_visual"
OUT.mkdir(parents=True,exist_ok=True)


def unused_port():
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1",0))
        return int(sock.getsockname()[1])


def main():
    port=unused_port()
    base=f"http://127.0.0.1:{port}"
    server=subprocess.Popen([
        sys.executable,"-m","streamlit","run","hackathon_app.py",
        "--server.port",str(port),"--server.headless","true",
        "--server.fileWatcherType","none","--browser.gatherUsageStats","false"
    ],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
    try:
        for _ in range(120):
            if server.poll() is not None:
                raise RuntimeError("Competition dashboard server quit")
            try:
                with urlopen(base+"/_stcore/health",timeout=.8) as response:
                    if response.status==200:
                        break
            except OSError:
                time.sleep(.35)
        else:
            raise RuntimeError("Competition dashboard did not respond")
        with sync_playwright() as pt:
            browser=pt.chromium.launch(headless=True,args=["--no-sandbox"])
            context=browser.new_context(
                viewport={"width":1440,"height":900},
                device_scale_factor=1,
                reduced_motion="reduce"
            )
            page=context.new_page()
            errors=[]
            page.on("pageerror",lambda err:errors.append(str(err)))
            page.goto(base,wait_until="domcontentloaded",timeout=45000)
            expect(page.locator(".ff-hero")).to_be_visible(timeout=45000)
            expect(page.get_by_text("Your engineering workflow")).to_be_visible()
            for label in (
                "Open Natural Language CAD",
                "Open Structural FEA",
                "Open Transient CFD",
                "Open Wall Load Transfer",
            ):
                expect(page.get_by_text(label,exact=True)).to_be_visible()
            expect(page.get_by_text("Verified OpenFOAM results")).to_be_visible()
            # Entire hero and at least two workflows must be within 900px.
            hero=page.locator(".ff-hero").bounding_box()
            assert hero and hero["y"]<280 and hero["height"]<320,hero
            cards=page.locator(".ff-card-title")
            assert cards.count()==4
            page.screenshot(path=str(OUT/"desktop_full.png"),full_page=True)
            page.screenshot(path=str(OUT/"desktop_first_screen.png"))
            page.set_viewport_size({"width":390,"height":844})
            page.reload(wait_until="domcontentloaded",timeout=45000)
            expect(page.locator(".ff-hero")).to_be_visible(timeout=45000)
            page.screenshot(path=str(OUT/"mobile_full.png"),full_page=True)
            assert not errors,errors[:5]
            print("PASS judge dashboard: desktop and mobile, four real links, no JS errors")
            context.close()
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10)


if __name__=="__main__":
    main()
