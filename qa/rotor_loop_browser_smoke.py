"""Chromium smoke for continuous rotor UX; QA geometry/fields are SYNTHETIC.

This verifies in-browser loop mechanics only. It is NOT physics evidence.
Real CFD acceptance is independently gated by rotating-openfoam.yml.
"""
from pathlib import Path
import math
import numpy as np
from playwright.sync_api import sync_playwright

from forceforge.continuous_rotor import make_loop_html


def create_fixture():
    # Simple triangular source ONLY for browser interaction tests.
    triangles=[]
    for i in range(40):
        angle=2*math.pi*i/40
        r=.3
        triangles.append([
            [r*math.cos(angle),r*math.sin(angle),0.],
            [r*math.cos(angle+.13),r*math.sin(angle+.13),.01],
            [.04*math.cos(angle),.04*math.sin(angle),.02],
        ])
    source={
        "triangles":np.asarray(triangles,dtype=float),
        "origin_m":np.array([0.,0.,0.]),
        "axis":np.array([0.,0.,1.]),
        "sha256":"f"*64,
        "rpm":600.,
    }
    points=np.zeros((3,50,3))
    points[:,:,0]=np.linspace(-.35,.35,50)
    points[:,:,1]=.06
    velocity=np.zeros_like(points)
    velocity[:,:,0]=2.
    pressure=np.full((3,50),.12)
    fields={
        "sample_points":points,"velocity_m_s":velocity,
        "kinematic_pressure_m2_s2":pressure,
        "physical_time_s":np.array([.002,.004,.008]),
    }
    return make_loop_html(source,fields)


def main():
    artifacts=Path("qa/artifacts_rotor_browser")
    artifacts.mkdir(parents=True,exist_ok=True)
    html=(
        "<!doctype html><html><head><meta charset='utf-8'></head>"
        "<body>"+create_fixture()+"</body></html>"
    )
    path=artifacts/"QA_ONLY_synthetic_rotor_loop.html"
    path.write_text(html,encoding="utf-8")
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(
            headless=True,args=[
                "--no-sandbox","--enable-webgl",
                "--use-gl=angle","--use-angle=swiftshader",
                "--enable-unsafe-swiftshader",
            ]
        )
        page=browser.new_page(viewport={"width":1280,"height":900})
        errors=[]
        page.on("pageerror",lambda error:errors.append(str(error)))
        page.goto(path.resolve().as_uri(),wait_until="load",timeout=60000)
        page.wait_for_function(
            "() => { const g=document.getElementById('ff-real-rotor');"
            "return !!(g && g.data && g.data.length===2 && g._fullLayout); }",
            timeout=40000,
        )
        try:
            page.get_by_role("button",name="Play continuous rotor").click()
            page.wait_for_function(
                "() => {const g=document.getElementById('ff-real-rotor');"
                "return Number(g.dataset.ffRotorSteps)>=6 && "
                "Number(g.dataset.ffRotorMaxX)-Number(g.dataset.ffRotorMinX)>.005;}",
                timeout=35000,
            )
            # Must move through more than a complete 48-step revolution
            # instead of merely playing the first few geometry frames.
            page.wait_for_function(
                "() => {const g=document.getElementById('ff-real-rotor');"
                "return Number(g.dataset.ffRotorSteps)>=52 && "
                "Number(g.dataset.ffRotorCycle)>=1;}",
                timeout=55000,
            )
            page.get_by_role("button",name="Pause rotor").click()
            before=page.evaluate(
                "Number(document.getElementById('ff-real-rotor').dataset.ffRotorSteps)"
            )
            page.wait_for_timeout(450)
            after=page.evaluate(
                "Number(document.getElementById('ff-real-rotor').dataset.ffRotorSteps)"
            )
            assert after==before,"Pause must stop geometry updates"
            print("PASS: real Chromium WebGL Mesh3D geometry updated, "
                  "completed >=1 loops, paused; frames=",before)
        finally:
            snapshot=page.evaluate(
                "() => {const g=document.getElementById('ff-real-rotor');"
                "return {steps:g.dataset.ffRotorSteps,"
                "cycle:g.dataset.ffRotorCycle,"
                "minX:g.dataset.ffRotorMinX,maxX:g.dataset.ffRotorMaxX,"
                "label:document.getElementById('ff-rotor-label')?.textContent};}"
            )
            print("CHROMIUM ROTOR DIAGNOSTIC:",snapshot,"JS errors:",errors[:3])
            page.screenshot(path=str(artifacts/"QA_ONLY_chromium_rotor_loop.png"),
                            full_page=True)
        if errors:
            raise AssertionError("Browser JS errors: "+";".join(errors[:3]))
        browser.close()


if __name__=="__main__":
    main()
