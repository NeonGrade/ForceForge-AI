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
import fcntl
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
    """Use job-specific Docker names so a timed-out CLI cannot orphan a solver.

    Do not use global Docker pruning or stop unrelated user containers.
    """
    suffix=re.sub(r"[^a-z0-9-]","-",logname.lower())[:28]
    container_name=f"forceforge-{root.name}-{suffix}"
    args=[
        "docker","run","--rm","--name",container_name,"--network","none",
        "--cpus=4","--memory=6g","--pids-limit=256",
        "--user",str(os.getuid())+":"+str(os.getgid()),
        "-e","HOME=/tmp",
        "-v",str(root.resolve())+":/workspace",
        "-w","/workspace",IMAGE,"bash","-lc",script,
    ]
    try:
        with (root/logname).open("w",encoding="utf-8") as log:
            res=subprocess.run(
                args,cwd=root,stdin=subprocess.DEVNULL,
                stdout=log,stderr=subprocess.STDOUT,
                timeout=limit,check=False,text=True,
            )
        if res.returncode:
            tail=(root/logname).read_text(
                encoding="utf-8",errors="replace"
            )[-1800:]
            raise RuntimeError(
                f"OpenFOAM container stage {logname} failed "
                f"({res.returncode}): {tail}"
            )
    except (subprocess.TimeoutExpired,RuntimeError,OSError):
        # A killed Docker CLI can leave an actively consuming daemon-side
        # container behind. Stop only the uniquely named container for
        # this exact job and stage, never other Docker work.
        try:
            subprocess.run(
                ["docker","rm","-f",container_name],
                cwd=root,stdin=subprocess.DEVNULL,
                capture_output=True,check=False,timeout=12,
            )
        except (OSError,subprocess.TimeoutExpired):
            pass
        raise


def _manifest(root: Path,info: dict):
    tmp=root/"status.tmp"
    tmp.write_text(json.dumps(info,indent=2,ensure_ascii=False),encoding="utf-8")
    tmp.replace(root/"status.json")


def _load_status(root: Path) -> dict:
    source=root/"status.json"
    if not source.is_file():
        return {"stage":"NOT_FOUND","status":"NOT_FOUND"}
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError):
        return {
            "stage":"STATUS_ERROR","status":"FAILED",
            "message":"Persistent CFD status is missing or invalid; inspect launcher.log",
        }


def _worker_pid(root: Path, status: dict) -> int | None:
    pid_file=root/"worker.pid"
    try:
        pid=int(pid_file.read_text(encoding="ascii").strip()) if pid_file.exists() else int(status["pid"])
        return pid if pid > 0 else None
    except (ValueError,KeyError,OSError):
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid,0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _active_cfd_job_ids() -> list[str]:
    """Check process ownership, not just a possibly stale status JSON."""
    active=[]
    if not ROOT.is_dir():
        return active
    for folder in ROOT.iterdir():
        if not folder.is_dir() or not re.fullmatch(r"[0-9a-f]{16}",folder.name):
            continue
        state=_load_status(folder)
        if state.get("status") not in ("RUNNING","SOLVER_FINISHED_UNVERIFIED_FIELDS"):
            continue
        pid=_worker_pid(folder,state)
        if pid is not None and _pid_alive(pid):
            active.append(folder.name)
        elif pid is None and time.time()-float(state.get("started_epoch_s",0))<20:
            active.append(folder.name)
    return active


def active_cfd_job_ids() -> list[str]:
    """Read-only list of live, locally owned OpenFOAM worker jobs."""
    return _active_cfd_job_ids()


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
    # Cross-tab and cross-process launch coordination on macOS and Linux:
    # only one expensive OpenFOAM job at a time for this local user.
    with (ROOT/".launch.lock").open("a+") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        running=_active_cfd_job_ids()
        if running:
            raise RuntimeError(
                "An OpenFOAM job is already active: "+", ".join(running)+
                ". Restore/refresh that job instead of starting duplicates."
            )
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
        # Never rewrite status.json AFTER spawning the worker: it may
        # already have advanced to COPY/MESH/POSTPROCESS and its update
        # would be overwritten by the original QUEUED manifest.
        (folder/"worker.pid").write_text(str(worker.pid),encoding="ascii")
        return job_id


def job_status(job_id: str) -> dict:
    folder=_valid_job_root(job_id)
    current=_load_status(folder)
    if current.get("status") not in ("RUNNING","SOLVER_FINISHED_UNVERIFIED_FIELDS"):
        return current
    pid=_worker_pid(folder,current)
    age=time.time()-float(current.get("started_epoch_s",time.time()))
    if pid is not None and not _pid_alive(pid) and age>8:
        return {
            **current,"status":"FAILED","stage":"WORKER_EXITED",
            "message":"The CFD worker exited unexpectedly. Inspect launcher.log "
                      "and the named Docker stage logs in this job folder.",
        }
    if current.get("stage")=="QUEUED" and age>30:
        return {
            **current,"warning":"CFD stayed QUEUED for more than 30 seconds. "
            "Check launcher.log; this stage should usually advance quickly.",
        }
    return current


def _parse_time(s: str) -> float | None:
    try:
        val=float(s)
    except ValueError:
        return None
    return val if np.isfinite(val) and val > 0 else None



def _select_export_time_names(case: Path) -> list[str]:
    """Bound VTK to real nonzero solver writes with both computed U and p."""
    available=[]
    for directory in case.iterdir():
        name=directory.name
        if (not directory.is_dir() or not re.fullmatch(
            r"(?:0|[1-9][0-9]*)(?:[.][0-9]+)?(?:[eE][+-]?[0-9]+)?",name
        )):
            continue
        when=float(name)
        if not np.isfinite(when) or when<=0:
            continue
        if all(
            (directory/field).is_file() or (directory/(field+".gz")).is_file()
            for field in ("U","p")
        ):
            available.append((when,name))
    available.sort()
    if len(available)<2:
        raise ValueError(
            "Fewer than two genuine nonzero OpenFOAM write directories "
            "contain both solved U and p fields"
        )
    selected=sorted({0,len(available)//2,len(available)-1})
    return [available[index][1] for index in selected]


def _file_sha256(path: Path) -> str:
    digest=sha256()
    with path.open("rb") as reader:
        for chunk in iter(lambda:reader.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()


def _collect_vtk(
    root: Path, *, selected_time_names: list[str] | None = None,
    export_name: str = "VTK",
) -> dict:
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
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*",export_name):
        raise ValueError("Invalid OpenFOAM VTK output directory")
    # Constrain import to this conversion attempt: legacy case/VTK may
    # contain an initial unsolved 0/ field or unsupported polyhedral files.
    paths=sorted((case/export_name).rglob("*.vtk"),key=vtk_sort_key)
    if len(paths)<2:
        raise ValueError("No real time-dependent OpenFOAM VTK snapshots available")
    if selected_time_names is not None and len(paths)!=len(selected_time_names):
        raise ValueError(
            f"Found {len(paths)} VTK files, expected "
            f"{len(selected_time_names)} authentic solver write times"
        )
    times=[]
    xyz_frames=[]
    u_frames=[]
    p_frames=[]
    files=[]
    read_errors=[]
    for path in paths:
        if len(times)>=MAX_FRAMES:
            break
        # Skip boundary-only/patch VTK, require both vector U and scalar p.
        try:
            obj=meshio.read(path)
        except (Exception, SystemExit) as exc:
            # meshio's legacy reader can call sys.exit on unhandled VTK
            # POLYHEDRON (type 42); never leave a stale RUNNING manifest.
            read_errors.append(f"{path.name}: {type(exc).__name__}: {exc}")
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
                      "sha256":_file_sha256(path)})
    if len(times)<2:
        raise ValueError(
            "Unable to validate at least two snapshots with real U/p fields "
            "and extractable time labels. CFD status remains unverified. "
            + " ; ".join(read_errors[:3])
        )
    if selected_time_names is not None and len(times)!=len(selected_time_names):
        raise ValueError(
            f"Export yielded {len(times)} verified U/p frames, expected "
            f"{len(selected_time_names)} genuine solver write times"
        )
    # Only a one-to-one mapping to solver write directories licenses seconds.
    length=min(map(len,xyz_frames))
    payload={
        "sample_points":np.stack([a[:length] for a in xyz_frames]),
        "velocity_m_s":np.stack([a[:length] for a in u_frames]),
        "kinematic_pressure_m2_s2":np.stack([a[:length] for a in p_frames]),
        "vtk_record_indices":np.asarray(times),
    }
    if selected_time_names is not None:
        payload["physical_time_s"]=np.asarray(
            [float(name) for name in selected_time_names],dtype=float
        )
    np.savez_compressed(root/"actual_cfd_frames.npz",**payload)
    return {
        "frame_count":len(times),
        "polyhedron_handling":"OpenFOAM-native -poly-decomp (tet/pyramid VTK export)",
        "export_directory":export_name,
        "sample_points_per_frame":length,
        "source_vtk_files":files,
        "fields":["U [m/s]","p [m2/s2] (kinematic)"],
        "time_axis_note":(
            "Physical seconds checked against selected OpenFOAM U/p directories"
            if selected_time_names is not None else
            "VTK record indices only; physical time unverified"
        ),
        "file_sha256":sha256((root/"actual_cfd_frames.npz").read_bytes()).hexdigest(),
    }



def _export_verified_fields(root: Path, data: dict) -> dict:
    """Re-export *existing* computed U and p, never call pimpleFoam.

    Original CFD time directories remain untouched. A unique VTK name
    prevents an old polyhedron/initial-time file being mistaken for proof.
    """
    selected=_select_export_time_names(root/"case")
    folder_name="FFFields_"+secrets.token_hex(5)
    data["selected_export_source_times_s"]=[float(t) for t in selected]
    data["current_vtk_output_name"]=folder_name
    _manifest(root,data)
    export_script=(
        "set -eu\ncd /workspace/case\n"
        "foamToVTK -legacy -ascii -poly-decomp -no-boundary "
        "-no-point-data -no-lagrangian -name "+folder_name+" "
        "-time '"+",".join(selected)+"' "
        "-fields '(U p)' > /workspace/foamToVTK.log\n"
    )
    _docker(root,export_script,180,"export_console.log")
    # A real successful foamToVTK must name the physical write times it
    # processed; matching them prevents index/seconds mislabelling.
    log=(root/"foamToVTK.log").read_text(encoding="utf-8",errors="replace")
    actual=[float(m) for m in re.findall(
        r"(?m)^Time:\s*([0-9.eE+-]+)\s*$",log
    )]
    expected=[float(t) for t in selected]
    if (len(actual)!=len(expected) or
            not all(np.isclose(a,b,rtol=1e-7,atol=1e-9)
                    for a,b in zip(actual,expected))):
        raise ValueError(
            "OpenFOAM VTK export log times did not match the exact "
            "computed U/p source directories; refuse unverified seconds"
        )
    return _collect_vtk(
        root,selected_time_names=selected,export_name=folder_name
    )


def recover_fields_only(job_id: str) -> dict:
    """Repair a finished solver's U/p export without remeshing or solving.

    Called manually via --recover-fields after the original worker exits.
    It validates the original hashed pimpleFoam log and leaves case/time
    directories intact. It may write a NEW isolated VTK export directory.
    """
    root=_valid_job_root(job_id)
    if not root.is_dir():
        raise ValueError("Unknown local CFD job")
    with (root/".recover-fields.lock").open("a+") as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another recovery for this job is active") from exc
        data=_load_status(root)
        if data.get("status")=="COMPLETED":
            return data
        if data.get("solved") is not True or data.get("status") not in (
            "SOLVER_FINISHED_UNVERIFIED_FIELDS","FAILED"
        ):
            raise ValueError(
                "This job has no verified completed Navier-Stokes solve; "
                "field-only recovery is not permitted"
            )
        pid=_worker_pid(root,data)
        if pid is not None and _pid_alive(pid):
            proc=subprocess.run(
                ["ps","-p",str(pid),"-o","stat=","-o","command="],
                capture_output=True,text=True,timeout=8,check=False,
            )
            if (proc.returncode==0 and
                    "forceforge.rotating_cfd --worker "+job_id in proc.stdout and
                    not proc.stdout.strip().startswith("Z")):
                raise RuntimeError(
                    "Original worker is still active. Do not race it: "
                    "inspect ps and launcher.log before recovery."
                )
        solver_file=root/"log.pimpleFoam"
        if not solver_file.is_file() or not data.get("solver_log_sha256"):
            raise ValueError("Required original verified solver log is absent")
        solver_log=solver_file.read_text(errors="replace")
        if sha256(solver_log.encode()).hexdigest()!=data["solver_log_sha256"]:
            raise ValueError("Original solver proof SHA-256 has changed")
        opts=data.get("controls",{})
        end_time=float(opts["end_time_s"])
        steps=[float(x) for x in re.findall(
            r"(?m)^Time =\s*([0-9.eE+-]+)",solver_log
        )]
        if (len(steps)<2 or max(steps)<end_time*.90 or
                "Courant Number" not in solver_log or
                "End" not in solver_log[-4000:]):
            raise ValueError("Original OpenFOAM transient completion not verified")
        ok,why=docker_ready()
        if not ok:
            raise RuntimeError(why)
        data["status"]="SOLVER_FINISHED_UNVERIFIED_FIELDS"
        data["stage"]="POSTPROCESS_REAL_FIELDS"
        data["recovery_attempted_epoch_s"]=time.time()
        _manifest(root,data)
        try:
            summary=_export_verified_fields(root,data)
            data.update({
                "status":"COMPLETED",
                "stage":"REAL_TRANSIENT_FIELDS_READY",
                "source_type":data["geometry_origin"],
                "result":summary,
                "completed_epoch_s":time.time(),
            })
            _manifest(root,data)
            return data
        except Exception as exc:
            data.update({
                "status":"FAILED","stage":"POSTPROCESS_RECOVERY_FAILED",
                "error_type":type(exc).__name__,
                "message":str(exc)[:1900],
                "completed_epoch_s":time.time(),
                "solved":True,
            })
            _manifest(root,data)
            raise


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
# The directory name ALSO exists under resources/geometry/, but that
# directory contains STL assets ONLY and is not a solver-ready tutorial.
# Prefer the exact documented incompressible/pimpleFoam/RAS path.
src="$FOAM_TUTORIALS/incompressible/pimpleFoam/RAS/rotatingFanInRoom"
if [ ! -f "$src/system/controlDict" ]; then
  src="$(find "$FOAM_TUTORIALS/incompressible" -type f -name controlDict \
    -path '*/rotatingFanInRoom/system/controlDict' -print -quit 2>/dev/null | sed 's@/system/controlDict$@@')"
fi
if [ -z "$src" ] || [ ! -f "$src/constant/dynamicMeshDict" ]; then
  echo "ERROR: real rotatingFanInRoom solver case (not raw geometry assets) missing" >&2
  find "$FOAM_TUTORIALS" -type f -path '*/rotatingFanInRoom/system/controlDict' -print | head -n 20 || true
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
            # The official rotatingFanInRoom Allrun.pre copies
            # tutorials/resources/geometry/rotatingFanInRoom/*.stl.gz INTO
            # constant/triSurface. Thus the real fan surface DOES NOT
            # exist at this stage. Inject the source CAD rotor immediately
            # after this official copy and immediately BEFORE meshing.
            pre=root/"case"/"Allrun.pre"
            if not pre.is_file():
                raise ValueError("Official case does not provide a meshing preparation script")
            raw=pre.read_text(encoding="utf-8")
            anchor="runApplication surfaceFeatureExtract"
            if raw.count(anchor)!=1:
                raise ValueError("No uniquely identified native surface meshing stage for source rotor")
            insert=r'''
# ForceForge: exact source-STEP rotor wall, inserted after official
# tutorial geometry copy and BEFORE real feature extraction / snappyHexMesh.
ff_rotor="$(find constant/triSurface -type f \( -name 'fan.stl.gz' -o -name 'fan.stl' \) -print -quit)"
if [ -z "$ff_rotor" ]; then
    echo "Missing original fan CAD wall asset after copy" >&2; exit 61
fi
if [ ! -s /workspace/user_rotor.stl ]; then
    echo "Original STEP-derived blade STL is absent" >&2; exit 62
fi
case "$ff_rotor" in
    *.gz)
        gzip -c /workspace/user_rotor.stl > "$ff_rotor"
        gzip -dc "$ff_rotor" | sha256sum | cut -d' ' -f1 > /workspace/source_rotor_mesh_sha256
        ;;
    *)
        cp /workspace/user_rotor.stl "$ff_rotor"
        sha256sum "$ff_rotor" | cut -d' ' -f1 > /workspace/source_rotor_mesh_sha256
        ;;
esac
'''
            pre.write_text(raw.replace(anchor,insert+"\n"+anchor,1),encoding="utf-8")
            data["source_step_rotor_injected_before_actual_meshing"]=True
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
            applied=root/"source_rotor_mesh_sha256"
            if (not applied.is_file() or
                    applied.read_text(encoding="ascii").strip()!=data["custom_rotor_stl_sha256"]):
                raise ValueError(
                    "OpenFOAM preprocessing did not inject exact user STEP rotor "
                    "into snappyHexMesh input; cannot claim custom CAD CFD"
                )
            data["verified_mesh_input_rotor_stl_sha256"]=applied.read_text().strip()
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
        summary=_export_verified_fields(root,data)
        data.update({
            "status":"COMPLETED","stage":"REAL_TRANSIENT_FIELDS_READY",
            "source_type":data["geometry_origin"],
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
        fields={k:a[k].copy() for k in (
            "sample_points","velocity_m_s","kinematic_pressure_m2_s2",
            "vtk_record_indices",
        )}
        if "physical_time_s" in a.files:
            fields["physical_time_s"]=a["physical_time_s"].copy()
        return fields


if __name__=="__main__":
    if len(sys.argv)!=3:
        raise SystemExit(
            "Usage: python -m forceforge.rotating_cfd "
            "--worker|--recover-fields JOB_ID"
        )
    jid=sys.argv[2]
    root=_valid_job_root(jid)
    if sys.argv[1]=="--recover-fields":
        result=recover_fields_only(jid)
        print(json.dumps({
            "job_id":jid,"status":result["status"],"stage":result["stage"],
            "result":result.get("result")
        },indent=2),flush=True)
    elif sys.argv[1]=="--worker":
        raw=job_status(jid)
        opts=raw.get("controls",{})
        params=ReferenceControls(
            rpm=int(opts.get("rpm",1500)),
            end_time_s=float(opts.get("end_time_s",.04)),
            write_interval_s=float(opts.get("write_interval_s",.004)),
        )
        _run_job(root,params)
    else:
        raise SystemExit("Unknown rotating CFD command")
