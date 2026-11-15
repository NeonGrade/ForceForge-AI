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

docker ps --format 'table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.CPUPerc}}'
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
