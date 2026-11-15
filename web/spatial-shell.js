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
  // Both spatial workspaces are served by the same Python backend and local origin.
  function closeMenu() {menu.hidden=true;selector.setAttribute('aria-expanded','false');}
  selector.addEventListener('click',e => {e.stopPropagation();menu.hidden=!menu.hidden;selector.setAttribute('aria-expanded',String(!menu.hidden));});
  $('open2d').addEventListener('click',()=>{closeMenu();api.setMode('design');closePanels();});
  const studioFrame = $('integratedStudioFrame');
  const backTo2D = $('return2D');
  const studioSwitch = $('open3d');
  let studioStarted = false;
  let studioSwitching = false;

  function closeStudio() {
    closeMenu();
    document.body.classList.remove('in-3d-workspace');
    studioFrame.hidden = true;
    backTo2D.hidden = true;
    studioSwitching = false;
    studioSwitch.disabled = false;
  }
  function addTrussChoiceToStudio() {
    // Same-origin iframe: add a real 2D entry to the existing 3D scene selector.
    // The original 3D scene choices and its WebGL canvas remain untouched.
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
    icon.className = 'project-icon';
    icon.textContent = '◈';
    const copy = doc.createElement('span');
    const title = doc.createElement('strong');
    title.textContent = 'Truss engineering';
    const sub = doc.createElement('small');
    sub.textContent = '2D FEA · Robust design';
    copy.append(title, sub);
    const arrow = doc.createElement('span');
    arrow.className = 'project-arrow';
    arrow.textContent = '↗';
    choice.append(icon, copy, arrow);
    choice.addEventListener('click', closeStudio);
    const kicker = chooser.querySelector('.sheet-kicker');
    if (kicker && kicker.nextSibling) chooser.insertBefore(choice, kicker.nextSibling);
    else chooser.appendChild(choice);
  }
  studioFrame.addEventListener('load', () => {
    try { addTrussChoiceToStudio(); }
    catch (err) { console.warn('Could not add 2D choice to embedded 3D selector', err); }
  });
  async function openStudio() {
    if (studioSwitching) return;
    studioSwitching = true;
    studioSwitch.disabled = true;
    closeMenu(); closePanels(); closeEditor();
    try {
      // Do not display a missing 3D pane when only the legacy 2D branch is installed.
      const response = await fetch('/api/3d/catalog', {cache:'no-store'});
      if (!response.ok) throw new Error('3D components are not available in this checkout.');
      const catalogue = await response.json();
      if (!Array.isArray(catalogue.modules)) throw new Error('Invalid 3D Studio catalogue.');
      if (!studioStarted) {
        studioFrame.src = '/studio/';
        studioStarted = true;
      }
      studioFrame.hidden = false;
      backTo2D.hidden = false;
      document.body.classList.add('in-3d-workspace');
    } catch(err) {
      const toast = $('toast');
      toast.textContent = err.message || '3D Studio could not be opened';
      toast.classList.add('show', 'error');
      setTimeout(() => toast.classList.remove('show', 'error'), 5000);
    } finally {
      studioSwitching = false;
      studioSwitch.disabled = false;
    }
  }
  studioSwitch.addEventListener('click', openStudio);
  backTo2D.addEventListener('click', closeStudio);
  document.addEventListener('pointerdown',e => {
    if(!menu.hidden&&!menu.contains(e.target)&&!selector.contains(e.target))closeMenu();
    if(!editor.hidden&&!editor.contains(e.target)&&!e.target.closest('.model-pin'))closeEditor();
  });
  document.addEventListener('keydown',e=>{
    if(e.key==='Escape') {closeMenu();closePanels();closeEditor();}
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
