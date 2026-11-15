/* ForceForge X — Adaptive Spatial UI v0.2, real STEP engineering integration.
 * The Python v0.8 Gmsh/tetra10 pipeline is always the numerical truth.
 */
"use strict";
const cadUI = (() => {
  const param = {
    workspace:"cad",source:"generated",web_mm:8,mesh_size_mm:10,
    force_n:250,direction:"+X",boundary:"Z",unit:"mm",
    E_gpa:200,nu:.29,density:8190,yield_mpa:900,visual_scale:35,
    token:null,revision_token:null,revision_web_mm:12
  };
  ui.params.cad=param;
  let current=null,revision=null,showRevision=false,busy=false;
  let sequence=0,timer=null,modelHash=null;
  let agentProposal=null,agentSnapshot=null,agentPrompt=null;
  const $cad = id=>document.getElementById(id);
  const sourceLabel = () => param.source==="generated"?"Editable bracket":
    current?.source_type==="Original NIST geometry"?"NIST original STEP":"Imported STEP";
  function display(){return showRevision&&revision?.revision?revision.revision:current;}
  function activate(){
    ui.workspace="cad";ui.data=null;ui.selected=null;ui.redesign=null;ui.calibration=null;
    revision=null;showRevision=false;modelHash=null;sequence++;
    if(view){view.count=0;view.points=[];view.faces=[];view.sensors=[];view.selected=null;view.reset();}
    $("scene-name").textContent="Real CAD";
    $("scene-kind").textContent="ACTUAL STEP · VOLUMETRIC FEA";
    $("scene-sigil").textContent="⌑";
    $("scene-sequence").textContent="03 / GEOMETRY → PHYSICS";
    $("scene-headline").textContent="Make geometry matter.";
    $("scene-subline").textContent="Your CAD, real mesh, real numerical response.";
    $("space-index").textContent="CAD / 003";
    $("footer-fidelity").textContent="STEP BREP / TETRA10 · ASSUMED LOAD";
    $("pin-force").hidden=false;$("pin-thickness").hidden=false;
    $("pin-support").hidden=true;$("pin-mode").hidden=true;$("pin-result").hidden=false;
    $("cad-controls").hidden=false;
    $("solid-settings").hidden=true;$("lab-settings").hidden=true;
    $("cad-settings").hidden=false;
    $("project-chooser").hidden=true;
    ui.viewMode="form";window.forceForgeViz="form";window.forceForgeSensors=false;
    $("mode-view").firstChild.textContent="MATERIAL ";
    syncSettings();refreshPinText();
    window.adaptiveUI?.onWorkspaceChange();
    solve();
  }
  function deactivate(){
    sequence++;clearTimeout(timer);
    $("cad-controls").hidden=true;
    $("cad-settings").hidden=true;
    current=null;revision=null;showRevision=false;ui.data=null;
  }
  function pinAnchors(){
    const d=display();if(!d)return {};
    const b=d.bbox_mm,axis="XYZ".indexOf(param.boundary);
    const center=b[0].map((v,i)=>(v+b[1][i])/2);
    const atTip=center.slice(),atMiddle=center.slice(),atResult=center.slice();
    atTip[axis]=b[1][axis];
    atMiddle[axis]=b[0][axis]+(b[1][axis]-b[0][axis])*.52;
    atResult[axis]=b[0][axis]+(b[1][axis]-b[0][axis])*.78;
    return {
      force:atTip,
      ...(param.source==="generated"?{thickness:atMiddle}:{}),
      result:atResult
    };
  }
  function refreshPinText(){
    $("force-caption").textContent="TRANSVERSE FORCE";
    $("force-readout").textContent=nf(param.force_n,0)+" N · "+param.direction;
    $("thickness-readout").textContent=param.source==="generated"?
      param.web_mm+" mm":"CHANGE CAD";
    $("pin-thickness").hidden=param.source!=="generated";
    $("result-caption").textContent="TIP MOVEMENT · STEP FEA";
    const d=display();
    $("result-readout").textContent=d?nf(d.tip_displacement_mm,4)+" mm":"— mm";
    $("cad-source-label").textContent=sourceLabel();
    $("cad-compare-shortcut").textContent=revision?"VIEW COMPARISON ↗":"REVISE CAD ↗";
  }
  function settingsValue(id,value){const el=$cad(id);if(el&&el!==document.activeElement)el.value=value;}
  function syncSettings(){
    $cad("cad-settings").hidden=ui.workspace!=="cad";
    if(ui.workspace!=="cad")return;
    settingsValue("cad-source-choice",param.source);
    settingsValue("cad-web",String(param.web_mm));
    settingsValue("cad-mesh",param.mesh_size_mm);
    settingsValue("cad-force",param.force_n);
    settingsValue("cad-direction",param.direction);
    settingsValue("cad-boundary",param.boundary);
    settingsValue("cad-unit",param.unit);
    settingsValue("cad-young",param.E_gpa);
    settingsValue("cad-nu",param.nu);
    settingsValue("cad-density",param.density);
    settingsValue("cad-yield",param.yield_mpa);
    settingsValue("cad-visual",param.visual_scale);
    settingsValue("cad-revision-web",String(param.revision_web_mm));
    $cad("cad-mesh-value").textContent=param.mesh_size_mm+" mm";
    $cad("cad-force-value").textContent=param.force_n+" N";
    $cad("cad-visual-value").textContent=param.visual_scale+"×";
    $cad("cad-web").disabled=param.source!=="generated";
    $cad("cad-revision-web").disabled=param.source!=="generated";
    $cad("cad-source-feedback").textContent=param.source==="generated"?
      "Demonstration L-bracket with three holes. Geometry is simulated, not a NIST measured part.":
      "Imported source "+(current?.source_sha256?.slice(0,12)||param.token?.slice(0,12)||"pending")+" · single watertight solid only";
    $cad("scientific-limit").textContent=
      "The original v0.8 STEP/Gmsh/tetra10 solver is used. CAD source geometry may be real; static loading and material properties are assumed.";
    refreshPinText();
  }
  function scheduleSolve(){
    agentProposal=null;
    $cad("cad-agent-confirm").disabled=true;
    if(ui.workspace!=="cad")return;
    ui.request++;sequence++;revision=null;showRevision=false;
    refreshPinText();setStatus("UPDATING");
    clearTimeout(timer);timer=setTimeout(solve,320);
  }
  async function solve(){
    if(ui.workspace!=="cad")return;
    current=null;revision=null;ui.data=null;showRevision=false;
    $cad("quick-result").hidden=true;
    refreshPinText();
    if(!$cad("detail-panel").hidden)renderDetails();
    const job=++sequence,requestId=++ui.request;
    const submitted={...param};delete submitted.revision_token;delete submitted.revision_web_mm;
    setStatus("SOLVING");
    $cad("loading-veil").hidden=!!current;
    try{
      const data=await request("/api/cad/solve",submitted);
      if(job!==sequence||requestId!==ui.request||ui.workspace!=="cad")return;
      current=data;ui.data=data;showRevision=false;
      $cad("loading-veil").hidden=true;
      const changedGeometry=data.source_sha256!==modelHash;
      modelHash=data.source_sha256;
      if(view){view.load(data);if(changedGeometry)view.reset();}
      setStatus("SOLVED");refreshPinText();refreshQuick();refreshLegend();
      if(!$cad("detail-panel").hidden)renderDetails();
      window.adaptiveUI?.onWorkspaceChange();
    }catch(e){
      if(job!==sequence||ui.workspace!=="cad")return;
      setStatus("ERROR");$cad("loading-veil").hidden=true;
      current=null;ui.data=null;
      if(view){view.count=0;view.draw();}
      refreshPinText();
      notice("CAD solve: "+e.message,true);
      $cad("cad-source-feedback").textContent=e.message+
        " · Install Gmsh on your Mac: python3 -m pip install 'gmsh>=4.12,<5'";
      $cad("cad-source-feedback").classList.add("error");
    }
  }
  async function importFile(file,revised=false){
    if(!file)return;
    if(!/\.(stp|step)$/i.test(file.name))throw Error("Choose a .step or .stp file");
    if(file.size>32*1024*1024)throw Error("STEP file exceeds the 32 MiB upload limit");
    setStatus("IMPORTING");
    const name=file.name.replace(/[^a-zA-Z0-9_. -]/g,"").slice(0,100);
    const response=await fetch("/api/cad/import",{
      method:"POST",headers:{"Content-Type":"application/step","X-Cad-Name":name},
      body:file
    });
    const output=await response.json();
    if(!response.ok)throw Error(output.error||"STEP import failed");
    if(revised){
      param.revision_token=output.token;
      $cad("cad-revision-feedback").textContent="Revised STEP imported: "+output.name+
        " · SHA-256 "+output.sha256.slice(0,12);
      notice("Revised STEP ready for independent mesh and solve.");
    }else{
      param.token=output.token;param.source="uploaded";param.unit="mm";
      revision=null;showRevision=false;
      syncSettings();scheduleSolve();
      notice("STEP source imported. Confirm geometry units and loading direction.");
    }
  }
  async function fetchNist(){
    setStatus("FETCHING");
    notice("Retrieving checksum-verified NIST original STEP…");
    try{
      const r=await request("/api/cad/fetch-nist",{});
      param.source="uploaded";param.token=r.token;param.unit="mm";
      scheduleSolve();syncSettings();
      notice("Original NIST geometry SHA-256 verified; meshing may exceed the 5,000-tet limit.");
    }catch(e){setStatus("ERROR");notice("NIST source fetch: "+e.message,true);}
  }
  async function runRevision(){
    if(ui.workspace!=="cad"||!current)return notice("Solve the original CAD first",true);
    if(param.source==="uploaded"&&!param.revision_token)
      return notice("Import a revised STEP file to compare this source.",true);
    const job=++sequence,params={...param};
    setStatus("SOLVING");
    $cad("cad-run-revision").disabled=true;
    try{
      const r=await request("/api/cad/revise",params);
      if(job!==sequence||ui.workspace!=="cad")return;
      revision=r;showRevision=false;setStatus("SOLVED");
      renderDetails();showPanel("detail-panel");
      notice("Two independent STEP meshes solved under the same assumed load.");
    }catch(e){setStatus("ERROR");notice("CAD revision: "+e.message,true);}
    finally{$cad("cad-run-revision").disabled=false;}
  }
  function switchComparison(useRevision){
    if(!revision)return;
    showRevision=useRevision;
    const d=display();if(view){view.load(d);view.reset();}
    refreshPinText();refreshQuick();refreshLegend();renderDetails();
  }
  function renderDetails(){
    $("detail-title").textContent="CAD analysis";
    $("detail-kicker").textContent="STEP BREP / VERIFIED MESH / TETRA10";
    if(!current){$("detail-content").innerHTML=
      "<div class='provenance'>No verified CAD result. Select a source and run the STEP mesh / FEA calculation. Optional Gmsh must be installed.</div>";
      return;}
    const d=display();
    let html=block("ACTUAL 3D FINITE ELEMENT SOLUTION",
      row("Tip movement",nf(d.tip_displacement_mm,4)+" mm")+
      row("Sampled von Mises",nf(d.max_von_mises_mpa,2)+" MPa")+
      row("Member mass",nf(d.mass_kg,4)+" kg")+
      row("Applied load",nf(d.force_n,0)+" N · "+d.direction));
    html+=block("GEOMETRY / MESH TRACE",
      row("CAD source",d.source_type)+
      row("STEP SHA-256",d.source_sha256.slice(0,16)+"…")+
      row("Tetrahedra",String(d.mesh_count))+
      row("Mesh/CAD volume difference",nf(d.volume_difference_percent,2)+"%")+
      row("Reaction residual",Number(d.reaction_residual).toExponential(2)));
    if(d.engineering_review){
      const review=d.engineering_review;
      html+=block("AGENT · EVIDENCE-BASED DESIGN REVIEW",
        "<p>"+esc(review.summary)+"</p>"+
        review.issues.map(text=>"<p>"+esc(text)+"</p>").join("")+
        "<p class='small-note'>"+esc(review.limitations.join(" "))+"</p>");
    }
    if(revision){
      html+=block("TWO INDEPENDENT STEP SOLVES",
        row("Original / revision mass",nf(revision.original.mass_kg,3)+" → "+nf(revision.revision.mass_kg,3)+" kg")+
        row("Original / revision movement",nf(revision.original.tip_displacement_mm,4)+" → "+nf(revision.revision.tip_displacement_mm,4)+" mm")+
        row("Original / revision stress",nf(revision.original.max_von_mises_mpa,2)+" → "+nf(revision.revision.max_von_mises_mpa,2)+" MPa")+
        row("Mass difference",(revision.mass_delta_percent>=0?"+":"")+nf(revision.mass_delta_percent,2)+"%")+
        '<div class="cad-compare-actions"><button type="button" id="cad-show-original" class="'+(!showRevision?"active":"")+'">View original</button><button type="button" id="cad-show-revised" class="'+(showRevision?"active":"")+'">View revised</button></div>');
    }
    html+=block("SOURCE & SCOPE",
      '<a href="https://doi.org/10.18434/mds2-2607" target="_blank" rel="noopener noreferrer">NIST official AM Bench dataset ↗</a>'+
      '<div class="data-row"><span>Model source</span><strong>'+esc(d.model_title)+'</strong></div>');
    html+='<div class="provenance">CAD geometry may be measured-source geometry, but the static force, supports and material are assumed. Tet10 FEA is linear elastic and not structural certification. Curved BRep faces are faceted. Peak stress requires mesh convergence.</div>';
    $("detail-content").innerHTML=html;
    const originalButton=$cad("cad-show-original"),revisedButton=$cad("cad-show-revised");
    if(originalButton)originalButton.onclick=()=>switchComparison(false);
    if(revisedButton)revisedButton.onclick=()=>switchComparison(true);
  }
  function refreshQuick(){
    if($("quick-result").hidden||!display())return;
    const d=display();
    $("quick-title").textContent="TET10 · COMPUTED MOVEMENT";
    $("quick-value").textContent=nf(d.tip_displacement_mm,4);
    $("quick-unit").textContent="mm";
    $("quick-minis").innerHTML="<div>Sampled stress: <strong>"+
      nf(d.max_von_mises_mpa,2)+" MPa</strong></div><div>Mesh: <strong>"+
      d.mesh_count+" volume tets</strong></div>";
  }
  function downloadStep(){
    const d=display();if(!d)return notice("No solved source is available",true);
    window.open("/download/cad/"+encodeURIComponent(d.cad_token)+".step","_blank","noopener");
  }
  function downloadAudit(){
    if(!current)return notice("No analysis result to export",true);
    const slim = d=>{
      if(!d)return null;
      const {mesh,cad_token,...metadata}=d;
      return metadata;
    };
    const text=JSON.stringify({
      original:slim(current),revision:revision?slim(revision.revision):null,
      note:"Original and revised STEP geometry were independently meshed and solved. Loads/materials/fixtures are assumptions."
    },null,2);
    const url=URL.createObjectURL(new Blob([text],{type:"application/json"}));
    const a=document.createElement("a");
    a.href=url;a.download="forceforge-cad-fem-audit.json";document.body.appendChild(a);
    a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),15000);
  }
  function sourceEditor(){
    showPanel("settings-panel");
    $cad("cad-source-choice").focus();
  }
  function bind(){
    $cad("cad-agent-preview").onclick=async()=>{
      agentProposal=null;$cad("cad-agent-confirm").disabled=true;
      const snapshot=JSON.stringify(param),prompt=$cad("cad-agent-brief").value;
      try{
        const response=await request("/api/cad/agent/preview",{current:{...param},prompt});
        if(snapshot!==JSON.stringify(param)||prompt!==$cad("cad-agent-brief").value)throw Error("Inputs changed; preview again.");
        agentProposal=response.proposal;agentSnapshot=snapshot;agentPrompt=prompt;
        $cad("cad-agent-output").textContent=JSON.stringify(agentProposal.changes,null,2)+"\n"+response.note;
        $cad("cad-agent-confirm").disabled=false;
      }catch(error){$cad("cad-agent-output").textContent=error.message;}
    };
    $cad("cad-agent-confirm").onclick=async()=>{
      if(!agentProposal||agentSnapshot!==JSON.stringify(param)||agentPrompt!==$cad("cad-agent-brief").value){
        agentProposal=null;$cad("cad-agent-confirm").disabled=true;
        $cad("cad-agent-output").textContent="Inputs changed; preview again before confirming.";return;
      }
      const snapshot=JSON.stringify(param),proposal=agentProposal;
      $cad("cad-agent-confirm").disabled=true;
      try{
        const response=await request("/api/cad/agent/confirm",{current:{...param},proposal});
        if(snapshot!==JSON.stringify(param))throw Error("Inputs changed; preview again.");
        Object.assign(param,response.parameters);agentProposal=null;
        $cad("cad-agent-output").textContent="Confirmed parameters; running fresh FEA…";
        syncSettings();clearTimeout(timer);await solve();
        $cad("cad-agent-output").textContent=current?
          "Fresh FEA completed. Open Results for the evidence-based design review.":
          "FEA did not complete. Inspect the reported solver error; no result is accepted.";
      }catch(error){agentProposal=null;$cad("cad-agent-output").textContent=error.message;}
    };
    $cad("cad-source-pin").onclick=sourceEditor;
    $cad("cad-compare-shortcut").onclick=()=>{
      if(revision)showPanel("detail-panel");
      else showPanel("settings-panel");
      $cad("cad-revision-web").focus();
    };
    $cad("cad-upload").onclick=()=>$cad("cad-file").click();
    $cad("cad-revision-upload").onclick=()=>$cad("cad-revision-file").click();
    $cad("cad-file").onchange=async e=>{
      try{await importFile(e.target.files?.[0]);}catch(err){notice(err.message,true);}
      e.target.value="";
    };
    $cad("cad-revision-file").onchange=async e=>{
      try{await importFile(e.target.files?.[0],true);}catch(err){notice(err.message,true);}
      e.target.value="";
    };
    $cad("cad-nist").onclick=fetchNist;
    $cad("cad-run-revision").onclick=runRevision;
    $cad("cad-download-step").onclick=downloadStep;
    $cad("cad-download-audit").onclick=downloadAudit;
    $cad("cad-source-choice").onchange=e=>{
      if(e.target.value==="uploaded"&&!param.token){$cad("cad-file").click();return;}
      param.source=e.target.value;revision=null;syncSettings();scheduleSolve();
    };
    const fieldMap={
      "cad-web":["web_mm",Number], "cad-mesh":["mesh_size_mm",Number],
      "cad-force":["force_n",Number], "cad-direction":["direction",String],
      "cad-boundary":["boundary",String], "cad-unit":["unit",String],
      "cad-young":["E_gpa",Number], "cad-nu":["nu",Number],
      "cad-density":["density",Number], "cad-yield":["yield_mpa",Number],
      "cad-visual":["visual_scale",Number]
    };
    for(const [id,[key,cast]] of Object.entries(fieldMap)){
      const el=$cad(id);
      const action=()=>{
        param[key]=cast(el.value);
        syncSettings();scheduleSolve();
      };
      el.addEventListener(el.type==="range"?"input":"change",action);
    }
    $cad("cad-revision-web").onchange=e=>{param.revision_web_mm=Number(e.target.value);};
  }
  bind();
  return {activate,deactivate,pinAnchors,refreshPinText,refreshQuick,syncSettings,
          scheduleSolve,solve,renderDetails,runRevision,showQuick:showQuickResult,
          sourceEditor};
  function showQuickResult(){if(current){$("quick-result").hidden=false;refreshQuick();}}
})();
window.cadUI=cadUI;

const adaptiveUI=(()=>{
 function compact(){return innerWidth<1080||innerHeight<710;}
 function onWorkspaceChange(){
   const space=ui.workspace;
   $("cad-controls").hidden=space!=="cad";
   $("cad-settings").hidden=space!=="cad";
   const buttons=document.querySelectorAll("[data-select-pin]");
   for(const b of buttons){
     const mode=b.dataset.selectPin;
     b.hidden=(mode==="support"||mode==="mode")&&space!=="lab"||
       mode==="thickness"&&space==="lab"||
       mode==="force"&&space==="lab"&&ui.params.lab.view!=="static"||
       mode==="mode"&&space==="lab"&&ui.params.lab.view==="static"||
       mode==="thickness"&&space==="cad"&&ui.params.cad.source!=="generated";
   }
   $("tools-toggle").setAttribute("aria-expanded","false");
   $("compact-tools").hidden=true;
   if(space!=="cad")$("pin-thickness").hidden=space==="lab";
 }
 function update(){
   const small=compact();
   const chooser=$("project-chooser");
   if(!small&&!chooser.hidden)chooser.hidden=true;
   onWorkspaceChangeIfNeeded();
 }
 let lastSpace=null;
 function onWorkspaceChangeIfNeeded(){
   if(ui.workspace!==lastSpace){lastSpace=ui.workspace;onWorkspaceChange();}
 }
 $("tools-toggle").onclick=()=>{
   const p=$("compact-tools");p.hidden=!p.hidden;
   $("tools-toggle").setAttribute("aria-expanded",String(!p.hidden));
 };
 document.querySelectorAll("[data-select-pin]").forEach(b=>b.onclick=()=>{
   $("compact-tools").hidden=true;$("tools-toggle").setAttribute("aria-expanded","false");
   showEditor(b.dataset.selectPin);
 });
 $("legacy-launch").onclick=()=>{
   $("project-chooser").hidden=true;
   closePanels();closeEditor();closeQuick();
   notice("Complete engineering modules are preserved. Start the original toolkit in another Terminal: python3 -m streamlit run app.py");
   $("detail-kicker").textContent="COMPLETE ENGINEERING MODULES";
   $("detail-title").textContent="Specialist workspaces";
   $("detail-content").innerHTML=block("ORIGINAL TOOLS",
     row("Advanced Structural Lab","Preserved")+
     row("Building / Industry / Automotive","Preserved")+
     row("Robust optimization and surrogate ML","Preserved")+
     row("Real STEP Engineering / 3D FEA","Preserved"))+
     '<div class="provenance">All original Streamlit pages remain in the same branch. Open a second Terminal in the repository and run <code>python3 -m streamlit run app.py</code>; then open <a href="http://127.0.0.1:8501" target="_blank" rel="noopener noreferrer">the complete engineering toolkit ↗</a>.</div>';
   $("detail-panel").hidden=false;$("settings-panel").hidden=true;
   $("panel-backdrop").hidden=false;
 };
 const src=$("project-chooser");
 document.addEventListener("pointerdown",e=>{
   if(!src.hidden&&!src.contains(e.target)&&!$("scene-selector").contains(e.target))src.hidden=true;
   const p=$("compact-tools");
   if(!p.hidden&&!p.contains(e.target)&&!$("tools-toggle").contains(e.target)){
     p.hidden=true;$("tools-toggle").setAttribute("aria-expanded","false");
   }
 });
 window.addEventListener("resize",update);
 onWorkspaceChange();
 return {onWorkspaceChange,update};
})();
window.adaptiveUI=adaptiveUI;
