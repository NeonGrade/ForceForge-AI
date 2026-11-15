"""Record real OpenFOAM reference-case STL motion over solved U/p snapshot."""
from pathlib import Path
import subprocess
from playwright.sync_api import sync_playwright

artifact=Path('qa/real_flow_artifact')
out=Path('qa/devpost_cfd_clip')
out.mkdir(parents=True,exist_ok=True)
files=list(artifact.rglob('offline_actual_rotor_and_solved_U_p.html'))
if len(files)!=1 or files[0].stat().st_size<500000:
    raise RuntimeError('Expected exactly one real OpenFOAM offline HTML artifact')

with sync_playwright() as tool:
    browser=tool.chromium.launch(headless=True,args=[
        '--no-sandbox','--enable-webgl','--use-gl=angle',
        '--use-angle=swiftshader','--enable-unsafe-swiftshader',
    ])
    ctx=browser.new_context(viewport={'width':1280,'height':760},
         record_video_dir=str(out),record_video_size={'width':1280,'height':760})
    page=ctx.new_page()
    errors=[]
    page.on('pageerror',lambda err:errors.append(str(err)))
    page.goto(files[0].resolve().as_uri(),wait_until='load',timeout=60000)
    page.wait_for_function(
        "() => {let g=document.getElementById('ff-real-rotor');return !!(g && g.data && g.data.length===2 && g._fullLayout);}",
        timeout=55000)
    page.get_by_role('button',name='Play continuous rotor').click()
    page.wait_for_function(
        "() => Number(document.getElementById('ff-real-rotor').dataset.ffRotorSteps)>=5",
        timeout=35000)
    page.wait_for_timeout(28000)
    page.screenshot(path=str(out/'actual_reference_openfoam_rotor.png'),full_page=True)
    steps=page.evaluate("Number(document.getElementById('ff-real-rotor').dataset.ffRotorSteps)")
    page.get_by_role('button',name='Pause rotor').click()
    video=page.video
    page.close()
    ctx.close()
    browser.close()
    if errors:
        raise AssertionError('JS errors: '+'; '.join(errors[:4]))
    if steps<48:
        raise AssertionError('Not a full continuous rotor revolution')
    target=out/'ForceForgeX_REAL_OpenFOAM_reference_CFD_clip.mp4'
    subprocess.run(['ffmpeg','-y','-loglevel','error','-i',video.path(),
        '-c:v','libx264','-preset','fast','-crf','24',
        '-pix_fmt','yuv420p','-movflags','+faststart',str(target)],
        check=True,timeout=180)
    (out/'SOURCE_AND_SCOPE.txt').write_text(
       'Real OpenFOAM reference rotor + genuine solved U/p snapshot.\n'
       'Source CI: https://github.com/NeonGrade/ForceForge-AI/actions/runs/43674796795\n'
       'Only original STL geometry rotates. NOT interpolated CFD or custom wall.\n'
       f'Browser steps: {steps}\n',encoding='utf-8')
    print('PASS: genuine reference-case OpenFOAM clip:',target,'steps',steps)
