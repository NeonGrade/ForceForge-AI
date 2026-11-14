"use strict";
const $=id=>document.getElementById(id);
const state={
 workspace:"solid",viz:"stress",sensors:true,data:null,redesign:null,calibration:null,requestId:0,drawer:"overview",
 params:{
  solid:{workspace:"solid",force_n:200,thickness_mm:12,allowed_mm:.12,visual_scale:60,resolution:"refined"},
  lab:{workspace:"lab",log10_k:3,mode:1,view:"modes",amplitude_mm:28,tip_force_n:.30,static_scale:15,E_gpa:210,elements:32,gauges:true,density:7850}
 }
};
const clamp=(x,a,b)=>Math.min(b,Math.max(a,x));
const fmt=(n,d=3)=>Number(n).toFixed(d);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function text(id,s){$(id).textContent=s;}
function visible(id,v){$(id).hidden=!v;}
function status(s){text("analysis-status",s);text("control-status",s);}
function notify(msg){const el=$("toast");el.textContent=msg;el.hidden=false;clearTimeout(notify.t);notify.t=setTimeout(()=>el.hidden=true,4800);}
async function api(path,data){
 const r=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
 const result=await r.json();
 if(!r.ok)throw Error(result.error||"Request failed");
 return result;
}
class Renderer{
 constructor(canvas){
  this.canvas=canvas;this.ctx=canvas.getContext("2d",{alpha:false});this.yaw=-.57;this.pitch=.33;this.zoom=1;
  this.points=[];this.faces=[];this.values=null;this.sensors=[];this.center=[0,0,0];this.extent=120;this.max=1;
  this.w=0;this.h=0;this.drag=false;this.last=[0,0];
  canvas.addEventListener("pointerdown",e=>{this.drag=true;this.last=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);});
  canvas.addEventListener("pointermove",e=>{if(!this.drag)return;this.yaw+=(e.clientX-this.last[0])*.007;this.pitch=clamp(this.pitch+(e.clientY-this.last[1])*.006,-1.35,1.35);this.last=[e.clientX,e.clientY];this.draw();});
  ["pointerup","pointercancel"].forEach(name=>canvas.addEventListener(name,()=>{this.drag=false;}));
  canvas.addEventListener("wheel",e=>{e.preventDefault();this.zoom=clamp(this.zoom*Math.exp(e.deltaY*.001),.55,3.5);this.draw();},{passive:false});
  if(window.ResizeObserver)new ResizeObserver(()=>this.resize()).observe(canvas);
  window.addEventListener("resize",()=>this.resize());
 }
 reset(){this.yaw=-.57;this.pitch=.33;this.zoom=1;this.draw();}
 load(d){
  this.points=d.mesh.vertices;this.faces=d.mesh.faces;this.values=d.mesh.scalar;this.sensors=d.sensors||[];
  this.max=d.stress_cmax_mpa||1;
  const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
  for(const p of this.points){for(let j=0;j<3;j++){lo[j]=Math.min(lo[j],p[j]);hi[j]=Math.max(hi[j],p[j]);}}
  this.center=lo.map((v,j)=>(v+hi[j])/2);
  this.extent=Math.max(1,...lo.map((v,j)=>hi[j]-v));
  this.resize();
 }
 resize(){
  const w=this.canvas.clientWidth,h=this.canvas.clientHeight;if(!w||!h)return;
  const dpr=Math.min(2,window.devicePixelRatio||1);
  this.w=w;this.h=h;
  this.canvas.width=Math.floor(w*dpr);this.canvas.height=Math.floor(h*dpr);
  this.ctx.setTransform(dpr,0,0,dpr,0,0);this.draw();
 }
 project(v){
  const x=(v[0]-this.center[0])/this.extent,y=(v[1]-this.center[1])/this.extent,z=(v[2]-this.center[2])/this.extent;
  const cy=Math.cos(this.yaw),sy=Math.sin(this.yaw),cp=Math.cos(this.pitch),sp=Math.sin(this.pitch);
  const xx=x*cy-y*sy,yy=x*sy+y*cy,up=z*cp-yy*sp,depth=z*sp+yy*cp;
  const scale=Math.min(this.w*.75,this.h*.78)/this.zoom;
  return {x:this.w*.5+xx*scale,y:this.h*.57-up*scale,d:depth};
 }
 color(t){
  const stops=[[66,124,157],[68,176,179],[150,212,144],[232,198,103],[222,128,91],[188,74,90]];
  const u=clamp(t,0,1)*(stops.length-1),i=Math.min(stops.length-2,Math.floor(u));
  return stops[i].map((n,j)=>Math.round(n*(1-(u-i))+stops[i+1][j]*(u-i)));
 }
 draw(){
  if(!this.w||!this.h)return;
  const c=this.ctx,w=this.w,h=this.h;c.fillStyle="#152330";c.fillRect(0,0,w,h);
  const g=c.createRadialGradient(w*.51,h*.45,10,w*.51,h*.45,Math.max(w,h)*.75);
  g.addColorStop(0,"#2a3d4a");g.addColorStop(.5,"#1b2c3b");g.addColorStop(1,"#101b28");c.fillStyle=g;c.fillRect(0,0,w,h);
  c.strokeStyle="#98b5c51a";c.lineWidth=.8;
  for(let k=-7;k<=7;k++){
   const n=k*this.extent*.17,z=this.center[2]-this.extent*.57;
   const a=this.project([this.center[0]-this.extent*1.4,this.center[1]+n,z]);
   const b=this.project([this.center[0]+this.extent*1.4,this.center[1]+n,z]);
   const d=this.project([this.center[0]+n,this.center[1]-this.extent*1.4,z]);
   const e=this.project([this.center[0]+n,this.center[1]+this.extent*1.4,z]);
   c.beginPath();c.moveTo(a.x,a.y);c.lineTo(b.x,b.y);c.moveTo(d.x,d.y);c.lineTo(e.x,e.y);c.stroke();
  }
  if(!this.points.length)return;
  const projected=this.points.map(p=>this.project(p)),polys=[];
  for(let i=0;i<Math.min(this.faces.length,25000);i++){
   const ids=this.faces[i],a=projected[ids[0]],b=projected[ids[1]],d=projected[ids[2]];
   if(!a||!b||!d)continue;
   const area=(b.x-a.x)*(d.y-a.y)-(b.y-a.y)*(d.x-a.x);if(Math.abs(area)<.03)continue;
   const p=this.points[ids[0]],q=this.points[ids[1]],r=this.points[ids[2]];
   const ux=q[0]-p[0],uy=q[1]-p[1],uz=q[2]-p[2],vx=r[0]-p[0],vy=r[1]-p[1],vz=r[2]-p[2];
   const nx=uy*vz-uz*vy,ny=uz*vx-ux*vz,nz=ux*vy-uy*vx;
   const magnitude=Math.hypot(nx,ny,nz)||1;
   const shade=clamp(.73+.26*(nx*.23+ny*.55+nz*.72)/magnitude,.4,1);
   const base=state.viz==="form"?[138,170,173]:state.workspace==="lab"?[116,170,168]:this.color(this.values?this.values[i]/this.max:0);
   polys.push({a,b,d,depth:(a.d+b.d+d.d)/3,color:base.map(v=>Math.round(v*shade))});
  }
  polys.sort((a,b)=>a.depth-b.depth);
  c.lineJoin="round";
  for(const p of polys){
   c.beginPath();c.moveTo(p.a.x,p.a.y);c.lineTo(p.b.x,p.b.y);c.lineTo(p.d.x,p.d.y);c.closePath();
   if(state.viz==="wire"){c.fillStyle="rgba(109,151,159,.12)";c.strokeStyle="rgba(173,216,212,.48)";c.lineWidth=.7;}
   else{c.fillStyle="rgb("+p.color.join(",")+")";c.strokeStyle="rgba("+p.color.join(",")+",.14)";c.lineWidth=.4;}
   c.fill();c.stroke();
  }
  if(state.workspace==="lab"&&state.sensors){
   c.font="700 10px sans-serif";c.textBaseline="middle";
   for(const sensor of this.sensors){
    const p=this.project(sensor.position);c.fillStyle="#d9f28c";c.beginPath();c.arc(p.x,p.y,4,0,Math.PI*2);c.fill();
    c.strokeStyle="#a0c7a2";c.beginPath();c.moveTo(p.x+6,p.y);c.lineTo(p.x+23,p.y-9);c.stroke();c.fillStyle="#dde9dc";c.fillText(sensor.id,p.x+27,p.y-10);
   }
  }
 }
}
let view,usingGPU=false;
try{
 view=new window.ForgeViewport($("model-canvas"));usingGPU=true;
}catch(error){
 console.warn("WebGL unavailable, using interactive canvas fallback",error);
 view=new Renderer($("model-canvas"));
}
window.forceForgeViz="stress";window.forceForgeSensors=true;
text("render-mode-status",usingGPU?"WEBGL2 / LIVE FE GEOMETRY":"CANVAS COMPATIBILITY MODE");
function setSceneSelection(selection){
 const d=state.data;if(!d)return;
 const sensor=selection&&selection.type==="sensor";
 const lab=state.workspace==="lab";
 text("intel-index",sensor?"EXPERIMENT / "+selection.id:lab?"SOURCE / MEASURED SPECIMEN":"SOLVER / VOLUMETRIC GEOMETRY");
 text("intel-title",sensor?selection.id+" · MEASUREMENT POINT":lab?"PHYSICAL STEEL SPECIMEN":"TETRA10 · SOLID MESH");
 text("intel-body",sensor?fmt(selection.height_mm,0)+" mm above the clamp · "+(selection.id==="MP4"||selection.id==="MP5"?"strain gauge":"motion measurement"):
  lab?"1,524 mm free length · published experimental modal reference · 5 measurement locations.":"120 × 30 mm computational solid · parameterized thickness · actual 3D FEA.");
 if(sensor){text("intel-action","VIEW MEASUREMENT DETAILS ↗");}
 else text("intel-action",lab?"REVIEW PUBLISHED EVIDENCE ↗":"EXPLORE MODEL PARAMETERS ↗");
}
if(usingGPU){
 view.onSelect=selection=>{
  setSceneSelection(selection);
  document.querySelectorAll(".tree-node").forEach(el=>el.classList.remove("selected"));
  $("tree-model").classList.add("selected");
  if(selection&&selection.type==="sensor"){
   text("inspector-intro",selection.id+" · "+fmt(selection.height_mm,0)+" mm above the base");
  }
 };
}
function updateSceneControls(){
 const lab=state.workspace==="lab";
 visible("true-scale",lab);
 visible("toggle-sensors",lab);
 document.querySelectorAll('[data-viz="stress"]').forEach(el=>el.hidden=lab);
 text("form-viz-label",lab?"Mode shape":"Material");
 text("mesh-viz-label",lab?"Geometry":"FE mesh");
 window.forceForgeViz=state.viz;
 text("tree-model-label",lab?"Hannover steel beam":"Solid cantilever");
 text("scene-index",lab?"EXP-002 / REAL LAB DATA":"CAE-001 / VOLUME ELEMENTS");
 $("tree-solver").innerHTML=lab?'<span class="tree-icon">▥</span> Reduced-order beam FEM':'<span class="tree-icon">▥</span> Tetra10 volume mesh';
 $("tree-measurements").innerHTML=lab?'<span class="tree-icon">◎</span> Measured sensors':'<span class="tree-icon">◎</span> Calculated fields';
 setSceneSelection(null);
}
function updateLabels(){
 const p=state.params.solid,l=state.params.lab;
 text("solid-force-value",p.force_n+" N");text("solid-thickness-value",p.thickness_mm+" mm");
 text("solid-limit-value",fmt(p.allowed_mm,3)+" mm");text("solid-visual-value",p.visual_scale+"×");
 text("lab-mode-value","B"+l.mode+"x");text("lab-stiffness-value","10^"+fmt(l.log10_k,2)+" N·m/rad");
 text("lab-amplitude-value",l.amplitude_mm+" mm");text("lab-force-value",fmt(l.tip_force_n,2)+" N");
 $("lab-mode").disabled=l.view==="static";$("lab-amplitude").disabled=l.view==="static";$("lab-force").disabled=l.view!=="static";
}
function selectWorkspace(workspace){
 state.workspace=workspace;state.viz=workspace==="solid"?"stress":"form";state.data=null;state.redesign=null;state.calibration=null;
 state.requestId++;visible("module-menu",false);updateSceneControls();
 document.querySelectorAll("[data-workspace]").forEach(el=>el.classList.toggle("is-active",el.dataset.workspace===workspace));
 document.querySelectorAll("[data-viz]").forEach(el=>el.classList.toggle("selected",el.dataset.viz===state.viz));
 visible("solid-controls",workspace==="solid");visible("lab-controls",workspace==="lab");
 text("header-project",workspace==="solid"?"SOLID MECHANICS":"REAL LABORATORY");
 text("module-name",workspace==="solid"?"Solid mechanics":"Real laboratory");
 text("module-subname",workspace==="solid"?"3D VOLUMETRIC FEA":"EXPERIMENTAL MODAL STUDY");
 text("module-icon",workspace==="solid"?"◈":"◇");
 text("stage-overline",workspace==="solid"?"STRUCTURAL SIMULATION / 01":"EXPERIMENTAL VALIDATION / 02");
 text("stage-title",workspace==="solid"?"Form meets force.":"What makes a model real?");
 text("stage-description",workspace==="solid"?"A solid structure, solved in three dimensions. Explore how loads become displacement and stress.":"A measured laboratory specimen. Explore the gap between prediction and physical observation.");
 text("viewport-type",workspace==="solid"?"3D TETRAHEDRAL FEA":"PUBLISHED EXPERIMENT");
 text("viewport-model-name",workspace==="solid"?"PARAMETRIC CANTILEVER":"HANNOVER STEEL BEAM");
 text("inspector-intro",workspace==="solid"?"Numbers behind the geometry.":"Measured evidence, computed predictions.");
 updateLabels();view.reset();setDrawer(false);solve();
}
function setControls(open){$("control-panel").classList.toggle("collapsed",!open);$("rail-controls").classList.toggle("tool-is-active",open);$("rail-controls").setAttribute("aria-expanded",String(open));setTimeout(()=>view.resize(),310);}
function setDrawer(open){$("bottom-drawer").classList.toggle("open",open);$("drawer-toggle").setAttribute("aria-expanded",String(open));text("drawer-toggle-label",open?"COLLAPSE DETAILS":"EXPAND DETAILS");setTimeout(()=>view.resize(),310);}
function drawerTab(tab){state.drawer=tab;document.querySelectorAll("[data-drawer-tab]").forEach(e=>e.classList.toggle("active",e.dataset.drawerTab===tab));renderDrawer();}
let pending;
function changed(){state.redesign=null;state.calibration=null;updateLabels();status("UPDATING");clearTimeout(pending);pending=setTimeout(solve,220);}
async function solve(){
 const req=++state.requestId,workspace=state.workspace,payload={...state.params[workspace]};
 status("SOLVING");$("primary-action").disabled=true;if(!state.data)visible("viewport-placeholder",true);
 try{
  const d=await api("/api/solve",payload);
  if(req!==state.requestId)return;
  state.data=d;view.load(d);renderInspector();renderDrawer();renderLegend();setSceneSelection(null);
  status("SOLVED");visible("viewport-placeholder",false);
 }catch(e){if(req!==state.requestId)return;status("SOLVER ERROR");visible("viewport-placeholder",false);notify("Solver error: "+e.message);}
 finally{if(req===state.requestId)$("primary-action").disabled=false;}
}
function renderLegend(){
 const d=state.data;if(!d)return;
 const show=state.workspace==="solid"&&state.viz==="stress";
 $("spectrum-scale").parentElement.classList.toggle("no-scale",!show);
 text("scale-name",show?"VON MISES · MAX GAUSS SAMPLE":"MATERIAL");
 text("scale-high",show?fmt(d.stress_cmax_mpa,2)+" MPa":"");
 text("visual-disclaimer",d.visual_deformation.toUpperCase());
 text("model-fidelity",state.workspace==="solid"?"3D TET10 / ASSUMED LOAD":"2D BEAM FEM / PUBLISHED MODES");
}
function renderInspector(){
 const d=state.data;if(!d)return;
 if(state.workspace==="solid"){
  text("primary-metric-title","TIP DISPLACEMENT");text("primary-metric-value",fmt(d.tip_displacement_mm,4));text("primary-metric-unit","mm");
  text("primary-metric-foot","3D quadratic volume FE calculation");text("secondary-a-title","VON MISES · MAX");text("secondary-a-value",fmt(d.max_von_mises_mpa,2)+" MPa");
  text("secondary-b-title","SOLID MASS");text("secondary-b-value",fmt(d.mass_kg,3)+" kg");
  text("comparison-heading","CURRENT PERFORMANCE");text("comparison-badge","SIMULATED");
  text("meter-title","Assumed movement target");
  const r=d.tip_displacement_mm/d.assumed_limit_mm;
  text("meter-value",fmt(r*100,1)+"%");$("meter-bar").style.width=clamp(r*100,0,100)+"%";$("meter-bar").classList.toggle("over",r>1);
  text("meter-foot",d.passes_assumed_limit?"Within modeled limits. Not safety certification.":"Modeled limit exceeded. Explore alternatives.");
  visible("mode-comparisons",false);text("primary-action-label","Explore design alternatives");
  text("action-footnote","Nine independently solved 3D mesh candidates.");
  text("inspector-source","Original computed specimen. No measured static deflection or certified material properties.");
 }else{
  const i=d.mode-1,e=d.error_percent[i];text("primary-metric-title","COMPUTED MODE B"+d.mode+"x");text("primary-metric-value",fmt(d.frequencies_hz[i],3));text("primary-metric-unit","Hz");
  text("primary-metric-foot","Physical measurement: "+fmt(d.measured_hz[i],3)+" Hz; signed error "+fmt(e,2)+"%");
  text("secondary-a-title","OBSERVED MODE 1");text("secondary-a-value",fmt(d.measured_hz[0],3)+" Hz");
  text("secondary-b-title","COMPUTED BEAM MASS");text("secondary-b-value",fmt(d.mass_kg,3)+" kg");
  text("comparison-heading","PHYSICAL / COMPUTED");text("comparison-badge","MEASURED");
  text("meter-title","Selected mode error");text("meter-value",fmt(e,2)+"%");
  $("meter-bar").style.width=clamp(Math.abs(e)*4,0,100)+"%";$("meter-bar").classList.toggle("over",Math.abs(e)>10);
  text("meter-foot","Frequency correlation only, not design certification.");
  $("mode-comparisons").innerHTML=d.frequencies_hz.map((f,j)=>"<div class='mode-row'><span>B"+(j+1)+"x · lab / FEM</span><b>"+fmt(d.measured_hz[j],3)+" / "+fmt(f,3)+" Hz</b></div>").join("");
  visible("mode-comparisons",true);text("primary-action-label","Calibrate using measured Mode 1");
  text("action-footnote","Fit one parameter; hold Modes 2 and 3 out.");
  text("inspector-source","Only modal values are published measurements; the material and fixture model parameters are assumed.");
 }
}
function cards(items){return "<div class='drawer-grid'>"+items.map(x=>"<div class='drawer-card'><h3>"+x[0]+"</h3>"+x[1]+"</div>").join("")+"</div>";}
function renderDrawer(){
 const d=state.data;if(!d)return;
 const solid=state.workspace==="solid",el=$("drawer-body");
 if(state.drawer==="overview"){
  el.innerHTML=solid?cards([
   ["True volumetric physics","<div class='drawer-number'>"+d.element_count.toLocaleString()+"</div><p>Quadratic tetrahedral volume elements, "+d.node_count.toLocaleString()+" mesh nodes</p>"],
   ["Theory cross-check","<div class='drawer-number'>"+fmt(d.theoretical_beam_tip_mm,4)+" mm</div><p>Independent ideal beam reference; deviation "+fmt(d.reference_difference_percent,2)+"%</p>"],
   ["Computational specimen","<div class='drawer-number'>120 × 30 × "+d.dimensions_mm[2]+" mm</div><p>Generated geometry; not a physically measured part.</p>"]
  ]):cards([
   ["Lab specimen","<div class='drawer-number'>1,524 mm</div><p>Reconstructed steel cantilever with five documented sensor heights.</p>"],
   ["Published Mode 1","<div class='drawer-number'>1.569 Hz</div><p>Measured laboratory natural frequency, distinct from our solver.</p>"],
   ["Validation boundaries","<p>Physical modal data only. This reduced-order FEM omits sensor masses, shear and fixture detail.</p>"]
  ]);
 }else if(state.drawer==="results"){
  if(solid){
   if(!state.redesign){el.innerHTML="<p class='result-note'>Run Explore design alternatives to calculate nine independent 3D finite-element candidate designs.</p>";return;}
   const r=state.redesign,rows=r.candidates;
   el.innerHTML=(r.best?"<p class='result-note'><strong>Selected candidate:</strong> "+r.best.thickness_mm+" mm · "+fmt(r.best.tip_displacement_mm,4)+" mm tip movement · "+fmt(r.best.mass_delta_percent,1)+"% mass change.</p>":"<p class='result-note'>No candidate satisfies the chosen modeled limits.</p>")+
    "<table class='result-table'><thead><tr><th>THICKNESS</th><th>DEFLECTION</th><th>VON MISES</th><th>MASS</th><th>LIMIT</th></tr></thead><tbody>"+rows.map(x=>"<tr><td>"+x.thickness_mm+" mm</td><td>"+fmt(x.tip_mm,4)+" mm</td><td>"+fmt(x.stress_mpa,2)+" MPa</td><td>"+fmt(x.mass_kg,3)+" kg</td><td>"+(x.feasible?"Within":"Exceeded")+"</td></tr>").join("")+"</tbody></table>";
  }else{
   el.innerHTML="<table class='result-table'><thead><tr><th>MODE</th><th>PHYSICAL</th><th>OUR FEM</th><th>PUBLISHED ABAQUS</th><th>OUR ERROR</th></tr></thead><tbody>"+d.frequencies_hz.map((f,i)=>"<tr><td>B"+(i+1)+"x</td><td>"+fmt(d.measured_hz[i],3)+" Hz</td><td>"+fmt(f,3)+" Hz</td><td>"+fmt(d.published_abaqus_hz[i],3)+" Hz</td><td>"+fmt(d.error_percent[i],2)+"%</td></tr>").join("")+"</tbody></table>"+
   (state.calibration?"<p class='result-note'>Effective fitted stiffness "+fmt(state.calibration.k_nm_rad,1)+" N·m/rad; Modes 2 and 3 held-out MAPE "+fmt(state.calibration.holdout_mape_percent,2)+"%. Fitted stiffness is not a directly measured physical property.</p>":"<p class='result-note'>Calibration uses only the measured first mode; Modes 2 and 3 are held out.</p>");
  }
 }else{
  el.innerHTML=solid?cards([
   ["Source of model","<p>Original parametric solid. No laboratory static test for this geometry.</p>"],
   ["Solver boundaries","<p>True tet10 linear elasticity, sampled Gauss-point von Mises. Clamp-region stress is mesh sensitive.</p>"],
   ["Original workflow","<p>Specialist Streamlit engineering pages remain available in the project.</p><a target='_blank' rel='noopener noreferrer' href='https://github.com/NeonGrade/ForceForge-AI'>Open repository ↗</a>"]
  ]):cards([
   ["Published article","<p>Thurn et al., Wind Energy Science (2026), CC BY 4.0.</p><a target='_blank' rel='noopener noreferrer' href='"+esc(d.measurement_source)+"'>Peer-reviewed paper ↗</a>"],
   ["University dataset","<p>Published original measurements and Abaqus files, CC BY 3.0.</p><a target='_blank' rel='noopener noreferrer' href='"+esc(d.dataset_source)+"'>Source dataset ↗</a>"],
   ["Reconstructed CAD","<p>STEP and STL based on the published physical specimen dimensions.</p><a href='/download/beam.step'>STEP ↗</a> &nbsp; <a href='/download/beam.stl'>STL ↗</a>"]
  ]);
 }
}
async function primaryAction(){
 const workspace=state.workspace;
 const original=JSON.stringify(state.params[workspace]);
 $("primary-action").disabled=true;status("COMPUTING");
 try{
  if(workspace==="solid"){
   const d=await api("/api/redesign",{...state.params.solid});
   if(workspace!==state.workspace||JSON.stringify(state.params[workspace])!==original)return;
   state.redesign=d;notify(d.best?"Candidate "+d.best.thickness_mm+" mm; mass change "+fmt(d.best.mass_delta_percent,1)+"%.":"No candidate passed the assumed limits.");
  }else{
   const d=await api("/api/calibrate",{...state.params.lab});
   if(workspace!==state.workspace||JSON.stringify(state.params[workspace])!==original)return;
   state.calibration=d;state.params.lab.log10_k=d.log10_k;$("lab-stiffness").value=d.log10_k;
   updateLabels();notify("Calibrated Mode 1; held-out MAPE "+fmt(d.holdout_mape_percent,2)+"%.");await solve();
  }
  drawerTab("results");setDrawer(true);
 }catch(e){notify("Analysis error: "+e.message);}
 finally{$("primary-action").disabled=false;status("SOLVED");}
}
function dialog(title,content){text("dialog-title",title);$("dialog-content").innerHTML=content;$("studio-dialog").showModal();}
function guide(){
 dialog("Engineering, made tangible.",
 "<p><strong>Explore the model.</strong> Drag to orbit; scroll to zoom. Select a workspace on the left, then adjust engineering controls. The geometry and numbers are driven by the existing Python solver.</p>"+
 "<p><strong>Inspect results.</strong> The right panel highlights current values. Expand the bottom drawer for detailed evidence, assumptions and source attribution.</p>"+
 "<p><strong>Interpret carefully.</strong> The true 3D solid is a numerical benchmark, not a physically tested part. The Hannover lab model has physical modal measurements but uses a simplified beam FEM. No structural safety certification is implied.</p>");
}
function init(){
 document.querySelectorAll("[data-workspace]").forEach(el=>el.onclick=()=>selectWorkspace(el.dataset.workspace));
 document.querySelectorAll("[data-select-workspace]").forEach(el=>el.onclick=()=>selectWorkspace(el.dataset.selectWorkspace));
 $("module-select").onclick=()=>visible("module-menu",$("module-menu").hidden);
 $("rail-controls").onclick=()=>setControls($("control-panel").classList.contains("collapsed"));
 $("close-controls").onclick=()=>setControls(false);
 $("rail-results").onclick=()=>setDrawer(!$("bottom-drawer").classList.contains("open"));
 $("rail-evidence").onclick=()=>{drawerTab("evidence");setDrawer(true);};
 $("drawer-toggle").onclick=()=>setDrawer(!$("bottom-drawer").classList.contains("open"));
 document.querySelectorAll("[data-drawer-tab]").forEach(el=>el.onclick=()=>{drawerTab(el.dataset.drawerTab);setDrawer(true);});
 document.querySelectorAll("[data-viz]").forEach(el=>el.onclick=()=>{
  state.viz=el.dataset.viz;window.forceForgeViz=state.viz;document.querySelectorAll("[data-viz]").forEach(a=>a.classList.toggle("selected",a===el));
  view.draw();if(state.data)renderLegend();
 });
 $("toggle-sensors").onclick=()=>{state.sensors=!state.sensors;window.forceForgeSensors=state.sensors;$("toggle-sensors").classList.toggle("is-on",state.sensors);view.draw();};
 ["reset-camera","view-reset-top"].forEach(id=>$(id).onclick=()=>view.reset());
 $("primary-action").onclick=primaryAction;
 let focus=false,standardView=0;
 $("explore-toggle").onclick=()=>{
   focus=!focus;$("app").classList.toggle("focus-mode",focus);
   $("explore-toggle").setAttribute("aria-pressed",String(focus));
   text("explore-toggle-text",focus?"ENGINEERING":"IMMERSIVE");
   setTimeout(()=>view.resize(),350);
 };
 $("camera-view").onclick=()=>{
   const sequence=["iso","front","right","top"];
   if(typeof view.setView==="function")view.setView(sequence[standardView%4]);
   else view.reset();
   text("camera-view",["ISO","FRONT","RIGHT","TOP"][standardView%4]);
   standardView++;
 };
 $("true-scale").onclick=()=>{
   if(typeof view.setTrueScale!=="function")return;
   const exact=$("true-scale").getAttribute("aria-pressed")!=="true";
   $("true-scale").setAttribute("aria-pressed",String(exact));
   text("true-scale",exact?"DETAIL":"1:1");
   view.setTrueScale(exact);
   notify(exact?"Actual beam section aspect ratio enabled.":"Section enlarged for inspection only; physical dimensions unchanged.");
 };
 $("intel-action").onclick=()=>{
   if(state.workspace==="lab"){drawerTab("evidence");setDrawer(true);}
   else {setControls(true);$("solid-force").focus();}
 };
 $("tree-model").onclick=()=>{setSceneSelection(null);view.reset();};
 $("tree-geometry").onclick=()=>{setSceneSelection(null);state.viz="form";window.forceForgeViz="form";document.querySelectorAll("[data-viz]").forEach(b=>b.classList.toggle("selected",b.dataset.viz==="form"));view.draw();};
 $("tree-solver").onclick=()=>{state.viz="wire";window.forceForgeViz="wire";document.querySelectorAll("[data-viz]").forEach(b=>b.classList.toggle("selected",b.dataset.viz==="wire"));view.draw();};
 $("tree-measurements").onclick=()=>{
    if(state.workspace==="lab"){state.sensors=true;window.forceForgeSensors=true;view.draw();setSceneSelection(null);}
    drawerTab("results");setDrawer(true);
 };

 $("help-btn").onclick=guide;$("rail-guide").onclick=guide;
 $("stage-info").onclick=()=>dialog("Model fidelity and limitations.",
  "<p>"+esc(state.data?.validation||"Model is not loaded.")+"</p><p>Visualization: "+esc(state.data?.visual_deformation||"not available")+"</p><p>See the Evidence drawer for sources and scope boundaries.</p>");
 $("dialog-close").onclick=()=>$("studio-dialog").close();
 const mapping={
  "solid-force":["solid","force_n"],"solid-thickness":["solid","thickness_mm"],
  "solid-limit":["solid","allowed_mm"],"solid-visual":["solid","visual_scale"],
  "solid-resolution":["solid","resolution"],"lab-view":["lab","view"],
  "lab-mode":["lab","mode"],"lab-stiffness":["lab","log10_k"],
  "lab-amplitude":["lab","amplitude_mm"],"lab-force":["lab","tip_force_n"],
  "lab-E":["lab","E_gpa"],"lab-elements":["lab","elements"],"lab-gauges":["lab","gauges"]
 };
 for(const [id,[w,key]] of Object.entries(mapping)){
  const el=$(id),callback=()=>{state.params[w][key]=el.type==="checkbox"?el.checked:el.tagName==="SELECT"&&id==="solid-resolution"||id==="lab-view"?el.value:Number(el.value);changed();};
  el.addEventListener(el.type==="range"?"input":"change",callback);
 }
 window.addEventListener("keydown",e=>{
  if(["INPUT","SELECT","TEXTAREA"].includes(document.activeElement.tagName))return;
  if(e.key==="r")view.reset();
  if(e.key==="f")$("explore-toggle").click();
  if(e.key==="1")selectWorkspace("solid");
  if(e.key==="2")selectWorkspace("lab");
 });
 updateLabels();view.resize();selectWorkspace("solid");
}
document.addEventListener("DOMContentLoaded",init);
