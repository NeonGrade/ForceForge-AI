"use strict";
/* ForceForge X / Spatial Engineering v0.1.
   Mesh-driven 3D annotations, direct manipulation, progressive disclosure.
   Physics and evidence always come from the original Python solvers.
*/
const $=id=>document.getElementById(id);
const nf=(x,d=3)=>Number(x).toFixed(d);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const ui={
 workspace:"solid",data:null,request:0,redesign:null,calibration:null,
 selected:null,edit:null,dragging:null,viewMode:"material",pending:null,
 params:{
  solid:{workspace:"solid",force_n:200,thickness_mm:12,allowed_mm:.12,visual_scale:60,resolution:"refined"},
  lab:{workspace:"lab",view:"modes",log10_k:3,mode:1,amplitude_mm:28,tip_force_n:.3,static_scale:15,E_gpa:210,elements:32,gauges:true,density:7850}
 }
};
let view=null,usingGPU=false;
try{view=new window.ForgeViewport($("model-canvas"));usingGPU=true;}
catch(err){console.warn("WebGL2 unavailable; using accessible 2D placeholder",err);}

function notice(message,isError=false){
 const el=$("notification");el.textContent=message;el.style.borderColor=isError?"#f1a48f":"#8aaf9e";el.hidden=false;
 clearTimeout(notice.timer);notice.timer=setTimeout(()=>el.hidden=true,4800);
}
function setStatus(kind){
 $("solver-status").classList.toggle("solving",kind==="SOLVING");
 $("solver-status").classList.toggle("error",kind==="ERROR");
 $("solver-status-text").textContent=kind;
}
async function request(path,p){
 const r=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(p)});
 let v;try{v=await r.json();}catch{throw Error("Unexpected server response");}
 if(!r.ok)throw Error(v.error||"Solver request failed");
 return v;
}
function active(){return {...ui.params[ui.workspace]};}
function closePanels(){
 $("detail-panel").hidden=true;$("settings-panel").hidden=true;$("panel-backdrop").hidden=true;
}
function showPanel(id){
 closeEditor();closeQuick();
 $("detail-panel").hidden=id!=="detail-panel";$("settings-panel").hidden=id!=="settings-panel";
 $("panel-backdrop").hidden=false;
 if(id==="detail-panel")renderDetails();
 if(id==="settings-panel")syncSettings();
}
function closeEditor(){ui.edit=null;$("spatial-editor").hidden=true;document.querySelectorAll(".spatial-pin").forEach(x=>x.classList.remove("selected"));}
function closeQuick(){$("quick-result").hidden=true;}
function changeWorkspace(space){
 if(space!=="lab"&&space!=="solid")return;
 ui.workspace=space;ui.selected=null;ui.redesign=null;ui.calibration=null;ui.data=null;
 ui.request++;closePanels();closeEditor();closeQuick();$("project-chooser").hidden=true;
 const lab=space==="lab";
 $("scene-name").textContent=lab?"Real laboratory":"Solid mechanics";
 $("scene-kind").textContent=lab?"MEASURED MODAL REFERENCE":"TRUE 3D · COMPUTATIONAL";
 $("scene-sigil").textContent=lab?"∿":"◈";
 $("scene-sequence").textContent=lab?"02 / EXPERIMENTAL MODES":"01 / STRUCTURAL ANALYSIS";
 $("scene-headline").textContent=lab?"Observe the invisible.":"Shape the response.";
 $("scene-subline").textContent=lab?"Pick a mode. Compare what was measured.":"Choose a handle to shape the structure.";
 $("space-index").textContent=lab?"EXP / 002":"CAE / 001";
 $("footer-fidelity").textContent=lab?"2D BEAM FEA / PHYSICAL MODES":"3D TET10 / COMPUTED";
 $("field-legend").hidden=true;
 window.forceForgeViz="form";window.forceForgeSensors=true;
 if(view){view.selected=null;view.setTrueScale(false);view.reset();}
 $("pin-force").hidden=lab?ui.params.lab.view!=="static":false;
 $("pin-thickness").hidden=lab;
 $("pin-support").hidden=!lab;
 $("pin-mode").hidden=!lab||ui.params.lab.view==="static";
 $("pin-result").hidden=false;
 $("mode-view").firstChild.textContent="MATERIAL ";
 $("settings-panel").hidden=true;
 syncSettings();refreshPinText();solve();
}
function refreshPinText(){
 const p=ui.params.solid,l=ui.params.lab;
 $("force-readout").textContent=ui.workspace==="solid"?nf(p.force_n,0)+" N":nf(l.tip_force_n,2)+" N";
 $("thickness-readout").textContent=nf(p.thickness_mm,0)+" mm";
 $("support-readout").textContent="10^"+nf(l.log10_k,2)+" N·m/rad";
 $("mode-readout").textContent="B"+l.mode+"x";
 if(ui.data){
  $("result-caption").textContent=ui.workspace==="solid"?"TIP MOVEMENT · FEM":l.view==="static"?"TIP MOVEMENT · FEM":"COMPUTED / MEASURED";
  $("result-readout").textContent=ui.workspace==="solid"?nf(ui.data.tip_displacement_mm,4)+" mm":
    l.view==="static"?nf(ui.data.static_tip_mm,3)+" mm":
    nf(ui.data.frequencies_hz[l.mode-1],3)+" / "+nf(ui.data.measured_hz[l.mode-1],3)+" Hz";
 }
}
function pinAnchors(){
 if(!ui.data)return {};
 if(ui.workspace==="solid"){
  const thickness=ui.params.solid.thickness_mm;
  return {
   force:[0,-thickness/2,120],
   thickness:[15,0,54],
   result:[0,0,93]
  };
 }
 return {
  force:[0,0,1524],
  support:[0,0,0],
  mode:[0,0,1190],
  result:[0,0,690]
 };
}
const pinLayout={
 solid:{force:[100,-12],thickness:[-107,25],result:[95,85]},
 lab:{force:[113,-15],support:[-105,28],mode:[94,-12],result:[95,72]}
};
function layoutPins(){
 if(!ui.data||!view||!view.width||!view.height)return;
 const matrix=view.matrices(),anchors=pinAnchors(),out=[];
 const world=$("world"),width=world.clientWidth,height=world.clientHeight;
 for(const [name,point] of Object.entries(anchors)){
  const pin=$("pin-"+name);if(pin.hidden)continue;
  const p=view.projectRaw(point,matrix);if(!p)continue;
  let [dx,dy]=pinLayout[ui.workspace][name];
  let x=clamp(p.x+dx,85,width-105),y=clamp(p.y+dy,140,height-112);
  if(width<800)x=clamp(p.x+dx*.62,80,width-84);
  out.push({name,p,pin,x,y});
 }
 // Labels are placed near the model and nudged when they would overlap.
 out.sort((a,b)=>a.y-b.y);
 for(let i=1;i<out.length;i++){
  if(Math.abs(out[i].y-out[i-1].y)<57&&Math.abs(out[i].x-out[i-1].x)<135)
    out[i].y=Math.min(height-110,out[i-1].y+61);
 }
 const svg=$("world-leaders");svg.setAttribute("viewBox","0 0 "+width+" "+height);
 svg.replaceChildren();
 for(const item of out){
  const {pin,p,x,y,name}=item;
  pin.style.left=x+"px";pin.style.top=y+"px";pin.classList.add("is-positioned");
  const line=document.createElementNS("http://www.w3.org/2000/svg","path");
  const ex=x+(x>p.x?-30:30),ey=y;
  line.setAttribute("d","M"+p.x.toFixed(1)+" "+p.y.toFixed(1)+" L"+(p.x+(ex-p.x)*.5).toFixed(1)+" "+ey.toFixed(1)+" L"+ex.toFixed(1)+" "+ey.toFixed(1));
  line.setAttribute("fill","none");line.setAttribute("stroke",name==="result"?"#b6d9c7":"#d4efa2");
  line.setAttribute("stroke-width","1.15");line.setAttribute("opacity",".53");svg.appendChild(line);
  const marker=document.createElementNS("http://www.w3.org/2000/svg","circle");
  marker.setAttribute("cx",p.x);marker.setAttribute("cy",p.y);marker.setAttribute("r","3.4");
  marker.setAttribute("fill",name==="result"?"#b8e6dd":"#d6efa3");svg.appendChild(marker);
 }
}
function positionLoop(){
 layoutPins();window.requestAnimationFrame(positionLoop);
}
function fallbackGeometry(){
 // Explicitly labeled visual fallback; numeric metrics still come from Python.
 const c=$("model-canvas"),ctx=c.getContext("2d");
 if(!ctx)return;
 function draw(){
  const w=c.clientWidth,h=c.clientHeight,dpr=Math.min(2,window.devicePixelRatio||1);
  if(!w||!h)return;
  c.width=w*dpr;c.height=h*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);
  const bg=ctx.createRadialGradient(w*.55,h*.5,0,w*.55,h*.5,Math.max(w,h)*.65);
  bg.addColorStop(0,"#293e49");bg.addColorStop(1,"#0d1821");ctx.fillStyle=bg;ctx.fillRect(0,0,w,h);
  const cx=w*.5,cy=h*.57,len=Math.min(h*.52,350);
  ctx.fillStyle="#71999d";
  ctx.beginPath();ctx.moveTo(cx-29,cy-len*.58);ctx.lineTo(cx+10,cy-len*.61);ctx.lineTo(cx+30,cy+len*.54);ctx.lineTo(cx-15,cy+len*.58);ctx.closePath();ctx.fill();
  ctx.fillStyle="#e8f2df";ctx.font="700 12px sans-serif";ctx.fillText("SOFTWARE 3D RENDERER UNAVAILABLE",24,h-120);
 }
 window.addEventListener("resize",draw);draw();
}
let debounce;
function modified(){
 ui.calibration=null;ui.redesign=null;
 refreshPinText();
 setStatus("UPDATING");
 clearTimeout(debounce);debounce=setTimeout(solve,200);
}
async function solve(){
 const token=++ui.request,workspace=ui.workspace;
 setStatus("SOLVING");$("loading-veil").hidden=Boolean(ui.data);
 try{
  const d=await request("/api/solve",active());
  if(token!==ui.request||workspace!==ui.workspace)return;
  ui.data=d;
  if(view){view.load(d);view.draw();}
  $("loading-veil").hidden=true;setStatus("SOLVED");
  refreshPinText();renderDetails();refreshQuick();refreshLegend();
 }catch(e){
  if(token!==ui.request)return;
  $("loading-veil").hidden=true;setStatus("ERROR");notice("Model solve failed: "+e.message,true);
 }
}
function refreshLegend(){
 const hasStress=ui.workspace==="solid"&&ui.viewMode==="stress"&&ui.data;
 $("field-legend").hidden=!hasStress;
 if(hasStress)$("field-max").textContent=nf(ui.data.max_von_mises_mpa,2);
}
const editors={
 force:{title:"Applied tip force",symbol:"↘",key:"force_n",unit:"N",min:50,max:500,step:10,workspace:"solid"},
 thickness:{title:"Section thickness",symbol:"↔",key:"thickness_mm",unit:"mm",min:8,max:20,step:1,workspace:"solid"},
 support:{title:"Support rotational stiffness",symbol:"⟲",key:"log10_k",unit:"log₁₀ kθ",min:0,max:6,step:.05,workspace:"lab"},
 mode:{title:"Natural vibration",symbol:"∿",key:"mode",unit:"MODE",min:1,max:3,step:1,workspace:"lab"},
 labforce:{title:"Illustrative lateral load",symbol:"↘",key:"tip_force_n",unit:"N",min:.05,max:1,step:.05,workspace:"lab"}
};
function editorConfig(name){
 if(name==="force"&&ui.workspace==="lab")return editors.labforce;
 return editors[name];
}
function updateEditor(){
 const e=ui.edit;if(!e)return;
 const c=editorConfig(e),p=ui.params[c.workspace],v=Number(p[c.key]);
 $("editor-title").textContent=c.title;$("editor-symbol").textContent=c.symbol;
 $("editor-value").value=v;$("editor-value").min=c.min;$("editor-value").max=c.max;$("editor-value").step=c.step;
 $("editor-unit").textContent=c.unit;
 $("editor-range").min=c.min;$("editor-range").max=c.max;$("editor-range").step=c.step;$("editor-range").value=v;
 const mode=e==="mode";
 $("editor-options").hidden=!mode;$("editor-range").hidden=mode;
 $("editor-value").parentElement.parentElement.hidden=mode;
 $("editor-hint").textContent=mode?"Select a measured vibration mode.":"Drag the marker or adjust the value here.";
 document.querySelectorAll("[data-mode]").forEach(el=>el.classList.toggle("active",Number(el.dataset.mode)===v));
}
function showEditor(name){
 if(name==="result"){showQuick();return;}
 ui.edit=name;closeQuick();closePanels();
 document.querySelectorAll(".spatial-pin").forEach(el=>el.classList.toggle("selected",el.dataset.pin===name));
 $("spatial-editor").hidden=false;updateEditor();
}
function setEditValue(value){
 const e=ui.edit;if(!e)return;
 const c=editorConfig(e);if(!Number.isFinite(Number(value)))return;
 const v=clamp(Math.round(Number(value)/c.step)*c.step,c.min,c.max);
 ui.params[c.workspace][c.key]=Number(v.toFixed(5));
 updateEditor();modified();
}
function refreshQuick(){
 if($("quick-result").hidden||!ui.data)return;
 const d=ui.data,lab=ui.workspace==="lab",idx=ui.params.lab.mode-1;
 const isStatic=lab&&ui.params.lab.view==="static";
 $("quick-title").textContent=lab?(isStatic?"SIMULATED · LATERAL LOAD":"MEASURED / COMPUTED · MODE B"+(idx+1)):"CALCULATED TIP MOVEMENT";
 $("quick-value").textContent=lab?(isStatic?nf(d.static_tip_mm,3):nf(d.frequencies_hz[idx],3)):nf(d.tip_displacement_mm,4);
 $("quick-unit").textContent=lab&&!isStatic?"Hz":"mm";
 $("quick-minis").innerHTML=lab?
  isStatic?"<div>Applied force: <strong>"+nf(d.static_force_n,2)+" N</strong></div><div>Prediction only — not measured</div>":
  "<div>Measured: <strong>"+nf(d.measured_hz[idx],3)+" Hz</strong></div><div>Deviation: <strong>"+nf(d.error_percent[idx],2)+"%</strong></div>":
  "<div>Von Mises: <strong>"+nf(d.max_von_mises_mpa,2)+" MPa</strong></div><div>Target: <strong>"+nf(d.assumed_limit_mm,3)+" mm</strong> (assumed)</div>";
}
function showQuick(){if(!ui.data)return;closeEditor();$("quick-result").hidden=false;refreshQuick();}
function row(k,v){return "<div class='data-row'><span>"+esc(k)+"</span><strong>"+esc(v)+"</strong></div>";}
function block(title,body){return "<div class='detail-block'><h3>"+esc(title)+"</h3>"+body+"</div>";}
function renderDetails(){
 if(!ui.data)return;
 const d=ui.data,lab=ui.workspace==="lab";
 $("detail-title").textContent=lab?"Laboratory results":"Structural results";
 $("detail-kicker").textContent=lab?"PUBLISHED MODES / INDEPENDENT FEM":"TRUE 3D / TETRA10";
 let html="";
 if(!lab){
  html+=block("FINITE ELEMENT SOLUTION",
    row("Tip displacement",nf(d.tip_displacement_mm,4)+" mm")+
    row("Maximum sampled von Mises",nf(d.max_von_mises_mpa,2)+" MPa")+
    row("Mass",nf(d.mass_kg,4)+" kg")+
    row("Volume elements",String(d.element_count))+
    row("Beam reference",nf(d.theoretical_beam_tip_mm,4)+" mm"));
  html+=block("CURRENT MODEL",row("Tip force",nf(d.force_n,1)+" N")+
    row("Cross section","30 × "+nf(ui.params.solid.thickness_mm,0)+" mm")+
    row("Assumed limit",nf(d.assumed_limit_mm,3)+" mm")+
    row("Status",d.passes_assumed_limit?"Within modeled limits":"Limit exceeded"));
  if(ui.redesign){
   html+=block("RE-SOLVED THICKNESS CANDIDATES",
    ui.redesign.best?row("Lightest feasible",ui.redesign.best.thickness_mm+" mm")+
    row("Mass difference",nf(ui.redesign.best.mass_delta_percent,1)+"%"):
    "<p>No tested section meets both assumed limits.</p>");
  }
  html+="<div class='provenance'>Numerical 3D solid specimen, not a physically measured component. Applied load, material and displacement limit are assumptions. Clamp stress is mesh-sensitive. No certification implied.</div>";
 }else{
  if(d.view==="static"){
   html+=block("ILLUSTRATIVE STATIC FEA",
     row("Predicted tip displacement",nf(d.static_tip_mm,3)+" mm")+
     row("Assumed tip force",nf(d.static_force_n,2)+" N")+
     row("Model beam mass",nf(d.mass_kg,3)+" kg"));
   html+="<div class='provenance'>This loading was not part of the published measured modal dataset. The static result is a separate numerical prediction.</div>";
  }else{
   html+="<table class='data-table'><thead><tr><th>MODE</th><th>MEASURED</th><th>OUR FEA</th><th>ERROR</th></tr></thead><tbody>"+
     d.measured_hz.map((value,i)=>"<tr><td>B"+(i+1)+"x</td><td>"+nf(value,3)+" Hz</td><td>"+nf(d.frequencies_hz[i],3)+" Hz</td><td>"+nf(d.error_percent[i],2)+"%</td></tr>").join("")+"</tbody></table>";
   if(ui.calibration)html+=block("ONE-PARAMETER CALIBRATION",
     row("Fitted effective support kθ",nf(ui.calibration.k_nm_rad,2)+" N·m/rad")+
     row("Held-out Modes 2/3 MAPE",nf(ui.calibration.holdout_mape_percent,2)+"%"));
   html+=block("EXTERNAL REFERENCES",
     "<a href='"+esc(d.measurement_source)+"' target='_blank' rel='noopener noreferrer'>Peer-reviewed laboratory paper ↗</a><p></p>"+
     "<a href='"+esc(d.dataset_source)+"' target='_blank' rel='noopener noreferrer'>Original university dataset ↗</a>");
   html+="<div class='provenance'>Measured values are from published physical tests. Our reduced-order beam FEA and fitted support stiffness are separate numerical modeling assumptions. Frequency correlation does not certify structural safety.</div>";
  }
 }
 $("detail-content").innerHTML=html;
}
function syncSettings(){
 const p=ui.params.solid,l=ui.params.lab;
 $("solid-settings").hidden=ui.workspace!=="solid";$("lab-settings").hidden=ui.workspace!=="lab";
 $("setting-resolution").value=p.resolution;$("setting-limit").value=p.allowed_mm;
 $("setting-limit-value").textContent=nf(p.allowed_mm,3)+" mm";
 $("setting-visual").value=p.visual_scale;$("setting-visual-value").textContent=p.visual_scale+"×";
 $("setting-lab-view").value=l.view;$("setting-stiffness").value=l.log10_k;
 $("setting-stiffness-value").textContent=nf(l.log10_k,2);
 $("setting-amplitude").value=l.amplitude_mm;$("setting-amplitude-value").textContent=l.amplitude_mm+" mm";
 $("setting-elements").value=l.elements;$("setting-young").value=l.E_gpa;
 $("setting-gauges").checked=l.gauges;
 $("scientific-limit").textContent=ui.workspace==="solid"?
  "Numerical tetra10 volume FEM. Load, material and limits are assumed. Not safety-certified.":
  "Published modal measurements with an independent simplified beam FEM. No static experiment validation.";
}
async function runRedesign(){
 if(ui.workspace!=="solid")return;
 $("redesign-run").disabled=true;setStatus("SOLVING");
 const key=JSON.stringify(active());
 try{
  const r=await request("/api/redesign",active());
  if(ui.workspace!=="solid"||JSON.stringify(active())!==key)return;
  ui.redesign=r;renderDetails();showPanel("detail-panel");
  notice(r.best?"Best tested thickness: "+r.best.thickness_mm+" mm.":"No thickness meets the assumed criteria.");
 }catch(e){notice(e.message,true);}
 finally{$("redesign-run").disabled=false;setStatus("SOLVED");}
}
async function runCalibration(){
 if(ui.workspace!=="lab")return;
 if(ui.params.lab.view==="static"){
  ui.params.lab.view="modes";syncSettings();modified();notice("Returned to measured modal modes. Run calibration again.");return;
 }
 $("calibrate-run").disabled=true;setStatus("SOLVING");
 const key=JSON.stringify(active());
 try{
  const r=await request("/api/calibrate",active());
  if(ui.workspace!=="lab"||JSON.stringify(active())!==key)return;
  ui.calibration=r;ui.params.lab.log10_k=r.log10_k;syncSettings();
  await solve();showPanel("detail-panel");
  notice("Mode 1 fitted · held-out MAPE "+nf(r.holdout_mape_percent,2)+"%");
 }catch(e){notice(e.message,true);}
 finally{$("calibrate-run").disabled=false;}
}
function changeViz(){
 const next=ui.workspace==="solid"?
  ["form","stress","wire"]:[ "form","wire" ];
 const current=next.indexOf(ui.viewMode);
 ui.viewMode=next[(current+1)%next.length];
 window.forceForgeViz=ui.viewMode;
 $("mode-view").firstChild.textContent=(ui.viewMode==="stress"?"STRESS":ui.viewMode==="wire"?"MESH":"MATERIAL")+" ";
 if(view)view.draw();refreshLegend();
}
function bind(){
 $("scene-selector").onclick=e=>{e.stopPropagation();$("project-chooser").hidden=!$("project-chooser").hidden;};
 document.querySelectorAll("[data-workspace]").forEach(el=>el.onclick=()=>changeWorkspace(el.dataset.workspace));
 $("settings-open").onclick=()=>showPanel("settings-panel");
 $("details-open").onclick=()=>showPanel("detail-panel");
 $("help-open").onclick=()=>{
  $("detail-title").textContent="Explore the space.";
  $("detail-kicker").textContent="THREE THINGS TO KNOW";
  $("detail-content").innerHTML=block("MODEL CONTROLS",row("Rotate","Drag in space")+row("Zoom","Scroll")+row("Adjust","Select an on-model marker")+row("Reset camera","R key"))+
    "<div class='provenance'>Physical measurements and simulated values remain distinct. For complete sources, switch to the laboratory space and open Results.</div>";
  closeEditor();$("detail-panel").hidden=false;$("settings-panel").hidden=true;$("panel-backdrop").hidden=false;
 };
 $("view-reset").onclick=()=>view&&view.reset();
 document.querySelectorAll("[data-view]").forEach(el=>el.onclick=()=>{
  document.querySelectorAll("[data-view]").forEach(b=>b.classList.toggle("active",b===el));
  if(view)view.setView(el.dataset.view);
 });
 $("mode-view").onclick=changeViz;
 for(const name of ["force","thickness","support","mode","result"]){
  const pin=$("pin-"+name);
  pin.onclick=()=>{if(!ui.dragging)showEditor(name);ui.dragging=null;};
  if(name==="result"||name==="mode")continue;
  let start=null;
  pin.addEventListener("pointerdown",e=>{
   if(e.button!==0)return;start={x:e.clientX,value:ui.params[editorConfig(name).workspace][editorConfig(name).key],moved:false};
  });
  pin.addEventListener("pointermove",e=>{
   if(!start)return;
   const dx=e.clientX-start.x;if(Math.abs(dx)<7&&!start.moved)return;
   start.moved=true;ui.dragging=true;
   const c=editorConfig(name),range=c.max-c.min;
   const value=clamp(start.value+dx/230*range,c.min,c.max);
   ui.edit=name;
   const step=c.step;
   ui.params[c.workspace][c.key]=Number((Math.round(value/step)*step).toFixed(5));
   refreshPinText();modified();
  });
  pin.addEventListener("pointerup",()=>{start=null;setTimeout(()=>ui.dragging=null,0);});
  pin.addEventListener("pointercancel",()=>{start=null;ui.dragging=null;});
 }
 $("editor-close").onclick=closeEditor;$("quick-close").onclick=closeQuick;
 $("quick-action").onclick=()=>showPanel("detail-panel");
 $("editor-minus").onclick=()=>{const c=editorConfig(ui.edit);setEditValue(Number(ui.params[c.workspace][c.key])-c.step);};
 $("editor-plus").onclick=()=>{const c=editorConfig(ui.edit);setEditValue(Number(ui.params[c.workspace][c.key])+c.step);};
 $("editor-range").oninput=e=>setEditValue(Number(e.target.value));
 $("editor-value").onchange=e=>setEditValue(Number(e.target.value));
 document.querySelectorAll("[data-mode]").forEach(el=>el.onclick=()=>setEditValue(Number(el.dataset.mode)));
 $("panel-backdrop").onclick=closePanels;$("detail-close").onclick=closePanels;$("settings-close").onclick=closePanels;
 $("setting-resolution").onchange=e=>{ui.params.solid.resolution=e.target.value;modified();};
 $("setting-limit").oninput=e=>{ui.params.solid.allowed_mm=Number(e.target.value);syncSettings();modified();};
 $("setting-visual").oninput=e=>{ui.params.solid.visual_scale=Number(e.target.value);syncSettings();modified();};
 $("setting-lab-view").onchange=e=>{
  ui.params.lab.view=e.target.value;
  $("pin-force").hidden=e.target.value!=="static";
  $("pin-mode").hidden=e.target.value==="static";
  modified();
 };
 $("setting-stiffness").oninput=e=>{ui.params.lab.log10_k=Number(e.target.value);syncSettings();modified();};
 $("setting-amplitude").oninput=e=>{ui.params.lab.amplitude_mm=Number(e.target.value);syncSettings();modified();};
 $("setting-elements").onchange=e=>{ui.params.lab.elements=Number(e.target.value);modified();};
 $("setting-young").onchange=e=>{ui.params.lab.E_gpa=Number(e.target.value);modified();};
 $("setting-gauges").onchange=e=>{ui.params.lab.gauges=e.target.checked;modified();};
 $("setting-true-scale").onchange=e=>{if(view)view.setTrueScale(e.target.checked);notice(e.target.checked?"True beam section proportions.":"Section expanded ×24 for inspection only.");};
 $("redesign-run").onclick=runRedesign;$("calibrate-run").onclick=runCalibration;
 $("dismiss-guide").onclick=()=>{$("first-use").hidden=true;};
 $("world").addEventListener("pointerdown",e=>{
  if(e.target.id==="model-canvas"){closeEditor();closeQuick();$("project-chooser").hidden=true;}
 });
 document.addEventListener("keydown",e=>{
  if(e.key==="Escape"){closePanels();closeEditor();closeQuick();$("project-chooser").hidden=true;}
  if(["INPUT","SELECT","TEXTAREA"].includes(document.activeElement.tagName))return;
  if(e.key.toLowerCase()==="r"&&view)view.reset();
 });
 if(view){
  view.onSelect=s=>{
   if(s&&s.type==="sensor"){
    ui.selected=s;
    $("quick-result").hidden=false;
    $("quick-title").textContent=s.id+" · MEASUREMENT POINT";
    $("quick-value").textContent=nf(s.height_mm,0);
    $("quick-unit").textContent="mm";
    $("quick-minis").innerHTML="<div>"+esc(s.type==="sensor"?(s.id==="MP4"||s.id==="MP5"?"Strain gauge":"Motion measurement"):"Measured point")+"</div><div>Published sensor elevation above base</div>";
  }
  };
 }
}
bind();refreshPinText();changeWorkspace("solid");
if(!usingGPU){fallbackGeometry();$("loading-veil").hidden=true;}
else window.requestAnimationFrame(positionLoop);
