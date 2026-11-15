/* ForceForge Engineering Workspace II — no third-party UI libraries.
   All engineering results originate from /api/* (the Python FEA modules).
   The browser only projects the returned geometry into the viewport. */
(() => {
  'use strict';

  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const cfg0 = {
    topology: 'Triangle', material: 'steel', span_m: 2, height_m: 1,
    area_mm2: 180, base_load_n: 1000, max_displacement_mm: 2,
    yield_safety_factor: 2, buckling_safety_factor: 2,
    load_uncertainty: 0.20, e_uncertainty: 0.10, area_uncertainty: 0.10,
  };
  const state = {
    config: {...cfg0}, solve: null, search: null, challenge: null, ml: null,
    parsed: null, mode: 'design', visual: 'stress', showDeform: true,
    deformScale: 300, grid: true, zoom: 1, panX: 0, panY: 0,
    selected: null, hovered: null, tooltip: null,
    challengeMultiplier: 1.4,
    brief: 'Design a lightweight 2 m truss bridge under 1000 N, with displacement limit 2 mm.',
    useApi: false, busy: new Set(), connected: false, error: null,
  };
  let solveTimer = 0;
  let solveSeq = 0;
  let toastTimer = 0;
  const viewport = $('#viewport');
  const svg = $('#sceneSvg');
  const bodyShell = $('.body-shell');
  const content = $('#panelContent');

  const num = (v, d = 2) => typeof v === 'number' && Number.isFinite(v)
    ? v.toLocaleString('en-US', {minimumFractionDigits: d, maximumFractionDigits: d}) : '—';
  const snum = (v, d = 2) => typeof v === 'number' && Number.isFinite(v)
    ? `${v >= 0 ? '+' : '−'}${num(Math.abs(v), d)}` : '—';
  const pct = v => num(v * 100, 0);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clamp = (x, min, max) => Math.max(min, Math.min(max, x));
  const svgText = value => esc(value);
  const ICON = name => `<svg class="icon"><use href="#i-${name}"/></svg>`;

  function toast(message, error = false) {
    const el = $('#toast');
    el.textContent = message;
    el.classList.toggle('error', error);
    el.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('show'), 3700);
  }

  async function post(route, data) {
    const response = await fetch(route, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data), cache: 'no-store',
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `Backend returned HTTP ${response.status}`);
    return payload;
  }

  function setConnected(connected, solving = false) {
    state.connected = connected;
    const dot = $('.status-dot');
    dot.className = 'status-dot' + (!connected ? ' offline' : solving ? ' pending' : '');
    $('#connectionText').textContent = !connected ? 'Solver offline' : solving ? 'Solving FEA…' : 'Solver connected';
  }

  function renderControls() {
    $$('[data-key]').forEach(element => {
      const key = element.dataset.key;
      if (element.value !== String(state.config[key])) element.value = state.config[key];
    });
    const heightInput = $('[data-key="height_m"]');
    heightInput.min = String(state.config.span_m * 0.2);
    heightInput.max = String(state.config.span_m * 1.25);
    heightInput.step = '0.01';
    $$('[data-value-key]').forEach(el => {
      const key = el.dataset.valueKey;
      const value = state.config[key];
      const output = key === 'span_m' || key === 'height_m' ? `${num(value,2)} <small>m</small>`
        : key === 'area_mm2' ? `${num(value,0)} <small>mm²</small>`
        : key === 'base_load_n' ? `${num(value,0)} <small>N</small>`
        : key === 'max_displacement_mm' ? `${num(value,2)} <small>mm</small>`
        : key.includes('safety_factor') ? `${num(value,2)} <small>×</small>`
        : `${pct(value)} <small>%</small>`;
      el.innerHTML = output;
    });
    $$('[data-topology]').forEach(b => {
      b.classList.toggle('selected', b.dataset.topology === state.config.topology);
      b.setAttribute('aria-pressed', b.dataset.topology === state.config.topology ? 'true' : 'false');
    });
    $('#viewportTitle').innerHTML = `${esc(state.config.topology)} Truss <span>·</span> Load Case 01`;
  }

  function clearComputed({requirementsChanged = true} = {}) {
    state.solve = null;
    state.challenge = null;
    state.selected = null;
    state.hovered = null;
    if (requirementsChanged) { state.search = null; state.ml = null; }
    state.error = null;
  }

  function updateConfig(key, value) {
    if (!Object.hasOwn(state.config, key)) return;
    const original = state.config[key];
    if (original === value) return;
    const requirementsChanged = !['topology','height_m','area_mm2'].includes(key);
    state.config[key] = value;
    if (key === 'span_m') {
      // Keep the model inside the physically implemented geometry envelope.
      state.config.height_m = Number(clamp(state.config.height_m, value*0.2, value*1.25).toFixed(4));
    }
    clearComputed({requirementsChanged});
    renderControls();
    renderScene();
    renderMetrics();
    renderPanel();
    scheduleSolve();
  }

  function scheduleSolve() {
    clearTimeout(solveTimer);
    ++solveSeq;
    solveTimer = setTimeout(runSolve, 140);
  }

  async function runSolve() {
    const seq = ++solveSeq;
    state.busy.add('solve');
    setConnected(state.connected, true);
    try {
      const result = await post('/api/solve', state.config);
      if (seq !== solveSeq) return;
      state.solve = result;
      state.error = null;
      setConnected(true, false);
    } catch (err) {
      if (seq !== solveSeq) return;
      state.solve = null;
      state.error = err.message;
      setConnected(false);
    } finally {
      if (seq === solveSeq) {
        state.busy.delete('solve');
        renderMetrics(); renderScene(); renderPanel();
      }
    }
  }

  function setMode(mode) {
    // The original five tools remain mounted. The optional 3D mode is an
    // embedded, same-origin study backed by a separate crash-isolated worker.
    // Switching modes does not discard the current 2D design or FEA results.
    state.mode = mode;
    const solid = mode === 'solid3d';
    $('[data-panel]').forEach(el => {
      const active = el.dataset.panel === mode;
      el.classList.toggle('active', active);
      el.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    bodyShell.classList.toggle('solid-mode', solid);
    if (solid && window.location.hash !== '#solid3d') {
      window.history.replaceState(null, '', window.location.pathname + window.location.search + '#solid3d');
    } else if (!solid && window.location.hash === '#solid3d') {
      window.history.replaceState(null, '', window.location.pathname + window.location.search);
    }
    const frame = $('#solidWorkspaceFrame');
    if (frame) {
      frame.hidden = !solid;
      if (solid && !frame.getAttribute('src')) {
        frame.setAttribute('src', frame.dataset.src);
      }
    }
    const current = $('.crumb-current');
    if (current) current.textContent = solid ? '3D Solid Study' : 'Truss Study 01';
    const tag = $('.file-tag');
    if (tag) tag.textContent = solid ? '3D · EXPERIMENTAL' : '2D · STATIC';
    if (solid) {
      bodyShell.classList.remove('show-left', 'show-right');
      return;
    }
    if (window.matchMedia('(max-width:1050px)').matches) {
      bodyShell.classList.remove('show-left');
      bodyShell.classList.add('show-right');
    }
    renderPanel();
    renderMetrics();
    renderScene();
  }

  function setBusy(mode, value) {
    value ? state.busy.add(mode) : state.busy.delete(mode);
    renderPanel();
  }

  // Hash only requirement-level inputs. Local geometry changes do not
  // invalidate an already screened design space, but requirement changes do.
  const reqKey = () => JSON.stringify(Object.entries(state.config)
    .filter(([key]) => !['topology','height_m','area_mm2'].includes(key)));

  async function runSearch() {
    if (state.busy.has('search')) return;
    const fingerprint = reqKey();
    setBusy('search', true);
    try {
      const incoming = await post('/api/search', {...state.config});
      if (fingerprint !== reqKey()) return;
      state.search = incoming;
      toast(`FEA screening complete · ${incoming.feasible_count} / ${incoming.total_count} feasible`);
    } catch (err) { if (fingerprint === reqKey()) toast(`Optimization failed: ${err.message}`, true); }
    finally { setBusy('search', false); }
  }

  async function runChallenge(redesign = false) {
    if (state.busy.has('challenge')) return;
    const fingerprint = JSON.stringify([state.config, state.challengeMultiplier]);
    setBusy('challenge', true);
    try {
      const incoming = await post('/api/challenge', {...state.config,
        challenge_multiplier: state.challengeMultiplier, redesign});
      if (fingerprint !== JSON.stringify([state.config, state.challengeMultiplier])) return;
      state.challenge = incoming;
      if (redesign) toast(incoming.redesign.best
        ? 'FEA-verified redesign available' : 'No feasible redesign in the search grid', !incoming.redesign.best);
    } catch (err) {
      if (fingerprint === JSON.stringify([state.config, state.challengeMultiplier])) toast(`Challenge failed: ${err.message}`, true);
    } finally { setBusy('challenge', false); renderMetrics(); renderScene(); }
  }

  async function runML() {
    if (state.busy.has('ml')) return;
    const fingerprint = reqKey();
    setBusy('ml', true);
    try {
      const incoming = await post('/api/ml', {...state.config, propose:true});
      if (fingerprint !== reqKey()) return;
      state.ml = incoming;
      toast('ML proposals checked with actual FEA');
    } catch (err) { if (fingerprint === reqKey()) toast(`ML validation failed: ${err.message}`, true); }
    finally { setBusy('ml', false); }
  }

  async function runAgent() {
    if (state.busy.has('agent')) return;
    setBusy('agent', true);
    try { state.parsed = await post('/api/interpret', {prompt:state.brief, use_api:state.useApi}); toast('Requirements extracted — review before applying'); }
    catch (err) { toast(`Interpretation failed: ${err.message}`, true); }
    finally { setBusy('agent', false); }
  }

  function applyCandidate(candidate) {
    if (!candidate || !['Triangle','Warren-2','Fan'].includes(candidate.topology)) return;
    const {height_m, area_mm2} = candidate;
    if (![height_m, area_mm2].every(x => Number.isFinite(x))) return;
    state.config.topology = candidate.topology;
    state.config.height_m = clamp(height_m, .2*state.config.span_m, 1.25*state.config.span_m);
    state.config.area_mm2 = clamp(area_mm2, 60, 800);
    clearComputed({requirementsChanged:false});
    renderControls(); resetView();
    renderMetrics(); scheduleSolve(); setMode('design');
    toast('FEA-verified candidate loaded into the viewport');
  }

  function applyBrief() {
    const values = state.parsed?.interpreted;
    if (!values) return;
    // Validation must be atomic: a rejected brief never changes live inputs.
    if (values.span_m < .5 || values.span_m > 4 || values.load_n < 100 || values.load_n > 3000 || values.max_displacement_mm < .25 || values.max_displacement_mm > 12) {
      toast('Parsed values exceed the workspace limits. Adjust the brief and try again.', true);
      return;
    }
    state.config.span_m = values.span_m;
    state.config.base_load_n = values.load_n;
    state.config.max_displacement_mm = values.max_displacement_mm;
    state.config.height_m = Number((values.span_m * 0.5).toFixed(4));
    clearComputed(); renderControls(); resetView(); renderMetrics(); scheduleSolve(); setMode('design');
    toast('Reviewed requirements applied — recomputing physics');
  }

  const topologyMap = {
    'Triangle': {nodes:s=>[[0,0],[s,0],[s/2,0]], members:[[0,1],[0,2],[1,2]], load:2, supports:[[0,true,true],[1,false,true]]},
    'Fan': {nodes:s=>[[0,0],[s/2,0],[s,0],[s/2,0]], members:[[0,1],[1,2],[0,3],[2,3],[1,3]], load:3, supports:[[0,true,true],[2,false,true]]},
    'Warren-2': {nodes:s=>[[0,0],[s/2,0],[s,0],[s/4,0],[s/2,0],[3*s/4,0]],members:[[0,1],[1,2],[0,3],[3,1],[1,5],[5,2],[3,4],[4,5],[1,4]],load:4,supports:[[0,true,true],[2,false,true]]},
  };

  function previewTruss() {
    const {span_m:s, height_m:h, topology, base_load_n:F} = state.config;
    const t = topologyMap[topology];
    if (!t) return null;
    const raw = t.nodes(s).map((pt,i) => ({id:i, x_m:pt[0], y_m:(pt[1] || ((i === t.load || (topology==='Warren-2' && i>=3)) ? h : 0)),
      ux_mm:0,uy_mm:0,displacement_mm:0, load_y_n:i===t.load?-F:0, load_x_n:0,rx_n:0,ry_n:0,fix_x:false,fix_y:false}));
    // For Triangle, Fan and Warren-2 the applied load is always at top center.
    if (topology==='Triangle') raw[2].y_m=h;
    if (topology==='Fan') raw[3].y_m=h;
    t.supports.forEach(([id,fx,fy]) => {raw[id].fix_x=fx;raw[id].fix_y=fy;});
    return {nodes:raw, members:t.members.map(([a,b],id)=>({id,a,b,state:'neutral',force_n:0,stress_mpa:0,pcr_n:0,length_m:Math.hypot(raw[b].x_m-raw[a].x_m,raw[b].y_m-raw[a].y_m)})), span_m:s,height_m:h,load_n:F};
  }

  function model() {
    return (state.mode === 'challenge' && state.challenge?.challenged_analysis)
      || state.solve?.analysis || previewTruss();
  }

  function transform() {
    const w=Math.max(250,viewport.clientWidth), h=Math.max(200,viewport.clientHeight);
    const span=state.config.span_m, height=state.config.height_m;
    const marginX=w<600?48:105, marginY=h<370?65:105;
    const base=Math.max(15,Math.min((w-2*marginX)/span,(h-2*marginY)/height));
    const scale=base*state.zoom;
    const cx=w/2+state.panX, cy=h/2+state.panY;
    return {
      w,h,scale,
      xy:(x,y)=>({x:cx+(x-span/2)*scale, y:cy-(y-height/2)*scale}),
      inv:(sx,sy)=>({x:(sx-cx)/scale+span/2,y:(cy-sy)/scale+height/2}),
    };
  }

  function resetView() { state.zoom=1;state.panX=0;state.panY=0;renderScene(); }
  function changeZoom(factor, pos) {
    const before=transform(); const p=pos || {x:before.w/2,y:before.h/2};
    const a=before.inv(p.x,p.y);
    const next=clamp(state.zoom*factor,0.45,5);
    if (next===state.zoom) return;
    state.zoom=next;
    const after=transform(); const b=after.inv(p.x,p.y);
    state.panX += (a.x-b.x)*after.scale;
    state.panY -= (a.y-b.y)*after.scale;
    renderScene();
  }

  function pathLine(x1,y1,x2,y2,attr='') {
    return `<line x1="${x1.toFixed(2)}" y1="${y1.toFixed(2)}" x2="${x2.toFixed(2)}" y2="${y2.toFixed(2)}" ${attr}/>`;
  }

  function renderGrid(t) {
    if (!state.grid) return '';
    const sx=t.inv(0,0).x,ex=t.inv(t.w,0).x,sy=t.inv(0,t.h).y,ey=t.inv(0,0).y;
    const xMin=Math.min(sx,ex),xMax=Math.max(sx,ex),yMin=Math.min(sy,ey),yMax=Math.max(sy,ey);
    const step=t.scale<100?0.25:0.1;
    let lines='',labels='';
    const x0=Math.floor(xMin/step),x1=Math.ceil(xMax/step),y0=Math.floor(yMin/step),y1=Math.ceil(yMax/step);
    for(let i=x0;i<=x1 && i<x0+220;i++){
      const x=Number((i*step).toFixed(5)),px=t.xy(x,0).x;
      const major=Math.abs(x*2-Math.round(x*2))<.0001;
      lines+=pathLine(px,0,px,t.h,`stroke="${major?'#466175':'#2b4153'}" stroke-opacity="${major?.32:.19}" stroke-width="${major?1.1:.7}"`);
      if(major && Math.abs(x)<20){const origin=t.xy(0,0).y; if(origin>0&&origin<t.h-16) labels+=`<text x="${px+3}" y="${origin+17}" fill="#638395" font-size="9">${num(x,1)}</text>`;}
    }
    for(let i=y0;i<=y1 && i<y0+220;i++){
      const y=Number((i*step).toFixed(5)),py=t.xy(0,y).y;
      const major=Math.abs(y*2-Math.round(y*2))<.0001;
      lines+=pathLine(0,py,t.w,py,`stroke="${major?'#466175':'#2b4153'}" stroke-opacity="${major?.32:.19}" stroke-width="${major?1.1:.7}"`);
      if(major && Math.abs(y)>0.001){const origin=t.xy(0,0).x; if(origin>26&&origin<t.w-30) labels+=`<text x="${origin-8}" y="${py-4}" fill="#638395" text-anchor="end" font-size="9">${num(y,1)}</text>`;}
    }
    const origin=t.xy(0,0),xAxis=t.xy(1,0),yAxis=t.xy(0,1);
    lines+=pathLine(0,origin.y,t.w,origin.y,'stroke="#607f8e" stroke-width="1.3" stroke-opacity=".75"');
    lines+=pathLine(origin.x,0,origin.x,t.h,'stroke="#607f8e" stroke-width="1.3" stroke-opacity=".75"');
    // Axis arrowheads and coordinate orientation remain visible when model is panned.
    if(origin.y>-50&&origin.y<t.h+50) lines+=`<path d="M${t.w-15} ${origin.y-4}l8 4-8 4" stroke="#7ba7b3" fill="none" stroke-width="1.5"/><text x="${t.w-23}" y="${origin.y-11}" fill="#93bdc7" font-size="11" font-weight="700">X</text>`;
    if(origin.x>-40&&origin.x<t.w+40) lines+=`<path d="M${origin.x-4} 16l4-8 4 8" stroke="#7ba7b3" fill="none" stroke-width="1.5"/><text x="${origin.x+13}" y="20" fill="#93bdc7" font-size="11" font-weight="700">Y</text>`;
    return `<g aria-hidden="true">${lines}${labels}</g>`;
  }

  function displayNodes(data) {
    const k=state.showDeform?state.deformScale:0;
    return data.nodes.map(n=>({...n,px:n.x_m+(n.ux_mm||0)/1000*k,py:n.y_m+(n.uy_mm||0)/1000*k}));
  }

  function memberColor(m, data) {
    if(!state.solve) return '#6b9a9e';
    if(state.visual==='displacement'){
      const a=data.nodes[m.a],b=data.nodes[m.b];
      const d=Math.max(a.displacement_mm,b.displacement_mm)/state.config.max_displacement_mm;
      return d>.75?'#eeac75':d>.4?'#aedb91':'#5ddbc1';
    }
    return m.state==='compression'?'#f2a16b':m.state==='tension'?'#65ddd4':'#759eac';
  }

  function renderLegend() {
    const legend=$('.view-legend');
    legend.innerHTML=state.visual==='displacement'
      ? `<span><i class="legend-line tension"></i> Low disp.</span><span><i class="legend-line compression"></i> High disp.</span><span><i class="legend-line reference"></i> Undeformed</span>`
      : `<span><i class="legend-line tension"></i> Tension</span><span><i class="legend-line compression"></i> Compression</span><span><i class="legend-line reference"></i> Undeformed</span>`;
  }

  function renderScene() {
    const data=model(),t=transform();
    if(!data) return;
    const raw=data.nodes,drawn=displayNodes(data);
    let html=`<defs><filter id="glow"><feGaussianBlur stdDeviation="4"/></filter><marker id="arrowLoad" markerWidth="8" markerHeight="8" refX="5" refY="3" orient="auto"><path d="M0 0L6 3L0 6" fill="none" stroke="#e8b074" stroke-width="1.7"/></marker></defs>`;
    html+=renderGrid(t);
    let frame='',members='',labels='',supports='',nodes='';
    for(const m of data.members){
      const a=t.xy(raw[m.a].x_m,raw[m.a].y_m),b=t.xy(raw[m.b].x_m,raw[m.b].y_m);
      frame+=pathLine(a.x,a.y,b.x,b.y,'stroke="#6e8796" stroke-width="1.65" stroke-dasharray="5 5" stroke-opacity=".65"');
    }
    for(const m of data.members){
      const a=t.xy(drawn[m.a].px,drawn[m.a].py),b=t.xy(drawn[m.b].px,drawn[m.b].py);
      const color=memberColor(m,data);
      const selected=(state.selected?.type==='member'&&state.selected.id===m.id);
      const hovered=(state.hovered?.type==='member'&&state.hovered.id===m.id);
      const maxForce=Math.max(1,...data.members.map(x=>Math.abs(x.force_n||0)));
      const width=state.visual==='force'?3.4+3.5*Math.abs(m.force_n||0)/maxForce:4.5;
      if(selected||hovered) members+=pathLine(a.x,a.y,b.x,b.y,`stroke="#73e8d5" stroke-opacity=".17" stroke-width="18" filter="url(#glow)"`);
      members+=pathLine(a.x,a.y,b.x,b.y,`stroke="${color}" stroke-width="${selected?width+2:hovered?width+1:width}" stroke-linecap="round" opacity="${state.solve?1:.85}"`);
      if(selected){const midx=(a.x+b.x)/2,midy=(a.y+b.y)/2; labels+=`<rect x="${midx-23}" y="${midy-28}" width="46" height="17" rx="4" fill="#214345" stroke="#4ca79b"/><text x="${midx}" y="${midy-16}" font-size="10" text-anchor="middle" fill="#c3fbee" font-weight="800">M${String(m.id).padStart(2,'0')}</text>`;}
    }
    for(const n of raw){
      if(!n.fix_x&&!n.fix_y) continue;
      const p=t.xy(n.x_m,n.y_m);
      const sz=13;
      supports+=`<path d="M${p.x} ${p.y+4}l${-sz} ${sz}h${sz*2}Z" fill="#194b4d" stroke="#69c9bb" stroke-width="1.5"/>`;
      supports+=pathLine(p.x-sz-3,p.y+sz+4,p.x+sz+3,p.y+sz+4,'stroke="#649da1" stroke-width="1.5"');
      if(!n.fix_x) supports+=`<circle cx="${p.x-5}" cy="${p.y+sz+7}" r="2.2" fill="#8cbdba"/><circle cx="${p.x+5}" cy="${p.y+sz+7}" r="2.2" fill="#8cbdba"/>`;
    }
    for(const n of drawn){
      const p=t.xy(n.px,n.py), selected=(state.selected?.type==='node'&&state.selected.id===n.id),hovered=(state.hovered?.type==='node'&&state.hovered.id===n.id);
      if(selected||hovered) nodes+=`<circle cx="${p.x}" cy="${p.y}" r="13" fill="none" stroke="#78e8ce" opacity=".6" stroke-width="1.4"/>`;
      nodes+=`<circle cx="${p.x}" cy="${p.y}" r="5.2" fill="#112735" stroke="${selected?'#b7fff2':'#9adbd0'}" stroke-width="2"/>`;
      nodes+=`<text x="${p.x+9}" y="${p.y-11}" fill="#9cbac6" font-weight="700" font-size="10">N${n.id}</text>`;
    }
    const load=raw.find(n=>Math.abs(n.load_y_n||0)>0);
    if(load){
      const p=t.xy(load.x_m,load.y_m),arrowTop=p.y-78,arrowBot=p.y-18;
      labels+=pathLine(p.x,arrowTop,p.x,arrowBot,'stroke="#e5aa79" stroke-width="2.5" marker-end="url(#arrowLoad)"');
      labels+=`<rect x="${p.x-35}" y="${arrowTop-23}" width="70" height="18" rx="4" fill="#2d2829" stroke="#7b6058"/><text x="${p.x}" y="${arrowTop-10}" fill="#ffce9d" font-size="10" font-weight="750" text-anchor="middle">${num(Math.abs(load.load_y_n),0)} N</text>`;
    }
    // Persistent span and height dimensions, never attached to the exaggerated geometry.
    const left=t.xy(0,0),right=t.xy(data.span_m,0),top=t.xy(0,data.height_m);
    const dimY=left.y+54;
    if(dimY<t.h-18&&dimY>35){
      labels+=pathLine(left.x,dimY,right.x,dimY,'stroke="#507886" stroke-width="1"');
      labels+=pathLine(left.x,dimY-6,left.x,dimY+6,'stroke="#648c97" stroke-width="1.4"');
      labels+=pathLine(right.x,dimY-6,right.x,dimY+6,'stroke="#648c97" stroke-width="1.4"');
      labels+=`<text x="${(left.x+right.x)/2}" y="${dimY-7}" text-anchor="middle" fill="#7eabb5" font-size="10" font-weight="700">L = ${num(data.span_m,2)} m</text>`;
    }
    const dimX=left.x-42;
    if(dimX>20&&dimX<t.w-20){
      labels+=pathLine(dimX,left.y,dimX,top.y,'stroke="#507886" stroke-width="1"');
      labels+=pathLine(dimX-6,left.y,dimX+6,left.y,'stroke="#648c97" stroke-width="1.4"');
      labels+=pathLine(dimX-6,top.y,dimX+6,top.y,'stroke="#648c97" stroke-width="1.4"');
      labels+=`<text x="${dimX-10}" y="${(left.y+top.y)/2}" transform="rotate(-90 ${dimX-10} ${(left.y+top.y)/2})" text-anchor="middle" fill="#7eabb5" font-size="10" font-weight="700">H = ${num(data.height_m,2)} m</text>`;
    }
    html+=`<g>${frame}</g><g>${members}</g><g>${supports}</g><g>${nodes}</g><g>${labels}</g>`;
    svg.setAttribute('viewBox',`0 0 ${t.w} ${t.h}`);
    svg.innerHTML=html;
    $('#zoomLabel').textContent=`${num(state.zoom*100,0)}%`;
    $('#deformControl').classList.toggle('is-hidden',!state.showDeform);
    $('#deformText').textContent=`${state.deformScale}×`;
    renderLegend();
    const prior=$('.view-error',viewport);if(prior)prior.remove();
    if(state.error){const div=document.createElement('div');div.className='view-error';div.textContent=`Solver unavailable: ${state.error}. Start the Python web server to enable analysis.`;viewport.append(div);}
  }

  function nearestHit(sx,sy) {
    const data=model();if(!data) return null;
    const t=transform(),points=displayNodes(data).map(n=>t.xy(n.px,n.py));
    let best=null,dist=1e9;
    for(let i=0;i<points.length;i++){
      const d=Math.hypot(sx-points[i].x,sy-points[i].y);
      if(d<12&&d<dist){best={type:'node',id:i};dist=d;}
    }
    if(best)return best;
    for(const m of data.members){
      const a=points[m.a],b=points[m.b],vx=b.x-a.x,vy=b.y-a.y,denom=vx*vx+vy*vy;
      if(denom<1e-8)continue;
      const q=clamp(((sx-a.x)*vx+(sy-a.y)*vy)/denom,0,1);
      const d=Math.hypot(sx-(a.x+q*vx),sy-(a.y+q*vy));
      if(d<12&&d<dist){best={type:'member',id:m.id};dist=d;}
    }
    return best;
  }

  function tooltipHTML(hit) {
    const data=model();if(!data||!hit)return '';
    if(hit.type==='node'){
      const n=data.nodes[hit.id];if(!n)return '';
      return `<div class="tooltip-title">NODE N${n.id}</div><div class="tooltip-grid"><span>Position</span><strong>${num(n.x_m,3)}, ${num(n.y_m,3)} m</strong><span>Displacement</span><strong>${num(n.displacement_mm,4)} mm</strong><span>Ux / Uy</span><strong>${snum(n.ux_mm,4)} / ${snum(n.uy_mm,4)} mm</strong>${n.fix_x||n.fix_y?`<span>Reaction X / Y</span><strong>${snum(n.rx_n,1)} / ${snum(n.ry_n,1)} N</strong>`:''}</div><div class="tooltip-hint">Click to pin inspection</div>`;
    }
    const m=data.members[hit.id];if(!m)return '';
    return `<div class="tooltip-title">MEMBER M${String(m.id).padStart(2,'0')} · ${esc(m.state.toUpperCase())}</div><div class="tooltip-grid"><span>Length</span><strong>${num(m.length_m,3)} m</strong><span>Axial force</span><strong>${snum(m.force_n,2)} N</strong><span>Axial stress</span><strong>${snum(m.stress_mpa,3)} MPa</strong><span>Euler Pcr</span><strong>${num(m.pcr_n,1)} N</strong></div><div class="tooltip-hint">Click to pin inspection</div>`;
  }

  function updateTooltip(hit,x,y) {
    const tt=$('#hoverTooltip');
    if(!hit){tt.hidden=true;return;}
    tt.innerHTML=tooltipHTML(hit);
    tt.hidden=false;
    const width=tt.offsetWidth,height=tt.offsetHeight;
    tt.style.left=`${clamp(x+16,8,viewport.clientWidth-width-8)}px`;
    tt.style.top=`${clamp(y+16,8,viewport.clientHeight-height-8)}px`;
  }

  function renderMetrics() {
    const challenged = state.mode === 'challenge' && Boolean(state.challenge?.check);
    const a = challenged ? state.challenge.challenged_analysis : state.solve?.analysis;
    const r = challenged ? state.challenge.check : state.solve?.robust;
    $('#metricMass').textContent=num(a?.mass_kg,3);
    $('#metricDisp').textContent=num(a?.max_displacement_mm,4);
    $('#metricStress').textContent=num(a?.max_stress_mpa,3);
    $('#metricDispSub').textContent=challenged
      ? `${num(state.challengeMultiplier,2)}× load · Limit ${num(state.config.max_displacement_mm,2)} mm`
      : `Limit ${num(state.config.max_displacement_mm,2)} mm`;
    $('#metricMassSub').textContent=challenged?'Area-reduced scenario mass':a?`${a.members.length} axial members`:'Nominal design';
    $('#metricStatus').textContent=!r?'—':r.feasible?'PASS':'FAIL';
    $('#metricStatus').className=r?(r.feasible?'metric-pass':'metric-fail'):'';
    $('#metricStatusDot').className=`metric-status-dot ${r?(r.feasible?'passed':'failed'):''}`;
    $('#metricWorst').textContent=r?`${challenged?'Challenge':'Worst'} utilization ${num(r.worst_utilization,3)} / 1.000`:'8 corner scenarios';
  }

  function usage(label, value) {
    if(typeof value!=='number')return '';
    const kind=value>1?'fail':value>.8?'warn':'';
    const width=clamp(value*100,0,100);
    return `<div class="util-row"><div class="util-label"><span>${esc(label)}</span><b style="color:${value>1?'#f99c93':'#cbdfe2'}">${num(value,3)} / 1.000</b></div><div class="util-track"><div class="util-fill ${kind}" style="width:${width}%"></div></div></div>`;
  }

  function selectedCard() {
    const s=state.selected, a=state.solve?.analysis;
    if(!s || !a)return '';
    const entity=s.type==='node'?a.nodes[s.id]:a.members[s.id];
    if(!entity)return '';
    if(s.type==='node'){
      const n=entity;
      return `<div class="selected-card"><div class="selected-label">SELECTED / NODE</div><div class="selected-title">N${n.id} · ${n.fix_x?'Pinned support':n.fix_y?'Roller support':'Free node'}</div><div class="selected-grid"><span>X / Y</span><strong>${num(n.x_m,3)} / ${num(n.y_m,3)} m</strong><span>Displacement</span><strong>${num(n.displacement_mm,4)} mm</strong><span>Ux / Uy</span><strong>${snum(n.ux_mm,4)} / ${snum(n.uy_mm,4)} mm</strong>${n.fix_x||n.fix_y?`<span>Reaction X / Y</span><strong>${snum(n.rx_n,2)} / ${snum(n.ry_n,2)} N</strong>`:''}</div></div>`;
    }
    const m=entity;
    return `<div class="selected-card"><div class="selected-label">SELECTED / AXIAL MEMBER</div><div class="selected-title">M${String(m.id).padStart(2,'0')} · ${esc(m.state)}</div><div class="selected-grid"><span>Nodes</span><strong>N${m.a} → N${m.b}</strong><span>Length</span><strong>${num(m.length_m,3)} m</strong><span>Force</span><strong>${snum(m.force_n,2)} N</strong><span>Stress</span><strong>${snum(m.stress_mpa,3)} MPa</strong><span>Ideal Euler Pcr</span><strong>${num(m.pcr_n,1)} N</strong><span>Buckling utilization</span><strong>${num(m.buckling_util,3)}</strong></div></div>`;
  }

  function designPanel() {
    if(!state.solve){return `<div class="results-loading"><span class="loading-spinner"></span><div>${state.error?'Could not connect to the FEA backend':'Computing nominal FEA…'}</div></div>${state.error?`<div class="inline-message warning">${esc(state.error)}<br>Run <code>python web_server.py</code> from the repository root.</div>`:''}`;}
    const a=state.solve.analysis,r=state.solve.robust;
    const supportNodes=a.nodes.filter(n=>n.fix_x||n.fix_y);
    const maxUsage=r.worst_utilization;
    return `
      <div class="result-overline">SCENARIO SCREENING · 8 CORNERS</div>
      <div class="result-hero ${r.feasible?'':'failed'}"><div class="hero-top"><span class="dot-label">${r.feasible?'FEA VERIFIED':'CONSTRAINT EXCEEDED'}</span></div><div class="hero-state">${r.feasible?'PASS':'FAIL'}</div><div class="hero-sub">Worst-case utilization <b>${num(maxUsage,3)}</b> / 1.000<br>Material & geometric uncertainty included</div></div>
      ${selectedCard()}
      <div class="result-card"><div class="result-card-heading">Constraint utilization <small>≤ 1.0 = PASS</small></div>
        ${usage('Axial yield',r.worst_stress_util)}
        ${usage('Nodal displacement',r.worst_displacement_util)}
        ${usage('Euler buckling',r.worst_buckling_util)}
      </div>
      <div class="subtle-divider"></div>
      <div class="result-card"><div class="result-card-heading">Axial members <small>${a.members.length} elements</small></div>
      <table class="analysis-table"><thead><tr><th>ID</th><th>Force (N)</th><th>Stress (MPa)</th></tr></thead><tbody>
        ${a.members.map(m=>`<tr class="clickable ${state.selected?.type==='member'&&state.selected.id===m.id?'active':''}" data-action="select-member" data-member="${m.id}" title="Inspect M${m.id}"><td>M${String(m.id).padStart(2,'0')}</td><td style="color:${m.force_n<0?'#e6aa81':'#6adccd'}">${snum(m.force_n,1)}</td><td>${snum(m.stress_mpa,2)}</td></tr>`).join('')}
      </tbody></table></div>
      <div class="result-card"><div class="result-card-heading">Support reactions <small>ΣF ≈ 0</small></div><div class="compact-list">${supportNodes.map(n=>`<button class="compact-row button-row" data-action="select-node" data-node="${n.id}"><span>N${n.id} <span class="row-kind">${n.fix_x?'PIN':'ROLLER'}</span></span><strong>Ry ${snum(n.ry_n,2)} N</strong></button>`).join('')}</div><div class="section-note">Equilibrium residual: ${num(a.equilibrium_residual_n,7)} N</div></div>
      <button class="panel-button secondary" data-action="download-members">${ICON('download')} Export member results (CSV)</button>
      <div class="inline-message">Ideal pin-jointed members · point load at the top-center node · magnified deformation is visual only.</div>`;
  }

  function plotScatter(result) {
    const rows=result.candidates.filter(r=>r.mass_kg!=null&&r.worst_displacement_util!=null);
    if(!rows.length)return '';
    const minX=Math.min(...rows.map(r=>r.mass_kg)),maxX=Math.max(...rows.map(r=>r.mass_kg));
    const minY=0,maxY=Math.max(1.2,...rows.map(r=>r.worst_displacement_util));
    const X=x=>26+(x-minX)/(maxX-minX||1)*204;
    const Y=y=>130-(y-minY)/(maxY-minY||1)*110;
    let shapes=`<line x1="26" y1="20" x2="26" y2="130" stroke="#3c5666"/><line x1="26" y1="130" x2="236" y2="130" stroke="#3c5666"/>`;
    const limit=Y(1);
    shapes+=`<line x1="26" y1="${limit}" x2="236" y2="${limit}" stroke="#b18374" stroke-dasharray="4 4" stroke-width="1"/>`;
    for(const [i,r] of rows.entries()){
      const idx=result.candidates.indexOf(r),best=r===result.best;
      const fill=r.feasible?'#62d8c5':'#cf826d';
      shapes+=`<circle class="plot-dot" data-action="apply-search" data-index="${idx}" cx="${X(r.mass_kg).toFixed(1)}" cy="${Y(r.worst_displacement_util).toFixed(1)}" r="2.8" fill="${fill}" fill-opacity="${r.feasible?'.8':'.45'}"><title>${esc(r.topology)} · ${num(r.mass_kg,3)} kg · u=${num(r.worst_displacement_util,3)}</title></circle>`;
    }
    const best=result.best;
    if(best){shapes+=`<circle cx="${X(best.mass_kg)}" cy="${Y(best.worst_displacement_util)}" r="8" fill="none" stroke="#a9fae2" stroke-width="1.5" pointer-events="none"/>`;}
    return `<svg class="scatter-plot" viewBox="0 0 245 155" role="img" aria-label="Optimized candidate mass versus displacement utilization">${shapes}<text x="28" y="145" font-size="8" fill="#819baa">${num(minX,1)}</text><text x="234" y="145" text-anchor="end" font-size="8" fill="#819baa">${num(maxX,1)} kg</text><text x="2" y="23" font-size="8" fill="#819baa">u</text><text x="22" y="${limit-3}" text-anchor="end" font-size="8" fill="#bc9184">1.0</text></svg><div class="scatter-caption">Mass (kg) → · Displacement utilization ↑ · Click any point to load it</div>`;
  }

  function optimizePanel() {
    const data=state.search, busy=state.busy.has('search');
    const btn=`<button class="panel-button" data-action="search" ${busy?'disabled':''}>${busy?'<span class="loading-spinner"></span> Screening FEA candidates…':`${ICON('target')} Run robust optimization`}</button>`;
    if(!data)return `<div class="result-overline">ROBUST DESIGN SEARCH</div><div class="result-hero"><div class="hero-top"><span class="dot-label">SOLVER-DRIVEN</span></div><div class="hero-state">144 designs</div><div class="hero-sub">3 topologies × 6 heights × 8 section areas<br>8 uncertainty corner scenarios per design</div></div><div class="empty-state">${ICON('target')} Minimize nominal mass while satisfying displacement, yield and ideal buckling constraints.</div>${btn}<div class="section-note">Every candidate is checked using the Python finite-element solver. An optimal result means lowest mass within this discrete grid, not global CAD optimization.</div>`;
    const best=data.best;
    return `<div class="result-overline">ROBUST OPTIMIZATION · FEA VERIFIED</div>
      <div class="result-mini-metrics"><div class="mini-stat accent"><label>FEASIBLE</label><strong>${num(data.feasible_count,0)} <small>/ ${num(data.total_count,0)}</small></strong></div><div class="mini-stat"><label>PARETO DESIGNS</label><strong>${num(data.pareto.length,0)}</strong></div></div>
      ${best?`<div class="result-hero"><div class="hero-top"><span class="dot-label">LIGHTEST FEASIBLE</span></div><div class="hero-state">${num(best.mass_kg,3)} <span style="font-size:12px">kg</span></div><div class="hero-sub">${esc(best.topology)} · H ${num(best.height_m,2)} m · A ${num(best.area_mm2,0)} mm²<br>Worst utilization ${num(best.worst_utilization,3)} / 1.000</div></div><button class="panel-button" data-action="apply-best">${ICON('arrow')} Apply best design</button>`:'<div class="inline-message warning">No feasible design in the current search grid. Modify constraints or the loading envelope.</div>'}
      <div class="result-card"><div class="result-card-heading">Design trade space <small>${data.candidates.length} sampled</small></div>${plotScatter(data)}</div>
      <div class="result-card"><div class="result-card-heading">Lightest verified candidates</div><div class="compact-list">${data.candidates.filter(c=>c.feasible).slice(0,5).map(c=>`<button class="compact-row button-row" data-action="apply-search" data-index="${data.candidates.indexOf(c)}"><span><span class="row-rank">${esc(c.topology)}</span><br><span class="row-kind">H ${num(c.height_m,2)} · A ${num(c.area_mm2,0)}</span></span><strong>${num(c.mass_kg,3)} kg</strong></button>`).join('')||'<div class="section-note">No feasible designs.</div>'}</div></div>
      ${data.sensitivity.length?`<details class="advanced-block" style="margin:0 0 12px"><summary><span>Local sensitivity</span>${ICON('chevron')}</summary><div class="advanced-inner">${data.sensitivity.map(r=>`<div class="label-value"><span>${esc(r.Parameter.replace('_m','').replace('_mm2',''))} · ${esc(r.Output.replace('worst_',''))}</span><strong>${num(r['Local elasticity'],2)}</strong></div>`).join('')}</div></details>`:''}
      <button class="panel-button secondary" data-action="download-candidates">${ICON('download')} Export full FEA database</button>
      ${btn}<div class="section-note">Feasibility is specific to your current loads, material and idealized beam geometry.</div>`;
  }

  function challengePanel() {
    const c=state.challenge, busy=state.busy.has('challenge');
    const change=c?.redesign, r=c?.check, challenged=c?.challenged_analysis;
    return `<div class="result-overline">DESIGN STRESS TEST</div>
      <div class="result-hero"><div class="hero-top"><span class="dot-label">CHALLENGE MY DESIGN</span></div><div class="hero-state">${num(state.challengeMultiplier,2)}× <span style="font-size:12px">load</span></div><div class="hero-sub">Check expanded uncertainty against the design in the viewport.</div></div>
      <div class="panel-field"><label for="challengeRange">Applied load multiplier <output id="challengeText">${num(state.challengeMultiplier,2)}×</output></label><input id="challengeRange" type="range" min="1" max="1.6" step="0.05" value="${state.challengeMultiplier}"></div>
      <div class="label-value"><span>E reduction</span><strong>${pct(state.config.e_uncertainty)}%</strong></div><div class="label-value"><span>Area reduction</span><strong>${pct(state.config.area_uncertainty)}%</strong></div>
      <button class="panel-button" data-action="challenge" ${busy?'disabled':''}>${busy?'<span class="loading-spinner"></span> Checking…':`${ICON('flask')} Run FEA challenge`}</button>
      ${r?`<div class="subtle-divider"></div><div class="result-card"><div class="result-card-heading">Expanded scenario envelope</div><div class="result-mini-metrics"><div class="mini-stat"><label>PEAK DISPLACEMENT</label><strong>${num(challenged.max_displacement_mm,4)}</strong><small>mm</small></div><div class="mini-stat"><label>AXIAL STRESS</label><strong>${num(challenged.max_stress_mpa,3)}</strong><small>MPa</small></div></div>
      ${usage('Axial yield',r.worst_stress_util)}${usage('Displacement',r.worst_displacement_util)}${usage('Ideal buckling',r.worst_buckling_util)}
      <div class="inline-message ${r.feasible?'success':'warning'}"><b>${r.feasible?'PASS':'FAIL'}</b> — ${r.feasible?'the current design passes the expanded scenario set.':'one or more constraints fail under the expanded envelope.'} Worst utilization: ${num(r.worst_utilization,3)}.</div>
      <button class="panel-button secondary" data-action="redesign" ${busy?'disabled':''}>${ICON('refresh')} Find FEA-verified redesign</button></div>`:''}
      ${change?`<div class="subtle-divider"></div><div class="result-card"><div class="result-card-heading">Challenge redesign</div><div class="result-mini-metrics"><div class="mini-stat"><label>FEASIBLE</label><strong>${change.feasible_count} <small>/ ${change.total_count}</small></strong></div><div class="mini-stat"><label>MASS CHANGE</label><strong>${change.mass_change_pct==null?'—':snum(change.mass_change_pct,1)+'%'}</strong></div></div>${change.best?`<div class="selected-card"><div class="selected-label">REOPTIMIZED WITH FEA</div><div class="selected-title">${esc(change.best.topology)} · ${num(change.best.mass_kg,3)} kg</div><div class="selected-grid"><span>Height</span><strong>${num(change.best.height_m,3)} m</strong><span>Area</span><strong>${num(change.best.area_mm2,0)} mm²</strong><span>Worst utilization</span><strong>${num(change.best.worst_utilization,3)}</strong></div></div><button class="panel-button" data-action="apply-redesign">${ICON('arrow')} Load redesigned truss</button>`:'<div class="inline-message warning">No feasible candidate in the original discrete search space.</div>'}</div>`:''}
      <div class="section-note">All challenge metrics are recomputed from 8 finite-element scenarios; stress, displacement and Euler buckling must all pass.</div>`;
  }

  function mlPanel() {
    const data=state.ml, busy=state.busy.has('ml');
    return `<div class="result-overline">ML-ASSISTED DESIGN DISCOVERY</div><div class="result-hero"><div class="hero-top"><span class="dot-label">FEA → ML → FEA</span></div><div class="hero-state">Physics first</div><div class="hero-sub">Random Forest predicts utilization, then each shortlisted design is solved again by FEA.</div></div>
      ${!data?`<div class="empty-state">${ICON('brain')} Train on FEA-generated scenarios and verify the model's suggested designs.</div>`:''}
      <button class="panel-button" data-action="ml" ${busy?'disabled':''}>${busy?'<span class="loading-spinner"></span> Training & verifying…':`${ICON('brain')} Train and verify candidates`}</button>
      ${data?`<div class="subtle-divider"></div><div class="result-card"><div class="result-card-heading">Held-out validation <small>Group split</small></div><table class="analysis-table"><thead><tr><th>Target</th><th>MAE</th><th>R²</th></tr></thead><tbody>${Object.entries(data.metrics).map(([key,metric])=>`<tr><td>${esc(key.replace('worst_','').replace('_util',''))}</td><td>${num(metric.mae,3)}</td><td>${num(metric.r2,3)}</td></tr>`).join('')}</tbody></table><div class="section-note">Training-mean baseline MAE: ${Object.values(data.metrics).map(m=>num(m.baseline_mae,3)).join(' / ')}</div></div>
      <div class="result-card"><div class="result-card-heading">FEA-reverified proposals <small>${data.verified.length} designs</small></div><div class="compact-list">${data.verified.slice(0,7).map((r,i)=>`<button class="compact-row button-row" data-action="apply-ml" data-index="${i}" ${r.feasible?'':'title="Failed constraints"'}><span><span class="row-rank">${esc(r.topology)}</span><br><span class="row-kind">H ${num(r.height_m,2)} · A ${num(r.area_mm2,0)} mm²</span></span><span style="text-align:right"><strong>${num(r.mass_kg,3)} kg</strong><br><span class="small-badge ${r.feasible?'':'fail'}">${r.feasible?'PASS':'FAIL'}</span></span></button>`).join('')}</div></div>
      <div class="inline-message warning">${esc(data.note)} The holdout does not establish generalization to other topology families or materials.</div>`:''}`;
  }

  function agentPanel() {
    const parsed=state.parsed?.interpreted,busy=state.busy.has('agent');
    return `<div class="result-overline">REQUIREMENTS INTERPRETER</div><div class="result-hero"><div class="hero-top"><span class="dot-label">ENGINEER-IN-THE-LOOP</span></div><div class="hero-state">From brief to inputs</div><div class="hero-sub">Parse span, central force and deflection limit. Review all extracted values before use.</div></div>
      <div class="result-card"><div class="result-card-heading">Design brief</div><textarea class="result-textarea" id="briefInput" maxlength="1600" aria-label="Write a truss design brief">${esc(state.brief)}</textarea><label class="checkbox-line"><input id="useApiCheck" type="checkbox" ${state.useApi?'checked':''}> Use OpenAI API if configured on server</label>
      <button class="panel-button" data-action="interpret" ${busy?'disabled':''}>${busy?'<span class="loading-spinner"></span> Interpreting…':`${ICON('chat')} Interpret requirements`}</button></div>
      ${parsed?`<div class="selected-card"><div class="selected-label">PROPOSED VALUES · REVIEW REQUIRED</div><div class="selected-grid"><span>Span</span><strong>${num(parsed.span_m,3)} m</strong><span>Central load</span><strong>${num(parsed.load_n,0)} N</strong><span>Displacement limit</span><strong>${num(parsed.max_displacement_mm,3)} mm</strong></div></div><div class="section-note">${esc(parsed.rationale)}</div><button class="panel-button" data-action="apply-brief">${ICON('check')} Apply reviewed inputs</button>`:''}
      <div class="inline-message">The language model never calculates FEA values or declares a structure safe. The offline parser works without a key.</div>`;
  }

  function renderPanel() {
    // Background 2D FEA or ML requests may finish while the 3D study is open.
    // Do not try to render an unknown 2D inspector mode in that case.
    if (state.mode === 'solid3d') return;
    const titles={design:['PHYSICS SOLVER','Analysis results'],optimize:['DESIGN EXPLORER','Robust optimization'],challenge:['LOAD TESTING','Design challenge'],ml:['MACHINE LEARNING','ML surrogate'],agent:['NATURAL LANGUAGE','AI requirements']};
    const [eyebrow,title]=titles[state.mode];
    $('#resultEyebrow').textContent=eyebrow;
    $('#resultTitle').textContent=title;
    content.innerHTML=state.mode==='design'?designPanel():state.mode==='optimize'?optimizePanel():state.mode==='challenge'?challengePanel():state.mode==='ml'?mlPanel():agentPanel();
  }

  function csvEscape(value) {
    const text=value==null?'':String(value);
    return /[",\n\r]/.test(text)?`"${text.replaceAll('"','""')}"`:text;
  }
  function rowsCSV(rows) {
    if(!rows.length)return '';
    const keys=[...new Set(rows.flatMap(row=>Object.keys(row)))];
    return [keys.join(','),...rows.map(row=>keys.map(k=>csvEscape(row[k])).join(','))].join('\r\n');
  }
  function download(name, text, mime) {
    const url=URL.createObjectURL(new Blob([text], {type:mime}));
    const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),800);
  }

  function exportProject() {
    if(!state.solve){toast('Wait for a verified FEA result before exporting',true);return;}
    const payload={
      project:'ForceForge AI / Workspace II',
      method:'2D linear elastic axial truss FEA; ideal pin joints and Euler buckling screen',
      certification:false,
      config:{...state.config},
      nominal_fea:state.solve.analysis,
      uncertainty_screen:state.solve.robust,
      optimization:state.search?{feasible_count:state.search.feasible_count,total_count:state.search.total_count,best:state.search.best}:null,
      challenge:state.challenge,
      ml_validation:state.ml?{metrics:state.ml.metrics,validation:state.ml.validation}:null,
    };
    download('forceforge_workspace_study.json',JSON.stringify(payload,null,2),'application/json');
    toast('Engineering study exported as JSON');
  }

  content.addEventListener('click', event => {
    const target=event.target.closest('[data-action]');
    if(!target)return;
    const action=target.dataset.action;
    if(action==='search')runSearch();
    else if(action==='challenge')runChallenge(false);
    else if(action==='redesign')runChallenge(true);
    else if(action==='ml')runML();
    else if(action==='interpret')runAgent();
    else if(action==='apply-best')applyCandidate(state.search?.best);
    else if(action==='apply-redesign')applyCandidate(state.challenge?.redesign?.best);
    else if(action==='apply-brief')applyBrief();
    else if(action==='apply-search')applyCandidate(state.search?.candidates[Number(target.dataset.index)]);
    else if(action==='apply-ml')applyCandidate(state.ml?.verified[Number(target.dataset.index)]);
    else if(action==='select-member'||action==='select-node'){
      state.selected={type:action==='select-member'?'member':'node',id:Number(target.dataset.member??target.dataset.node)};
      renderScene();renderPanel();
    }
    else if(action==='download-members'){
      const rows=state.solve?.analysis.members||[];
      if(rows.length)download('forceforge_member_forces.csv',rowsCSV(rows),'text/csv');
    }
    else if(action==='download-candidates'){
      const rows=state.search?.candidates||[];
      if(rows.length)download('forceforge_verified_designs.csv',rowsCSV(rows),'text/csv');
    }
  });

  content.addEventListener('input',event=>{
    if(event.target.id==='challengeRange'){
      state.challengeMultiplier=Number(event.target.value);
      $('#challengeText').textContent=`${num(state.challengeMultiplier,2)}×`;
    } else if(event.target.id==='briefInput')state.brief=event.target.value;
    else if(event.target.id==='useApiCheck')state.useApi=event.target.checked;
  });
  content.addEventListener('change',event=>{
    if(event.target.id==='challengeRange'){
      state.challenge=null;renderPanel();renderMetrics();renderScene();
    }
  });

  $$('[data-panel]').forEach(b=>b.addEventListener('click',()=>setMode(b.dataset.panel)));
  $$('[data-topology]').forEach(b=>b.addEventListener('click',()=>updateConfig('topology',b.dataset.topology)));
  $$('[data-key]').forEach(input=>{
    const key=input.dataset.key;
    const update=e=>updateConfig(key,key==='material'?e.target.value:Number(e.target.value));
    input.addEventListener(input.type==='range'?'input':'change',update);
  });
  $$('[data-visual]').forEach(btn=>btn.addEventListener('click',()=>{
    state.visual=btn.dataset.visual;
    $$('[data-visual]').forEach(b=>b.classList.toggle('selected',b===btn));
    renderScene();
  }));
  $('#deformToggle').addEventListener('change',e=>{state.showDeform=e.target.checked;renderScene();});
  $('#deformScale').addEventListener('input',e=>{state.deformScale=Number(e.target.value);renderScene();});
  $('#zoomIn').addEventListener('click',()=>changeZoom(1.22));
  $('#zoomOut').addEventListener('click',()=>changeZoom(1/1.22));
  $('#fitView').addEventListener('click',resetView);
  $('#toggleGrid').addEventListener('click',()=>{state.grid=!state.grid;$('#toggleGrid').style.color=state.grid?'':'#58707c';renderScene();});
  $('#btnExport').addEventListener('click',exportProject);
  $('#btnHelp').addEventListener('click',()=>$('#helpDialog').showModal());
  $('#closeHelp').addEventListener('click',()=>$('#helpDialog').close());
  $('#mobileLeft').addEventListener('click',()=>{bodyShell.classList.toggle('show-left');bodyShell.classList.remove('show-right');});
  $('#mobileRight').addEventListener('click',()=>{bodyShell.classList.toggle('show-right');bodyShell.classList.remove('show-left');});

  let dragging=null;
  const coords=event=>{const rect=viewport.getBoundingClientRect();return {x:event.clientX-rect.left,y:event.clientY-rect.top};};
  svg.addEventListener('pointerdown',event=>{
    if(event.button!==0)return;
    dragging={x:event.clientX,y:event.clientY,panX:state.panX,panY:state.panY,moved:false};
    svg.setPointerCapture(event.pointerId);
  });
  svg.addEventListener('pointermove',event=>{
    const point=coords(event),world=transform().inv(point.x,point.y);
    $('#cursorX').textContent=num(world.x,3);
    $('#cursorY').textContent=num(world.y,3);
    if(dragging){
      const dx=event.clientX-dragging.x,dy=event.clientY-dragging.y;
      if(Math.abs(dx)+Math.abs(dy)>4)dragging.moved=true;
      if(dragging.moved){state.panX=dragging.panX+dx;state.panY=dragging.panY+dy;renderScene();$('#hoverTooltip').hidden=true;}
      return;
    }
    const hit=nearestHit(point.x,point.y);
    const old=state.hovered;
    if(old?.type!==hit?.type||old?.id!==hit?.id){state.hovered=hit;renderScene();}
    updateTooltip(hit,point.x,point.y);
  });
  svg.addEventListener('pointerup',event=>{
    if(!dragging)return;
    if(!dragging.moved){
      const point=coords(event),hit=nearestHit(point.x,point.y);
      state.selected=hit;
      renderScene();renderPanel();
      if(hit && window.matchMedia('(max-width:1050px)').matches)bodyShell.classList.add('show-right');
    }
    dragging=null;
    if(svg.hasPointerCapture(event.pointerId))svg.releasePointerCapture(event.pointerId);
  });
  svg.addEventListener('pointercancel',()=>{dragging=null;});
  svg.addEventListener('pointerleave',()=>{state.hovered=null;$('#hoverTooltip').hidden=true;renderScene();});
  viewport.addEventListener('wheel',event=>{
    event.preventDefault();
    changeZoom(event.deltaY>0?1/1.10:1.10,coords(event));
  },{passive:false});
  document.addEventListener('keydown',event=>{
    const typing=['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName);
    if(typing)return;
    if(event.key==='Escape'){
      state.selected=null;bodyShell.classList.remove('show-left','show-right');renderScene();renderPanel();
    }
    if(event.key==='f'||event.key==='F')resetView();
    if('123456'.includes(event.key)&&event.key.length===1){
      const modes=['design','optimize','challenge','ml','agent','solid3d'];setMode(modes[Number(event.key)-1]);
    }
  });
  new ResizeObserver(()=>renderScene()).observe(viewport);
  renderControls();renderMetrics();renderScene();renderPanel();
  // Match the initially highlighted Analyze tool with accessible state,
  // without opening the mobile results overlay on first load.
  $('[data-panel]').forEach(el => {
    el.setAttribute('aria-pressed', el.dataset.panel === 'design' ? 'true' : 'false');
  });
  if (window.location.hash === '#solid3d') setMode('solid3d');
  runSolve();
})();