/* ForceForge 3D workspace: no websocket, no external JS/CDN dependency.
 * Backend 3D work executes in a separate process; canvas draws only bounded
 * surface triangles. Faults leave the HTTP server and this UI responsive.
 */
"use strict";
(function () {
  const $ = (id) => document.getElementById(id);
  const form = $("studyForm");
  const canvas = $("solidCanvas");
  const ctx = canvas.getContext("2d", {alpha: false});
  const ui = {
    geometry: $("geometry"), boxFields: $("boxFields"),
    stepFields: $("stepFields"), file: $("stepFile"), filename: $("filename"),
    meshSize: $("meshSize"), meshSizeValue: $("meshSizeValue"),
    status: $("statusMessage"), solve: $("solveButton"), solveLabel: $("solveLabel"),
    health: $("health"), healthText: $("healthText"),
    amp: $("amplification"), ampValue: $("amplificationValue"),
    fit: $("fitButton"), export: $("exportButton"), placeholder: $("placeholder"),
  };
  let result = null, busy = false, revision = 0;
  let yaw = -0.68, pitch = -0.35, zoom = 1.0;
  let drag = false, dragX = 0, dragY = 0, framePending = false;

  function status(text, type) {
    ui.status.textContent = text;
    ui.status.className = "status-message" + (type ? " " + type : "");
  }
  function metric(id, text) {
    $(id).textContent = text;
  }
  function resetMetrics() {
    for (const id of ["nodesMetric", "tetMetric", "stressMetric", "dispMetric", "balanceMetric"]) metric(id, "—");
  }
  function invalidate() {
    revision++;
    result = null;
    ui.placeholder.hidden = false;
    ui.export.disabled = true;
    $("legendTop").textContent = "—";
    resetMetrics();
    if (!busy) status("Inputs changed. Run the 3D solver to refresh the results.");
    scheduleRender();
  }

  function switchSource() {
    const step = ui.geometry.value === "step";
    ui.boxFields.hidden = step;
    ui.stepFields.hidden = !step;
    for (const el of ui.boxFields.querySelectorAll("input")) el.disabled = step;
    invalidate();
  }
  ui.geometry.addEventListener("change", switchSource);
  for (const id of ["length", "width", "height", "E", "poisson", "force", "axis", "cadUnit"]) {
    $(id).addEventListener("change", invalidate);
  }
  ui.meshSize.addEventListener("input", function () {
    ui.meshSizeValue.textContent = ui.meshSize.value;
    invalidate();
  });
  ui.file.addEventListener("change", function () {
    const file = ui.file.files[0];
    ui.filename.textContent = file ? file.name + " · " + (file.size / 1e6).toFixed(2) + " MB" : "No file selected · maximum 4 MB";
    invalidate();
  });
  ui.amp.addEventListener("input", function () {
    ui.ampValue.textContent = ui.amp.value + "×";
    scheduleRender();
  });

  async function binaryBase64(file) {
    const raw = new Uint8Array(await file.arrayBuffer());
    let binary = "";
    const chunk = 16384;
    for (let i = 0; i < raw.length; i += chunk) {
      binary += String.fromCharCode.apply(null, raw.subarray(i, i + chunk));
    }
    return btoa(binary);
  }
  async function payload() {
    const asNumber = (id) => Number($(id).value);
    const data = {
      geometry: ui.geometry.value, mesh_size_mm: asNumber("meshSize"),
      E_gpa: asNumber("E"), poisson: asNumber("poisson"),
      force_n: asNumber("force"), axis: $("axis").value,
    };
    if (data.geometry === "box") {
      data.length_mm = asNumber("length");
      data.width_mm = asNumber("width");
      data.height_mm = asNumber("height");
    } else {
      const file = ui.file.files[0];
      if (!file) throw new Error("Select a STEP file before solving.");
      if (file.size < 1 || file.size > 4000000) {
        throw new Error("STEP file must be non-empty and at most 4 MB.");
      }
      data.cad_unit = $("cadUnit").value;
      data.step_base64 = await binaryBase64(file);
    }
    return data;
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    if (busy) return;
    busy = true;
    ui.solve.disabled = true;
    ui.solveLabel.textContent = "SOLVING ...";
    const startedRevision = revision;
    status("Meshing and computing in an isolated worker. You can still navigate the workspace.");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 80000);
    try {
      const data = await payload();
      const response = await fetch("/api/solid3d/solve", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(data),
        signal: controller.signal,
      });
      let body;
      try { body = await response.json(); }
      catch (parseError) { throw new Error("Server returned an invalid response. Check the local server terminal."); }
      if (!response.ok || !body.ok) {
        throw new Error(body.error || "FEA solve failed (HTTP " + response.status + ").");
      }
      if (startedRevision !== revision) {
        status("Study settings changed during solve. Previous result ignored; press Solve again.");
        return;
      }
      result = body;
      ui.placeholder.hidden = true;
      ui.export.disabled = false;
      metric("nodesMetric", String(body.mesh.node_count));
      metric("tetMetric", String(body.mesh.tetrahedra));
      metric("stressMetric", body.metrics.max_von_mises_mpa.toFixed(3));
      metric("dispMetric", body.metrics.max_displacement_mm.toFixed(6));
      metric("balanceMetric", body.metrics.equilibrium_residual_n.toExponential(2));
      $("legendTop").textContent = body.metrics.max_von_mises_mpa.toFixed(2);
      status("Complete · " + body.mesh.surface_triangles + " boundary faces rendered · server remained connected.", "success");
      scheduleRender();
    } catch (error) {
      const message = error && error.name === "AbortError" ?
        "3D request timed out. Increase tetrahedral size or simplify CAD geometry." :
        (error && error.message ? error.message : "3D request failed.");
      status(message + " The main workspace remains available.", "error");
    } finally {
      clearTimeout(timer);
      busy = false;
      ui.solve.disabled = false;
      ui.solveLabel.textContent = "GENERATE MESH & SOLVE";
    }
  });

  async function ping() {
    try {
      const signal = AbortSignal.timeout ? AbortSignal.timeout(4000) : undefined;
      const response = await fetch("/api/health", {cache: "no-store", signal});
      if (!response.ok) throw new Error("Unavailable");
      ui.health.className = "health online";
      ui.healthText.textContent = "LOCAL SOLVER ONLINE";
    } catch (error) {
      ui.health.className = "health offline";
      ui.healthText.textContent = "SERVER OFFLINE";
    }
  }
  ping();
  setInterval(ping, 15000);

  function resizeCanvas() {
    const bounds = canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.max(1, Math.floor(bounds.width * dpr));
    const h = Math.max(1, Math.floor(bounds.height * dpr));
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w; canvas.height = h;
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return {width: bounds.width, height: bounds.height};
  }

  const palette = [
    [0.00, 80, 121, 213], [0.25, 99, 202, 213],
    [0.50, 160, 221, 121], [0.75, 255, 188, 82],
    [1.00, 245, 89, 84],
  ];
  function stressColor(ratio, shade) {
    const t = Math.max(0, Math.min(1, ratio));
    let j = 1;
    while (j < palette.length - 1 && palette[j][0] < t) j++;
    const a = palette[j - 1], b = palette[j];
    const f = (t - a[0]) / (b[0] - a[0]);
    const k = shade;
    return "rgb(" +
      Math.round((a[1] + (b[1] - a[1]) * f) * k) + "," +
      Math.round((a[2] + (b[2] - a[2]) * f) * k) + "," +
      Math.round((a[3] + (b[3] - a[3]) * f) * k) + ")";
  }

  function render() {
    framePending = false;
    const size = resizeCanvas();
    const w = size.width, h = size.height;
    ctx.fillStyle = "#152337";
    ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = "rgba(102,142,159,.09)";
    ctx.lineWidth = 1;
    const spacing = 36;
    for (let x = 0; x < w; x += spacing) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
    }
    for (let y = 0; y < h; y += spacing) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
    }
    if (!result || !result.vertices_mm || !result.boundary_faces) return;

    const vertices = result.vertices_mm;
    const disp = result.displacements_mm;
    const faces = result.boundary_faces;
    const nodal = result.nodal_von_mises_mpa;
    const amp = Number(ui.amp.value);
    const center = [0, 0, 0];
    for (const p of vertices) {
      center[0] += p[0]; center[1] += p[1]; center[2] += p[2];
    }
    center[0] /= vertices.length; center[1] /= vertices.length; center[2] /= vertices.length;
    const cy = Math.cos(yaw), sy = Math.sin(yaw);
    const cp = Math.cos(pitch), sp = Math.sin(pitch);
    const points = new Array(vertices.length);
    let minx = Infinity, maxx = -Infinity, miny = Infinity, maxy = -Infinity;
    for (let i = 0; i < vertices.length; i++) {
      const v = vertices[i], u = disp[i];
      const dx = v[0] + amp*u[0] - center[0];
      const dy = v[1] + amp*u[1] - center[1];
      const dz = v[2] + amp*u[2] - center[2];
      const xx = dx*cy + dz*sy;
      const zz = -dx*sy + dz*cy;
      const yy = dy*cp - zz*sp;
      const depth = dy*sp + zz*cp;
      points[i] = [xx, yy, depth];
      minx = Math.min(minx, xx); maxx = Math.max(maxx, xx);
      miny = Math.min(miny, yy); maxy = Math.max(maxy, yy);
    }
    const spanx = Math.max(maxx - minx, .001), spany = Math.max(maxy - miny, .001);
    const factor = Math.max(.001, Math.min((w - 130) / spanx, (h - 130) / spany)) * zoom;
    const originx = (w - (minx+maxx)*factor)/2;
    const originy = (h + (miny+maxy)*factor)/2;
    const p2 = points.map(p => [originx + p[0]*factor, originy - p[1]*factor, p[2]]);
    const vmax = Math.max(result.metrics.max_von_mises_mpa, 1e-12);
    const triangles = [];
    for (const ids of faces) {
      const a = p2[ids[0]], b = p2[ids[1]], c = p2[ids[2]];
      if (!a || !b || !c) continue;
      const ratio = (nodal[ids[0]] + nodal[ids[1]] + nodal[ids[2]]) / (3*vmax);
      const dx = b[0] - a[0], dy = b[1] - a[1];
      const ex = c[0] - a[0], ey = c[1] - a[1];
      const area = dx*ey - dy*ex;
      if (Math.abs(area) < .0001) continue;
      const shade = 0.76 + .24 * Math.min(1, Math.abs(area)/1400);
      triangles.push({a, b, c, ratio, shade, depth:(a[2]+b[2]+c[2])/3});
    }
    triangles.sort((a,b) => a.depth - b.depth);
    ctx.lineJoin = "round"; ctx.lineWidth = .65;
    for (const tri of triangles) {
      ctx.beginPath();
      ctx.moveTo(tri.a[0], tri.a[1]);
      ctx.lineTo(tri.b[0], tri.b[1]);
      ctx.lineTo(tri.c[0], tri.c[1]);
      ctx.closePath();
      ctx.fillStyle = stressColor(tri.ratio, tri.shade);
      ctx.fill();
      ctx.strokeStyle = "rgba(9,24,37,.15)";
      ctx.stroke();
    }
  }
  function scheduleRender() {
    if (!framePending) {
      framePending = true;
      window.requestAnimationFrame(render);
    }
  }
  canvas.addEventListener("pointerdown", e => {
    if (!result) return;
    drag = true; dragX = e.clientX; dragY = e.clientY;
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener("pointermove", e => {
    if (!drag || !result) return;
    yaw += (e.clientX - dragX) * .009;
    pitch = Math.max(-1.5, Math.min(1.5, pitch + (e.clientY - dragY)*.009));
    dragX = e.clientX; dragY = e.clientY;
    scheduleRender();
  });
  canvas.addEventListener("pointerup", () => {drag = false;});
  canvas.addEventListener("pointercancel", () => {drag = false;});
  canvas.addEventListener("wheel", e => {
    if (!result) return;
    e.preventDefault();
    zoom = Math.max(.35, Math.min(5, zoom * (e.deltaY > 0 ? .9 : 1.1)));
    scheduleRender();
  }, {passive:false});
  ui.fit.addEventListener("click", () => {
    yaw = -.68; pitch = -.35; zoom = 1; scheduleRender();
  });
  ui.export.addEventListener("click", () => {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], {type:"application/json"});
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url; link.download = "forceforge_3d_fea_result.json";
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  window.addEventListener("resize", scheduleRender);
  if (window.ResizeObserver) new ResizeObserver(scheduleRender).observe($("viewport"));
  scheduleRender();
})();
