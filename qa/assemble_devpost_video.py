"""Assemble a <=3-minute *real-screen* Devpost fallback MP4.

Actual UI recordings: natural language CAD/Gmsh, real bracket tetra10 FEA,
and a separately validated official OpenFOAM reference rotor/U-p clip.
This does not depict unverified custom wall/guard CFD or wall material FEA.
No fabricated solver visual or AI-generated pseudo-stress is included.
"""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"qa"/"final_devpost_video"
OUT.mkdir(parents=True,exist_ok=True)
FONT=Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
BOLD=Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
if not FONT.exists() or not BOLD.exists():
    raise RuntimeError("Required system subtitle fonts are missing")

def call(*args,timeout=240):
    return subprocess.run(args,check=True,timeout=timeout)

def duration(file:Path)->float:
    result=subprocess.run(
        ["ffprobe","-v","error","-show_entries","format=duration",
         "-of","default=noprint_wrappers=1:nokey=1",str(file)],
        capture_output=True,text=True,check=True,timeout=20
    )
    seconds=float(result.stdout.strip())
    if not .1<seconds<3000:
        raise ValueError(f"Unusable video duration: {file}: {seconds}")
    return seconds

def title_card(title:str,subtitle:str,length:float,target:Path)->None:
    # On-screen captions, no pretend narration, no synthetic CFD imagery.
    filters=(
        "drawtext=fontfile="+str(BOLD)+":text='"+title+
        "':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=h/2-82,"
        "drawtext=fontfile="+str(FONT)+":text='"+subtitle+
        "':fontcolor=0xb8d6e0:fontsize=24:x=(w-text_w)/2:y=h/2+14"
    )
    call("ffmpeg","-y","-loglevel","error","-f","lavfi",
         "-i","color=c=0x101e30:s=1280x720:r=24",
         "-t",str(length),"-vf",filters,
         "-an","-c:v","libx264","-preset","veryfast","-crf","24",
         "-pix_fmt","yuv420p",str(target),timeout=100)

def normalize(src:Path,target:Path,max_len:float,*,from_tail:bool=True)->None:
    length=duration(src)
    length=min(max_len,length)
    start=max(0.,duration(src)-length) if from_tail else 0.
    call("ffmpeg","-y","-loglevel","error",
         "-ss",f"{start:.3f}","-i",str(src),"-t",f"{length:.3f}",
         "-vf","scale=1280:720:force_original_aspect_ratio=decrease,"
               "pad=1280:720:(ow-iw)/2:(oh-ih)/2,"
               "fps=24,format=yuv420p",
         "-an","-c:v","libx264","-preset","veryfast","-crf","24",
         "-pix_fmt","yuv420p",str(target),timeout=240)

def exactly_one(paths,description:str)->Path:
    paths=list(paths)
    if len(paths)!=1:
        raise RuntimeError(f"{description} needs exactly one real source: {paths}")
    return paths[0]

def main():
    fan=exactly_one((ROOT/"qa"/"artifacts_nl_fluid").glob("*.webm"),"real browser CAD")
    fea=exactly_one((ROOT/"qa"/"artifacts").glob("*.webm"),"real browser FEA")
    wall=exactly_one((ROOT/"qa"/"artifacts_wall_mount").glob("*.webm"),"real browser wall statics")
    cfd=exactly_one((ROOT/"qa"/"real_flow_demo").glob("*.mp4"),"genuine OpenFOAM reference")
    if min(fan.stat().st_size,fea.stat().st_size,wall.stat().st_size,cfd.stat().st_size)<50000:
        raise RuntimeError("One authentic raw browser/CFD video is suspiciously small")
    cards=[
        ("ForceForge X","Hack The Nest 2026 | Engineering AI",4.),
        ("01  Natural Language CAD","Real STEP geometry from an English/Chinese request",3.),
        ("02  Structural FEA","Independent tetra10 solver | genuine stress and deformation",3.),
        ("03  Mounting Loads","Real 4-anchor equilibrium | illustrative load inputs",3.),
        ("04  Rotating CFD","Real OpenFOAM reference flow U/p | true STL rotor",3.),
        ("Physics vs Animation","Rigid blade loop | flow snapshot is physically solved",4.),
        ("ForceForge X","4 CAD families | limited fixtures | source-linked evidence",4.),
    ]
    title_paths=[]
    for i,(name,subtitle,seconds) in enumerate(cards):
        target=OUT/f"title_{i}.mp4"
        title_card(name,subtitle,seconds,target)
        title_paths.append(target)
    fan_dst=OUT/"fan_CAD_actual_UI.mp4"
    fea_dst=OUT/"bracket_FEA_actual_UI.mp4"
    wall_dst=OUT/"four_anchor_static_actual_UI.mp4"
    cfd_dst=OUT/"OpenFOAM_reference_actual_U_p.mp4"
    normalize(fan,fan_dst,34.)
    normalize(fea,fea_dst,45.)
    normalize(wall,wall_dst,11.)
    normalize(cfd,cfd_dst,30.,from_tail=False)
    playlist=[
        title_paths[0],title_paths[1],fan_dst,
        title_paths[2],fea_dst,
        title_paths[3],wall_dst,
        title_paths[4],cfd_dst,
        title_paths[5],title_paths[6],
    ]
    manifest=OUT/"concat.txt"
    manifest.write_text(
        "".join("file '"+str(p.resolve())+"'\n" for p in playlist),
        encoding="utf-8",
    )
    video=OUT/"ForceForgeX_Devpost_Real_Engineering_Demo.mp4"
    call("ffmpeg","-y","-loglevel","error","-f","concat","-safe","0",
         "-i",str(manifest),"-c","copy","-movflags","+faststart",str(video),
         timeout=120)
    time=duration(video)
    if not 40<time<180:
        raise RuntimeError(f"Final video out of Devpost max 3m: {time}s")
    evidence={
        "video_seconds":time,
        "sources":{
            "natural_language_CAD":"actual Chromium Gmsh/OpenCASCADE STEP recorded in this run",
            "structural_FEA":"actual Chromium quadratic tetra10 FEA recorded in this run",
            "wall_mount_statics":"actual Chromium 4-anchor analytical reactions with unverified example input",
            "reference_CFD":"GitHub Actions verified reference run 43722359161",
        },
        "limitations":[
            "Wall four-anchor reactions use explicitly labeled demonstration loads",
            "No actual wall material FEA, contact or anchor pullout",
            "CFD clip shows official OpenFOAM reference domain",
            "Flow U/p frozen during smooth kinematic STL rotation",
            "Neither arbitrary text-to-any-CAD nor generic assembly CFD is claimed",
        ],
        "audio":"none (captions; narration can be recorded separately)",
    }
    (OUT/"VIDEO_EVIDENCE.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    print("PASS full true-source engineering demo mp4",video,"seconds",time,flush=True)


if __name__=="__main__":
    main()
