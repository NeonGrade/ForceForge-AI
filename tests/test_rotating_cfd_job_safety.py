"""Safety regressions for multiple Streamlit tabs launching real OpenFOAM.

These tests use fake workers and fake Docker; no solver output is created.
Actual pimpleFoam/AMI must pass the separate native integration workflow.
"""
import json
import os
from pathlib import Path
import subprocess
import time

import pytest

import forceforge.rotating_cfd as cfd


def test_unknown_job_does_not_masquerade_as_running(tmp_path, monkeypatch):
    monkeypatch.setattr(cfd, "ROOT", tmp_path)
    assert cfd.job_status("a" * 16)["status"] == "NOT_FOUND"


def test_launch_never_overwrites_child_stage_and_refuses_duplicate(tmp_path, monkeypatch):
    store=tmp_path/"jobs"
    monkeypatch.setattr(cfd, "ROOT", store)
    monkeypatch.setattr(cfd, "docker_ready", lambda: (True, "sha256:installed"))
    starts=[]
    class SimulatedWorker:
        def __init__(self, cmd, **kwargs):
            job_id=cmd[-1]
            folder=store/job_id
            state=json.loads((folder/"status.json").read_text())
            state["stage"]="MESH_AND_SOLVE_REAL_TRANSIENT"
            state["status"]="RUNNING"
            (folder/"status.json").write_text(json.dumps(state))
            starts.append(job_id)
            self.pid=os.getpid()
    monkeypatch.setattr(cfd.subprocess, "Popen", SimulatedWorker)
    one=cfd.launch_reference_job(
        cfd.ReferenceControls(rpm=600,end_time_s=.008,write_interval_s=.002)
    )
    assert (store/one/"worker.pid").read_text()==str(os.getpid())
    assert cfd.job_status(one)["stage"]=="MESH_AND_SOLVE_REAL_TRANSIENT"
    assert cfd.active_cfd_job_ids()==[one]
    with pytest.raises(RuntimeError,match="already active"):
        cfd.launch_reference_job(cfd.ReferenceControls(
            rpm=600,end_time_s=.008,write_interval_s=.002
        ))
    assert starts==[one]


def test_worker_exit_yields_actionable_failure_without_fake_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(cfd,"ROOT",tmp_path)
    folder=tmp_path/("b"*16)
    folder.mkdir()
    (folder/"status.json").write_text(json.dumps({
        "status":"RUNNING","stage":"QUEUED",
        "started_epoch_s":time.time()-45,
    }))
    (folder/"worker.pid").write_text("9999999")
    monkeypatch.setattr(cfd,"_pid_alive",lambda pid:False)
    status=cfd.job_status("b"*16)
    assert status["status"]=="FAILED"
    assert status["stage"]=="WORKER_EXITED"
    assert "launcher.log" in status["message"]
    assert cfd.active_cfd_job_ids()==[]


def test_queued_heartbeat_warning_when_worker_is_alive(tmp_path,monkeypatch):
    monkeypatch.setattr(cfd,"ROOT",tmp_path)
    folder=tmp_path/("c"*16)
    folder.mkdir()
    (folder/"status.json").write_text(json.dumps({
        "status":"RUNNING","stage":"QUEUED",
        "started_epoch_s":time.time()-60,
    }))
    (folder/"worker.pid").write_text(str(os.getpid()))
    status=cfd.job_status("c"*16)
    assert status["status"]=="RUNNING"
    assert "warning" in status
    assert "launcher.log" in status["warning"]


def test_native_docker_timeout_removes_only_its_own_named_container(
    tmp_path,monkeypatch
):
    folder=tmp_path/("d"*16)
    folder.mkdir()
    seen=[]
    def fake_run(args,**kwargs):
        seen.append(args)
        if args[:2]==["docker","run"]:
            raise subprocess.TimeoutExpired(cmd=args,timeout=1)
        return subprocess.CompletedProcess(args,0,b"",b"")
    monkeypatch.setattr(cfd.subprocess,"run",fake_run)
    with pytest.raises(subprocess.TimeoutExpired):
        cfd._docker(folder,"true",1,"solver_console.log")
    name="forceforge-"+("d"*16)+"-solver-console-log"
    assert ["docker","rm","-f",name] in seen
    assert seen[0][0:2]==["docker","run"]
    assert seen[0][seen[0].index("--name")+1]==name
