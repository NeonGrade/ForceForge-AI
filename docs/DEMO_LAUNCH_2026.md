## Judge-ready launcher (November 15 final submission)

For a concise ForceForge-only demonstration, this branch has a separate
judge-facing entrypoint. It does **not** replace the historical research
app or teammates' code. It never launches OpenFOAM automatically.

From your existing Mac checkout:


```bash
git switch hack-the-nest-2026-submission
git pull --ff-only origin hack-the-nest-2026-submission
source .venv/bin/activate
sh scripts/run_hackathon_demo.sh
```

Open http://localhost:8501. The front page presents exactly three
steps: natural-language STEP, real bracket FEA and verified rotating CFD.
If finished job files exist in `~/.forceforge_x/transient_cfd`,
the launcher verifies result hashes and offers a one-click replay without
re-solving. Keep the terminal window open while judges view the demo.

A locally recorded video (<=3 min) is still mandatory on Devpost;
this local Streamlit URL is not publicly accessible.
