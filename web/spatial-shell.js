/* ForceForge X / Spatial Workspace shell for the physics-verified 2D truss UI.
   Pure presentation and input routing: no fabricated forces or FEM values. */
(() => {
  'use strict';
  const api = window.ForceForge2D;
  if (!api) { console.error('ForceForge 2D interface not initialized'); return; }
  const $ = id => document.getElementById(id);
  const shell = document.querySelector('.body-shell');
  const viewport = $('viewport');
  const menu = $('sceneMenu');
  const selector = $('sceneSelector');
  const backdrop = $('drawerBackdrop');
  const editor = $('modelEditor');
  const values = {
    base_load_n: {label:'Applied force',glyph:'↓',unit:'N'},
    area_mm2: {label:'Member section area',glyph:'↔',unit:'mm²'}
  };
  let editing = null;
  let currentAnchor = null;
  const clamp = (x,a,b) => Math.max(a,Math.min(x,b));
  const number = (x,d=0) => Number(x).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
  const panelsOpen = () => shell.classList.contains('show-left') || shell.classList.contains('show-right');

  function updatePanelState() {
    const open=panelsOpen();
    backdrop.hidden=!open;
    $('mobileLeft').setAttribute('aria-expanded',String(shell.classList.contains('show-left')));
    $('mobileRight').setAttribute('aria-expanded',String(shell.classList.contains('show-right')));
    if(open)closeEditor();
  }
  function closePanels() { shell.classList.remove('show-left','show-right'); }
  new MutationObserver(updatePanelState).observe(shell,{attributes:true,attributeFilter:['class']});
  document.querySelectorAll('[data-close-panel]').forEach(button => button.addEventListener('click',closePanels));
  backdrop.addEventListener('click',closePanels);
  // A workspace action opens the relevant sheet; the structure remains visible behind it.
  document.querySelector('.tool-rail').addEventListener('click',e => {
    const target=e.target.closest('[data-panel]');if(!target)return;
    if(target.dataset.panel==='design')closePanels();
    else {shell.classList.remove('show-left');shell.classList.add('show-right');}
    closeEditor();closeMenu();
  });
  // The workspace is a product surface, not the future product home page.
  // Both real solvers remain isolated under one origin and in one browser tab.
  const studioFrame = $('integratedStudioFrame');
  const backTo2D = $('return2D');
  const studioSwitch = $('open3d');
  const transition = $('workspaceTransition');
  const retry3D = $('retry3D');
  const cancel3D = $('cancel3DLoading');
  const appShell = $('appShell');
  let studioLoaded = false;
  let studioFramePromise = null;
  let studioSwitching = false;
  let activeRequest = 0;
  let preflightController = null;

  function closeMenu() {
    menu.hidden = true;
    selector.setAttribute('aria-expanded', 'false');
  }
  selector.addEventListener('click', e => {
    e.stopPropagation();
    menu.hidden = !menu.hidden;
    selector.setAttribute('aria-expanded', String(!menu.hidden));
  });
  $('open2d').addEventListener('click', () => {
    closeMenu(); api.setMode('design'); closePanels();
    selector.focus({preventScroll:true});
  });

  function routeSpace() {
    return new URLSearchParams(window.location.search).get('space') === '3d' ? '3d' : '2d';
  }
  function updateRoute(space, replace = false) {
    const dest = new URL(window.location.href);
    dest.pathname = '/workspace/';
    if (space === '3d') dest.searchParams.set('space', '3d');
    else dest.searchParams.delete('space');
    const next = dest.pathname + dest.search + dest.hash;
    if (next === window.location.pathname + window.location.search + window.location.hash) return;
    window.history[replace ? 'replaceState' : 'pushState']({space}, '', next);
  }
  function showTransition(kind, title, message) {
    transition.hidden = false;
    transition.dataset.state = kind;
    transition.setAttribute('role', kind === 'error' ? 'alert' : 'status');
    $('transitionTitle').textContent = title;
    $('transitionMessage').textContent = message;
    $('transitionSymbol').textContent = kind === 'error' ? '!' : '⬡';
    retry3D.hidden = kind !== 'error';
    cancel3D.textContent = kind === 'error' ? 'Back to 2D' : 'Stay in 2D';
  }
  function hideTransition() {
    transition.hidden = true;
    retry3D.hidden = true;
  }
  function closeStudio({history = true, focus = true} = {}) {
    ++activeRequest; // A late 3D preflight or iframe load may not reopen the scene.
    if (preflightController) preflightController.abort();
    preflightController = null;
    closeMenu(); hideTransition();
    document.body.classList.remove('in-3d-workspace');
    studioFrame.hidden = true; studioFrame.setAttribute('aria-hidden', 'true');
    appShell.inert = false; appShell.removeAttribute('aria-hidden');
    backTo2D.hidden = true;
    studioSwitching = false; studioSwitch.disabled = false;
    if (history) updateRoute('2d');
    if (focus) selector.focus({preventScroll:true});
  }

  function addTrussChoiceToStudio() {
    // The integrated iframe is same-origin. Its original engineering controls,
    // WebGL viewport, and material/CAD methods are kept intact.
    const doc = studioFrame.contentDocument;
    if (!doc) return;
    const chooser = doc.getElementById('project-chooser');
    if (!chooser || doc.getElementById('integrated-truss-choice')) return;
    const choice = doc.createElement('button');
    choice.type = 'button';
    choice.id = 'integrated-truss-choice';
    choice.className = 'project-choice';
    choice.setAttribute('aria-label', 'Switch to 2D truss engineering');
    const icon = doc.createElement('span');
    icon.className = 'project-icon'; icon.textContent = '◈';
    const copy = doc.createElement('span');
    const title = doc.createElement('strong'); title.textContent = 'Truss engineering';
    const sub = doc.createElement('small'); sub.textContent = '2D FEA / Robust design';
    copy.append(title, sub);
    const arrow = doc.createElement('span');
    arrow.className = 'project-arrow'; arrow.textContent = '↗';
    choice.append(icon, copy, arrow);
    choice.addEventListener('click', () => closeStudio());
    const kicker = chooser.querySelector('.sheet-kicker');
    if (kicker && kicker.nextSibling) chooser.insertBefore(choice, kicker.nextSibling);
    else chooser.appendChild(choice);
  }

  function ensureStudioFrame() {
    if (studioLoaded && studioFrame.contentDocument?.getElementById('model-canvas')) {
      return Promise.resolve();
    }
    if (studioFramePromise) return studioFramePromise;
    studioFramePromise = new Promise((resolve, reject) => {
      let settled = false;
      const finish = error => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        studioFrame.removeEventListener('load', onLoad);
        studioFramePromise = null;
        if (error) reject(error);
        else resolve();
      };
      const onLoad = () => {
        try {
          const doc = studioFrame.contentDocument;
          if (!doc || !doc.getElementById('model-canvas') || !doc.getElementById('project-chooser')) {
            return finish(new Error('The 3D interface did not load correctly. Check Studio assets.'));
          }
          addTrussChoiceToStudio();
          studioLoaded = true;
          finish(null);
        } catch (error) {finish(error);}
      };
      const timeout = setTimeout(() => {
        finish(new Error('3D viewport loading timed out. You can retry without losing 2D inputs.'));
      }, 16000);
      studioFrame.addEventListener('load', onLoad);
      studioFrame.hidden = false;
      studioFrame.removeAttribute('aria-hidden');
      studioFrame.src = '/studio/';
    });
    return studioFramePromise;
  }

  async function openStudio({history = true} = {}) {
    if (studioSwitching) return;
    const current = ++activeRequest;
    studioSwitching = true; studioSwitch.disabled = true;
    closeMenu(); closePanels(); closeEditor();
    showTransition('loading', 'Opening 3D Spatial Studio', 'Connecting the original 3D FEA and CAD tools.');
    try {
      const controller = new AbortController();
      preflightController = controller;
      const timeout = setTimeout(() => controller.abort(), 8500);
      let response;
      try {response = await fetch('/api/3d/catalog', {cache:'no-store', signal:controller.signal});}
      finally {clearTimeout(timeout);}
      if (current !== activeRequest) return;
      if (!response.ok) throw new Error('3D modules are not installed in this checkout. Use the unified integration branch.');
      const catalogue = await response.json();
      if (!Array.isArray(catalogue.modules) || !['solid','cad','lab'].every(id =>
            catalogue.modules.some(m => m.id === id))) {
        throw new Error('The 3D catalogue is incomplete. Check your installed project files.');
      }
      $('transitionMessage').textContent = 'Preparing the WebGL workspace and engineering overlays.';
      await ensureStudioFrame();
      if (current !== activeRequest) return;
      hideTransition();
      studioFrame.hidden = false; studioFrame.removeAttribute('aria-hidden');
      appShell.inert = true; appShell.setAttribute('aria-hidden', 'true');
      document.body.classList.add('in-3d-workspace');
      backTo2D.hidden = false;
      if (history) updateRoute('3d');
      backTo2D.focus({preventScroll:true});
    } catch (error) {
      if (current !== activeRequest) return;
      studioFrame.hidden = true; studioFrame.setAttribute('aria-hidden', 'true');
      studioLoaded = false;
      const message = error.name === 'AbortError'
        ? 'The local 3D server did not respond in time. Check the terminal and retry.'
        : (error.message || '3D Studio could not be opened.');
      showTransition('error', '3D workspace unavailable', message);
    } finally {
      if (current === activeRequest) {
        studioSwitching = false;
        studioSwitch.disabled = false;
        preflightController = null;
      }
    }
  }
  studioSwitch.addEventListener('click', () => openStudio());
  backTo2D.addEventListener('click', () => closeStudio());
  cancel3D.addEventListener('click', () => closeStudio());
  retry3D.addEventListener('click', () => openStudio());
  window.addEventListener('popstate', () => {
    if (routeSpace() === '3d') openStudio({history:false});
    else closeStudio({history:false,focus:false});
  });
  const initialSpace = routeSpace();
  updateRoute(initialSpace, true);
  if (initialSpace === '3d') openStudio({history:false});
  // Readiness is passive: it never starts an expensive CAD or FE solve.
  fetch('/api/workspace', {cache:'no-store'}).then(r => r.ok ? r.json() : null).then(info => {
    if (info && info.spaces?.['3d']?.available === false) {
      $('studioAvailability').textContent = '3D modules missing in this checkout';
    }
  }).catch(() => {});
  document.addEventListener('pointerdown',e => {
    if(!menu.hidden&&!menu.contains(e.target)&&!selector.contains(e.target))closeMenu();
    if(!editor.hidden&&!editor.contains(e.target)&&!e.target.closest('.model-pin'))closeEditor();
  });
  document.addEventListener('keydown',e=>{
    if(e.key==='Escape') {if(!transition.hidden) closeStudio(); else {closeMenu();closePanels();closeEditor();}}
  });
  $('dismissGesture').addEventListener('click',()=>{$('gestureGuide').hidden=true;});

  function pinPlacement(el,x,y,transform) {
    const width=transform.w,height=transform.h;
    const small=width<760;
    const pad=small?76:105;
    if(height<430&&el.id==='spatialPinArea'){el.classList.remove('is-positioned');return;}
    el.style.left=clamp(x,pad,width-pad)+'px';
    el.style.top=clamp(y,small?228:110,height-(small?243:165))+'px';
    el.classList.add('is-positioned');
  }
  function sync() {
    const state=api.state(),data=api.model(),t=api.transform();
    if(!data||!data.nodes||!t)return;
    const raw=data.nodes;
    const load=raw.find(node=>Math.abs(node.load_y_n||0)>0);
    const loadPt=load?t.xy(load.x_m,load.y_m):{x:t.w*.5,y:t.h*.45};
    const midPt=t.xy(data.span_m/2,0);
    const mobile=t.w<760;
    pinPlacement($('spatialPinLoad'),loadPt.x+(mobile?102:125),loadPt.y-(mobile?72:75),t);
    pinPlacement($('spatialPinArea'),midPt.x-(mobile?0:150),midPt.y+(mobile?70:58),t);
    pinPlacement($('spatialPinResult'),loadPt.x+(mobile?-100:198),loadPt.y+(mobile?92:94),t);
    $('spatialLoadValue').textContent=number(state.config.base_load_n)+' N';
    $('spatialAreaValue').textContent=number(state.config.area_mm2)+' mm²';
    const disp=(state.mode==='challenge'?state.challenge?.challenged_analysis?.max_displacement_mm:undefined)
      ??state.solve?.analysis?.max_displacement_mm;
    $('spatialResultValue').textContent=Number.isFinite(disp)?number(disp,4)+' mm':'— mm';
    if(editing&&editor.hidden===false){
      const key=editing,parameter=values[key];
      if(parameter&&document.activeElement!==$('modelEditorValue'))$('modelEditorValue').value=String(state.config[key]);
      if(document.activeElement!==$('modelEditorRange'))$('modelEditorRange').value=String(state.config[key]);
    }
  }
  // renderScene rewrites the SVG whenever the solver, camera, or hover changes.
  // A MutationObserver allows on-model controls to follow the exact FEA geometry
  // without modifying the existing numerical calculation or screen projection.
  const svg=$('sceneSvg');
  new MutationObserver(sync).observe(svg,{childList:true,attributes:true,attributeFilter:['viewBox']});
  new ResizeObserver(sync).observe(viewport);

  function closeEditor() {
    editing=null;currentAnchor=null;editor.hidden=true;
    document.querySelectorAll('.model-pin').forEach(pin=>pin.classList.remove('selected'));
  }
  function openEditor(key,pin) {
    const info=values[key],source=document.querySelector(`[data-key="${key}"]`);
    if(!info||!source)return;
    if(panelsOpen())closePanels();
    editing=key;currentAnchor=pin;
    $('modelEditorGlyph').textContent=info.glyph;
    $('modelEditorTitle').textContent=info.label;
    $('modelEditorUnit').textContent=info.unit;
    const range=$('modelEditorRange'),numeric=$('modelEditorValue');
    range.min=source.min;range.max=source.max;range.step=source.step;
    numeric.min=source.min;numeric.max=source.max;numeric.step=source.step;
    range.value=api.state().config[key];numeric.value=api.state().config[key];
    editor.hidden=false;
    document.querySelectorAll('.model-pin').forEach(p=>p.classList.toggle('selected',p===pin));
    const t=api.transform(),rect=pin.getBoundingClientRect(),viewRect=viewport.getBoundingClientRect();
    editor.style.left=clamp(rect.right-viewRect.left+16,12,t.w-294)+'px';
    editor.style.top=clamp(rect.top-viewRect.top-34,84,t.h-273)+'px';
  }
  function updateEdited(raw) {
    if(!editing)return;
    const source=document.querySelector(`[data-key="${editing}"]`);
    const n=Number(raw);if(!Number.isFinite(n))return;
    const value=clamp(n,Number(source.min),Number(source.max));
    api.updateConfig(editing,Math.round(value/Number(source.step))*Number(source.step));
    $('modelEditorRange').value=String(api.state().config[editing]);
    $('modelEditorValue').value=String(api.state().config[editing]);
  }
  $('modelEditorClose').addEventListener('click',closeEditor);
  $('modelEditorRange').addEventListener('input',e=>updateEdited(e.target.value));
  $('modelEditorValue').addEventListener('change',e=>updateEdited(e.target.value));
  $('modelEditorMinus').addEventListener('click',()=>{const key=editing;if(!key)return;const input=document.querySelector(`[data-key="${key}"]`);updateEdited(api.state().config[key]-Number(input.step));});
  $('modelEditorPlus').addEventListener('click',()=>{const key=editing;if(!key)return;const input=document.querySelector(`[data-key="${key}"]`);updateEdited(api.state().config[key]+Number(input.step));});
  Object.keys(values).forEach(key=>{
    const pin=document.querySelector(`[data-pin-key="${key}"]`);
    let drag=null;
    pin.addEventListener('pointerdown',event=>{
      if(event.button!==0)return;
      drag={x:event.clientX,start:api.state().config[key],moved:false};
      try{pin.setPointerCapture(event.pointerId);}catch{}
    });
    pin.addEventListener('pointermove',event=>{
      if(!drag)return;
      const delta=event.clientX-drag.x;
      if(Math.abs(delta)>7)drag.moved=true;
      if(!drag.moved)return;
      const step=Number(document.querySelector(`[data-key="${key}"]`).step);
      const increment=key==='base_load_n'?Math.round(delta/10)*step:Math.round(delta/12)*step;
      const input=document.querySelector(`[data-key="${key}"]`);
      const next=clamp(drag.start+increment,Number(input.min),Number(input.max));
      api.updateConfig(key,next);
    });
    pin.addEventListener('pointerup',event=>{
      if(!drag)return;
      if(!drag.moved)openEditor(key,pin);
      drag=null;
      try{pin.releasePointerCapture(event.pointerId);}catch{}
    });
    pin.addEventListener('pointercancel',()=>{drag=null;});
    pin.addEventListener('click',event=>{if(event.detail===0)openEditor(key,pin);});
  });
  $('spatialPinResult').addEventListener('click',()=>{
    closeEditor();closeMenu();shell.classList.remove('show-left');shell.classList.add('show-right');
  });
  // Selecting a real member or node reveals its computed force/displacement.
  svg.addEventListener('pointerup',()=>{
    if(api.state().selected){closeEditor();shell.classList.remove('show-left');shell.classList.add('show-right');}
  });
  sync();updatePanelState();
})();
