# ForceForge X: safe local CFD job and Docker recovery

## What the indicators mean
- `RUNNING / QUEUED` is an internal launch state; it does **not** establish that OpenFOAM has solved Navier-Stokes or even started meshing. If this remains for more than 30 seconds, inspect the worker diagnostics.
- `COPY_OFFICIAL_TUTORIAL`: source OpenFOAM tutorial preparation.
- `MESH_AND_SOLVE_REAL_TRANSIENT`: Gmsh/snappyHexMesh preparation and then actual pimpleFoam. Use `solver_console.log` and `log.pimpleFoam` to distinguish these sub-stages.
- `SOLVER_FINISHED_UNVERIFIED_FIELDS / POSTPROCESS_REAL_FIELDS`: solver has time steps; real velocity/pressure frame export has not passed validation.
- `COMPLETED`: actual VTK U/p fields passed verification; only then enable animated CFD.
- `FAILED` / `WORKER_EXITED`: inspect status.json and the log files before retrying.

## Read-only Mac terminal checks

```bash
JOB=REPLACE_WITH_THE_EXACT_16_HEX_JOB_ID
DIR="$HOME/.forceforge_x/transient_cfd/$JOB"

cat "$DIR/status.json"
test -f "$DIR/worker.pid" && ps -p "$(cat "$DIR/worker.pid")" -o pid,etime,stat,command

for log in launcher.log copy_openfoam.log solver_console.log log.pimpleFoam foamToVTK.log; do
  if [ -f "$DIR/$log" ]; then
    echo "======= $log ======="
    tail -n 15 "$DIR/$log"
  fi
done

docker ps --format 'table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}'
docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}'
for id in $(docker ps --filter ancestor=opencfd/openfoam-default:2512 -q); do
  docker inspect "$id" --format '{{.Name}} {{range .Mounts}}{{.Source}} -> {{.Destination}} {{end}}'
done
```

The Docker bind source identifies which local CFD job owns a container.
**Do not** run `docker system prune`, `docker stop $(docker ps -q)`,
or delete `~/.forceforge_x`. These may erase evidence or unrelated Docker
applications.

For an orphaned container that has been positively matched to a failed
job, you may use `docker stop CONTAINER_ID`, then `docker rm CONTAINER_ID`
with the *specific* ID. Do not stop an active job that is still writing
legitimate solver time steps.

## Reliability changes
- `launch_reference_job` now uses an exclusive local launch lock and
  refuses to start a second live worker from another Streamlit tab.
- Worker PID is written separately; the launcher cannot overwrite a
  later progress stage back to QUEUED.
- Missing job directories no longer masquerade as RUNNING.
- A dead worker with stale status becomes WORKER_EXITED rather than
  showing an endless spinner.
- Each new Docker container has a job-specific name and is cleaned
  up on stage failure or timeout without touching unrelated containers.
- UI shows active jobs, a QUEUED stall warning, and job-specific
  diagnostic commands.

This release **does not** by itself prove a full transient CFD
solution. The v0.3 integration requires a successful native OpenFOAM
pimpleFoam + actual U/p field-export test and separate source-STEP
sliding-AMI acceptance.

## Bounded export and failure evidence

- Postprocessing picks at most three actual nonzero solver write times
  containing both `U` and `p`; the unsolved initial `0/` is excluded.
- `foamToVTK -legacy -ascii -no-point-data -no-boundary -time ...`
  avoids interpolating and exporting all solver time steps.
- Exactly one validated VTK U/p field frame per selected source time
  is required before physical seconds are presented in the UI.
- GitHub Actions uploads `status.json`, `foamToVTK.log`,
  `export_console.log`, and worker/solver logs on polling timeout.
- Full dynamic CFD still requires successful real OpenFOAM CI acceptance.

## Nov 15: Mac OpenFOAM result recovery without rerunning CFD

Screenshot evidence for job `2e9aefe6c51efd9d`: `pimpleFoam`
ended after 198 real steps at simulation time 0.04003 seconds and
`foamToVTK` completed. The Python reader then failed on OpenFOAM's
VTK polyhedron cell type 42. This is a parser/export issue, not evidence
of a new need to solve Navier-Stokes.

After updating your local source to the PR #16 branch, **close or wait
for the original CFD worker to exit** (verify `worker.pid` using `ps`).
Then run from the repository root with its activated venv:

```bash
python -m forceforge.rotating_cfd --recover-fields 2e9aefe6c51efd9d
```

The repair verifies the original solver log's SHA-256 and genuine time
steps, then runs **only foamToVTK**, using `-poly-decomp` and a new
unique `FFFields_*` directory. It does not call `pimpleFoam`, does not
remesh, and does not delete the original case, time directories, or
previous VTK files. The new export is restricted to real nonzero U/p
write directories, and the reader rejects missing/mismatched field
and time data.

Do not run recovery while the original worker still owns the job.
If the recovery fails, `status.json` becomes `POSTPROCESS_RECOVERY_FAILED`
with an error; inspect `foamToVTK.log`, `export_console.log`, and
`launcher.log`. A false `COMPLETED` state is never generated.

## ARM64 VTK type-42 recovery after Segmentation fault 139

The 300-mm rotating-fan reference run on macOS completed 198
pimpleFoam steps and the original plain foamToVTK export. A subsequent
recovery attempt using foamToVTK -poly-decomp crashed inside OpenFOAM's
geometry writer with exit code 139. Do not try that argument again on
this installation.

The fixed Python reader uses native VTK to import OpenFOAM polyhedral
VTK cells (type 42), including actual finite-volume cell-centred U
and p. It samples up to 500 genuine cell centres per frame. An old
case_N.vtk index N is mapped to the exact Nth Time record from the
SHA-256-verified pimpleFoam log (never treated as seconds). Existing
real VTK files are reused first, without Docker or extra CFD.

For the already-solved job (run from the ForceForge-AI repository
with its Python venv active):

    git pull --ff-only origin feature/stress-local-validation-v11
    python -m pip install "vtk>=9.6,<10"
    python -m forceforge.rotating_cfd --recover-fields 2e9aefe6c51efd9d

If successful, the same Job ID becomes COMPLETED /
REAL_TRANSIENT_FIELDS_READY. Then refresh or restore it inside the
Transient CFD Streamlit page. Original case, logs and time directories
are not deleted.

If old snapshots are insufficient, field-only recovery can run a
bounded plain foamToVTK (without -poly-decomp), but no pimpleFoam.
The explicit status/error remains FAILED when real U/p data cannot
be verified. CI must still prove full native end-to-end acceptance.
