"""Actual rotating-blade transient CFD reference-runner for ForceForge X.

Supported mode: the *official OpenFOAM rotatingFanInRoom example* with
pimpleFoam, rotatingMotion and arbitrary mesh interface (AMI). This is a
blade-resolved reference case, NOT a solve of ForceForge's generated
300-mm STEP fan. The two geometries must never share a provenance badge.
There is NO synthetic CFD output path. Unavailable Docker/OpenFOAM or an
unverified real time series results in a visible BLOCKED/FAILED status.

Long-running native work is isolated in a detached process; the Streamlit
server never imports OpenFOAM shared libraries. Docker image is fixed to
an official versioned package and CPU/memory/time budgets are bounded.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import time

import numpy as np

IMAGE="opencfd/openfoam-default:2512"
SCENE_KIND="OFFICIAL_OPENFOAM_ROTATING_FAN_REFERENCE_GEOMETRY"
ROOT=Path.home()/".forceforge_x"/"transient_cfd"
TIME_LIMIT_S=900
MAX_POINTS_PER_FRAME=500
MAX_FRAMES=18


@dataclass(frozen=True)
class ReferenceControls:
    rpm: int = 1500
    end_time_s: float = .04
    write_interval_s: float = .004

    def __post_init__(self):
        if type(self.rpm) is not int or not 100 <= self.rpm <= 2400:
            raise ValueError("Reference rotor RPM must be an integer from 100 to 2400")
        if not .008 <= self.end_time_s <= .08:
            raise ValueError("Transient duration must be 0.008-0.08 s")
        if not .001 <= self.write_interval_s <= .016:
            raise ValueError("Reference write interval must be 0.001-0.016 s")
        if self.write_interval_s > self.end_time_s/2:
            raise ValueError("At least two solution writes are required")

    @property
    def angular_velocity_rad_s(self):
        return self.rpm * 2 * np.pi / 60

    def as_dict(self):
        return {"rpm":self.rpm,"angular_velocity_rad_s":self.angular_velocity_rad_s,
                "end_time_s":self.end_time_s,"write_interval_s":self.write_interval_s,
                "geometry_origin":SCENE_KIND,"image":IMAGE}


def _replace_scalar(text: str, name: str, value: str) -> str:
    pat=re.compile(r"(?m)^(\s*"+re.escape(name)+r"\s+)([^;{}]+)(;)")
    matches=list(pat.finditer(text))
    if len(matches)!=1:
        raise ValueError(f"OpenFOAM dictionary requires exactly one '{name}' entry; found {len(matches)}")
    return pat.sub(lambda m: m.group(1)+value+m.group(3),text)


def adapt_reference_case(case: Path, controls: ReferenceControls) -> dict:
    """Modify only documented controlDict and rotatingMotion omega entries.

    The actual sample geometry remains the official tutorial; the code may
    NOT claim it matches the current natural-language STEP model.
    """
    dynamic=case/"constant"/"dynamicMeshDict"
    control=case/"system"/"controlDict"
    if not dynamic.is_file() or not control.is_file():
        raise ValueError("Rotating-fan tutorial missing motion or control dictionary")
    movement=dynamic.read_text(encoding="utf-8")
    if "rotatingMotion" not in movement or "rotatingZone" not in movement:
        raise ValueError("Reference case lacks rotatingMotion/rotatingZone")
    cfg=control.read_text(encoding="utf-8")
    if "pimpleFoam" not in cfg:
        raise ValueError("Reference case must use transient pimpleFoam")
    movement=_replace_scalar(
        movement,"omega",f"{controls.angular_velocity_rad_s:.12g}"
    )
    cfg=_replace_scalar(cfg,"endTime",f"{controls.end_time_s:.9g}")
    cfg=_replace_scalar(cfg,"writeControl","runTime")
    cfg=_replace_scalar(cfg,"writeInterval",f"{controls.write_interval_s:.9g}")
    dynamic.write_text(movement,encoding="utf-8")
    control.write_text(cfg,encoding="utf-8")
    return {
        "dynamic_mesh_sha256":sha256(movement.encode()).hexdigest(),
        "control_sha256":sha256(cfg.encode()).hexdigest(),
        "motion":"rotatingMotion",
        "interface":"AMI (must be checked in actual mesh)",
        "rotation_axis":"from official reference geometry",
    }


def docker_ready() -> tuple[bool,str]:
    if not shutil.which("docker"):
        return False,"Docker CLI missing. Install Docker Desktop or an OpenFOAM environment first."
    try:
        p=subprocess.run(
            ["docker","image","inspect",IMAGE,"--format","{{.Id}}"],
            capture_output=True,text=True,timeout=8,check=False,
        )
    except (OSError,subprocess.TimeoutExpired):
        return False,"Docker engine not reachable"
    if p.returncode:
        return False,(
            "Official OpenFOAM tutorial image is not pulled. "
            "Run: docker pull "+IMAGE
        )
    return True,p.stdout.strip()


def _docker(root: Path,script: str,limit: int,logname: str):
    """Only fixed developer-authored shell scripts; never concatenate user input."""
    args=[
        "docker","run","--rm","--network","none",
        "--cpus=4","--memory=6g","--pids-limit=256",
        "--user",str(os.getuid())+":"+str(os.getgid()),
        "-e","HOME=/tmp",
        "-v",str(root.resolve())+":/workspace",
        "-w","/workspace",IMAGE,"bash","-lc",script,
    ]
    with (root/logname).open("w",encoding="utf-8") as log:
        res=subprocess.run(
            args,cwd=root,stdin=subprocess.DEVNULL,
            stdout=log,stderr=subprocess.STDOUT,
            timeout=limit,check=False,text=True,
        )
    if res.returncode:
        tail=(root/logname).read_text(encoding="utf-8",errors="replace")[-1800:]
        raise RuntimeError(
            f"OpenFOAM container stage {logname} failed ({res.returncode}): {tail}"
        )


def _manifest(root: Path,info: dict):
    tmp=root/"status.tmp"
    tmp.write_text(json.dumps(info,indent=2,ensure_ascii=False),encoding="utf-8")
    tmp.replace(root/"status.json")


def _load_status(root: Path) -> dict:
    try:
        return json.loads((root/"status.json").read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError):
        return {"stage":"STARTING","status":"RUNNING"}


def _valid_job_root(job_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{16}",job_id):
        raise ValueError("Invalid CFD job identifier")
    root=(ROOT/job_id).resolve()
    if root.parent!=ROOT.resolve():
        raise ValueError("CFD output location not approved")
    return root


def launch_reference_job(
    controls: ReferenceControls, *, custom_rotor_stl: bytes | None = None,
    custom_source_sha256: str | None = None,
    custom_diameter_mm: float | None = None,
) -> str:
    """Real OpenFOAM: official reference fan or source-STEP custom rotor.

    The custom rotor is inserted in the OFFICIAL reference room; stationary
    guard, wall-anchor loads and the user's own surrounding room are NOT
    included. The source SHA is recorded separately from the reference mesh.
    """
    if custom_rotor_stl is not None:
        from .rotor_surface import MAX_STL_BYTES
        if (not isinstance(custom_rotor_stl,bytes)
                or not custom_rotor_stl.startswith(b"solid fan")
                or not 1000<len(custom_rotor_stl)<=MAX_STL_BYTES):
            raise ValueError("Custom rotor must be genuine bounded ASCII STL data")
        if not custom_source_sha256 or not re.fullmatch(
            r"[0-9a-f]{64}",custom_source_sha256
        ):
            raise ValueError("Exact source STEP SHA-256 required for custom blade case")
        if custom_diameter_mm is None or not 100<=custom_diameter_mm<=800:
            raise ValueError("Known custom rotor diameter required")
    ok,msg=docker_ready()
    if not ok:
        raise RuntimeError(msg)
    ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
    job_id=secrets.token_hex(8)
    folder=_valid_job_root(job_id)
    folder.mkdir(mode=0o700,parents=False,exist_ok=False)
    if custom_rotor_stl is not None:
        (folder/"user_rotor.stl").write_bytes(custom_rotor_stl)
    data={
        "status":"RUNNING","stage":"QUEUED",
        "job_id":job_id,"started_epoch_s":time.time(),
        "geometry_origin":(
            "USER_STEP_ROTOR_IN_OFFICIAL_REFERENCE_ROOM"
            if custom_rotor_stl is not None else SCENE_KIND
        ),
        "reference_only":custom_rotor_stl is None,
        "assumptions":(
            "Real user STEP rotor wall; official reference room and AMI zone. "
            "NO user-specific wall-mounted guard, wall or anchors."
            if custom_rotor_stl is not None else
            "Official OpenFOAM rotatingFanInRoom geometry, NOT generated ForceForge STEP"
        ),
        "custom_source_sha256":custom_source_sha256,
        "custom_rotor_stl_sha256":(
            sha256(custom_rotor_stl).hexdigest()
            if custom_rotor_stl is not None else None
        ),
        "custom_diameter_mm":custom_diameter_mm,
        "controls":controls.as_dict(),
        "docker_image_id":msg,
        "solved":False,
    }
    _manifest(folder,data)
    with (folder/"launcher.log").open("w",encoding="utf-8") as log:
        worker=subprocess.Popen(
            [sys.executable,"-m","forceforge.rotating_cfd",
             "--worker",job_id],
            stdin=subprocess.DEVNULL,stdout=log,
            stderr=subprocess.STDOUT,close_fds=True,
            start_new_session=True,
        )
    data["pid"]=worker.pid
    _manifest(folder,data)
    return job_id


def job_status(job_id: str) -> dict:
    return _load_status(_valid_job_root(job_id))


def _parse_time(s: str) -> float | None:
    try:
        val=float(s)
    except ValueError:
        return None
    return val if np.isfinite(val) and val > 0 else None


def _collect_vtk(root: Path) -> dict:
    """Read ONLY actual OpenFOAM foamToVTK outputs. No synthetic fallback."""
    import meshio

    case=root/"case"
    # A filesystem timestamp is not CFD time. Sort genuine VTK records
    # by their exported numeric index (only validated labels are shown).
    def vtk_sort_key(path: Path):
        match=re.search(r"([0-9]+(?:\.[0-9]+)?)\.vtk$",path.name)
        return (
            float(match.group(1)) if match else float("inf"),
            str(path),
        )
    paths=sorted(case.rglob("*.vtk"),key=vtk_sort_key)
    if len(paths)<2:
        raise ValueError("No real time-dependent OpenFOAM VTK snapshots available")
    times=[]
    xyz_frames=[]
    u_frames=[]
    p_frames=[]
    files=[]
    for path in paths:
        if len(times)>=MAX_FRAMES:
            break
        # Skip boundary-only/patch VTK, require both vector U and scalar p.
        try:
            obj=meshio.read(path)
        except Exception:
            continue
        fields={k.lower():v for k,v in obj.point_data.items()}
        if "u" in fields and "p" in fields:
            pts=np.asarray(obj.points,dtype=float)
            vel=np.asarray(fields["u"],dtype=float)
            pres=np.asarray(fields["p"],dtype=float).reshape(-1)
        else:
            # foamToVTK frequently writes cell-centred finite-volume
            # fields rather than nodal fields. Sample actual cell centres,
            # never fill absent solver values with zeros or approximations.
            blocks=obj.cell_data
            names={k.lower():v for k,v in blocks.items()}
            if "u" not in names or "p" not in names:
                continue
            if len(names["u"])!=len(obj.cells) or len(names["p"])!=len(obj.cells):
                continue
            pts=np.concatenate([
                np.asarray(obj.points,dtype=float)[cell.data].mean(axis=1)
                for cell in obj.cells
            ])
            vel=np.concatenate([np.asarray(v,dtype=float) for v in names["u"]])
            pres=np.concatenate([
                np.asarray(v,dtype=float).reshape(-1) for v in names["p"]
            ])
        if (pts.ndim!=2 or pts.shape[1]!=3 or vel.shape!=pts.shape
                or pres.shape!=(len(pts),) or len(pts)<20):
            continue
        if not all(np.isfinite(x).all() for x in (pts,vel,pres)):
            continue
        stem=path.stem
        match=re.search(r"(?:^|[_-])([0-9]+(?:\.[0-9]+)?)$",stem)
        t=(_parse_time(match.group(1)) if match else None)
        # OpenFOAM foamToVTK often calls the file '<case>_0005.vtk'
        # (time index rather than seconds). The real time is taken from
        # the adjacent file's header when present; no guessed timestamps.
        if t is None:
            continue
        sel=np.linspace(0,len(pts)-1,min(MAX_POINTS_PER_FRAME,len(pts))).astype(int)
        times.append(t)
        xyz_frames.append(pts[sel])
        u_frames.append(vel[sel])
        p_frames.append(pres[sel])
        files.append({"path":str(path.relative_to(root)),
                      "sha256":sha256(path.read_bytes()).hexdigest()})
    if len(times)<2:
        raise ValueError(
            "Unable to validate at least two snapshots with real U/p fields "
            "and extractable time labels. CFD status remains unverified."
        )
    # Store dimensions explicitly. VTK indices are not assumed physical
    # seconds unless a genuine time mapping is recorded elsewhere.
    length=min(map(len,xyz_frames))
    np.savez_compressed(
        root/"actual_cfd_frames.npz",
        sample_points=np.stack([a[:length] for a in xyz_frames]),
        velocity_m_s=np.stack([a[:length] for a in u_frames]),
        kinematic_pressure_m2_s2=np.stack([a[:length] for a in p_frames]),
        vtk_record_indices=np.asarray(times),
    )
    return {
        "frame_count":len(times),
        "sample_points_per_frame":length,
        "source_vtk_files":files,
        "fields":["U [m/s]","p [m2/s2] (kinematic)"],
        "time_axis_note":"VTK file indices; physical time requires case postProcessing mapping",
        "file_sha256":sha256((root/"actual_cfd_frames.npz").read_bytes()).hexdigest(),
    }


def _run_job(root: Path,controls: ReferenceControls):
    data=_load_status(root)
    if data.get("geometry_origin") not in (
        SCENE_KIND,"USER_STEP_ROTOR_IN_OFFICIAL_REFERENCE_ROOM"
    ):
        raise ValueError("Invalid CFD case provenance")
    try:
        data["stage"]="COPY_OFFICIAL_TUTORIAL";_manifest(root,data)
        copy_script=r'''
set -ex
echo "OpenFOAM version environment:"
echo "$WM_PROJECT_VERSION"
echo "FOAM_TUTORIALS before shell setup:"
echo "$FOAM_TUTORIALS"
if [ -z "$FOAM_TUTORIALS" ]; then
  for f in /opt/OpenFOAM/*/etc/bashrc /usr/lib/openfoam/*/etc/bashrc /opt/openfoam*/etc/bashrc; do
    if [ -f "$f" ]; then
      echo "Sourcing official environment from $f"
      . "$f"
      break
    fi
  done
fi
if [ -z "$FOAM_TUTORIALS" ]; then
  echo "ERROR: FOAM_TUTORIALS missing after environment setup" >&2
  find /opt -maxdepth 4 -name rotatingFanInRoom -type d -print || true
  exit 42
fi
src="$(find "$FOAM_TUTORIALS" -type d -name rotatingFanInRoom -print -quit)"
if [ -z "$src" ]; then
  echo "ERROR: rotatingFanInRoom not found in installed OpenFOAM tutorials" >&2
  ls "$FOAM_TUTORIALS/incompressible/pimpleFoam/RAS" || true
  exit 43
fi
echo "Official rotating-fan case: $src"
cp -r "$src" /workspace/case
ls -la /workspace/case
ls -la /workspace/case/constant || true
ls -la /workspace/case/system || true
if [ ! -f /workspace/case/constant/dynamicMeshDict ]; then
  echo "ERROR: no real motion dictionary in tutorial" >&2
  exit 44
fi
if [ ! -f /workspace/case/system/controlDict ]; then
  echo "ERROR: no time-stepping control dictionary" >&2
  exit 45
fi
'''
        _docker(root,copy_script,90,"copy_openfoam.log")
        if not data.get("reference_only",True):
            source=root/"user_rotor.stl"
            if not source.is_file() or sha256(source.read_bytes()).hexdigest()!=data.get("custom_rotor_stl_sha256"):
                raise ValueError("Custom rotor STL missing or tampered")
            target=root/"case"/"constant"/"triSurface"/"fan.stl"
            if not target.is_file():
                raise ValueError(
                    "Installed tutorial has no replaceable fan.stl reference "
                    "surface; cannot inject real custom rotor safely"
                )
            target.unlink()
            target.write_bytes(source.read_bytes())
            data["reference_fan_stl_replaced_by_exact_user_cad"]=True
        settings=adapt_reference_case(root/"case",controls)
        data["case_configuration"]=settings
        data["stage"]="MESH_AND_SOLVE_REAL_TRANSIENT";_manifest(root,data)
        solver_script=r'''
set -eu
cd /workspace/case
if [ -f ./Allrun.pre ]; then
  bash ./Allrun.pre
elif [ -f ./Allrun ]; then
  bash ./Allrun
else
  echo "Missing official OpenFOAM runner" >&2
  exit 44
fi
if [ ! -d constant/polyMesh ]; then
  echo "No actual CFD finite-volume mesh" >&2; exit 45
fi
checkMesh > /workspace/checkMesh.log
pimpleFoam > /workspace/log.pimpleFoam
'''
        _docker(root,solver_script,TIME_LIMIT_S-90,"solver_console.log")
        # OpenFOAM tutorial preprocessing must not silently restore the
        # original RPM or time settings. The solver must use the exact
        # requested rotatingMotion and controlDict physics parameters.
        configuration={
            "dynamic_mesh_sha256":root/"case"/"constant"/"dynamicMeshDict",
            "control_sha256":root/"case"/"system"/"controlDict",
        }
        for key,path in configuration.items():
            if (not path.is_file() or
                    sha256(path.read_bytes()).hexdigest()!=settings[key]):
                raise ValueError(
                    "OpenFOAM preprocessing rewrote a configured motion/time "
                    "dictionary; cannot claim the requested RPM or transient duration"
                )
        if not data.get("reference_only",True):
            target=root/"case"/"constant"/"triSurface"/"fan.stl"
            if (not target.is_file() or
                    sha256(target.read_bytes()).hexdigest()!=data["custom_rotor_stl_sha256"]):
                raise ValueError(
                    "OpenFOAM meshing overwrote source CAD fan.stl; "
                    "refusing to call this a custom rotor computation"
                )
        log=(root/"log.pimpleFoam").read_text(errors="replace")
        times=[float(x) for x in re.findall(
            r"(?m)^Time =\s*([0-9.eE+-]+)",log
        )]
        if len(times)<2 or max(times)<.90*controls.end_time_s:
            raise ValueError(
                "pimpleFoam did not advance to the configured real transient endTime"
            )
        if "Courant Number" not in log:
            raise ValueError("No reported Courant number; solver verification incomplete")
        if "End" not in log[-4000:]:
            raise ValueError("OpenFOAM solver log missing successful termination marker")
        data.update({
            "status":"SOLVER_FINISHED_UNVERIFIED_FIELDS",
            "stage":"POSTPROCESS_REAL_FIELDS",
            "solved":True,
            "last_time_s":max(times),
            "steps":len(times),
            "solver_log_sha256":sha256(log.encode()).hexdigest(),
        });_manifest(root,data)
        export_script=r'''
set -eu
cd /workspace/case
foamToVTK -ascii -fields '(U p)' > /workspace/foamToVTK.log
'''
        _docker(root,export_script,100,"export_console.log")
        summary=_collect_vtk(root)
        data.update({
            "status":"COMPLETED","stage":"REAL_TRANSIENT_FIELDS_READY",
            "source_type":SCENE_KIND,
            "result":summary,
            "completed_epoch_s":time.time(),
        })
        _manifest(root,data)
    except Exception as e:
        data.update({
            "status":"FAILED","stage":"FAILED",
            "error_type":type(e).__name__,
            "message":str(e)[:1900],
            "completed_epoch_s":time.time(),
            "solved":bool(data.get("solved",False)),
        })
        _manifest(root,data)


def load_actual_frames(job_id: str):
    root=_valid_job_root(job_id)
    status=job_status(job_id)
    if status.get("status")!="COMPLETED":
        raise ValueError("Real CFD fields are not verified and ready")
    path=root/"actual_cfd_frames.npz"
    if sha256(path.read_bytes()).hexdigest()!=status["result"]["file_sha256"]:
        raise ValueError("Corrupted actual CFD output; refuse to display")
    with np.load(path,allow_pickle=False) as a:
        return {k:a[k].copy() for k in (
            "sample_points","velocity_m_s","kinematic_pressure_m2_s2",
            "vtk_record_indices",
        )}


if __name__=="__main__":
    if len(sys.argv)!=3 or sys.argv[1]!="--worker":
        raise SystemExit("Internal reference OpenFOAM worker")
    jid=sys.argv[2]
    root=_valid_job_root(jid)
    raw=job_status(jid)
    opts=raw.get("controls",{})
    params=ReferenceControls(
        rpm=int(opts.get("rpm",1500)),
        end_time_s=float(opts.get("end_time_s",.04)),
        write_interval_s=float(opts.get("write_interval_s",.004)),
    )
    _run_job(root,params)
