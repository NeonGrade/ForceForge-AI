/* ForceForge X — Spatial Inspection UI v0.2.1
 * 3D depth-tested reference grid + legible XYZ axes + surface hover probing.
 * Surface picks return barycentric undeformed coordinates and FEM field samples.
 * No interpolated value is presented as a physical measurement.
 */
(function(){
"use strict";
const canvas=document.getElementById("model-canvas");
if(!canvas)return;
const world=document.getElementById("world");
const $id=id=>document.getElementById(id);
const tip=document.createElement("div");
tip.id="surface-probe";tip.className="surface-probe";tip.hidden=true;
tip.setAttribute("role","status");tip.setAttribute("aria-label","Hovered finite element surface data");
world.appendChild(tip);
const gridLabel=document.createElement("div");
gridLabel.className="spatial-grid-label";gridLabel.textContent="XYZ REFERENCE · mm";
world.appendChild(gridLabel);
const axisIndicator=document.createElement("div");
axisIndicator.className="axis-indicator";axisIndicator.setAttribute("aria-label","World coordinate axis orientation");
world.appendChild(axisIndicator);
const clamp=(v,a,b)=>Math.max(a,Math.min(v,b));
const fmt=(v,d=2)=>Number(v).toFixed(d);
const vertexShader=`#version 300 es
precision highp float;
layout(location=0) in vec3 aPoint;
layout(location=1) in vec4 aColor;
uniform mat4 uMVP;
out vec4 color;
void main(){gl_Position=uMVP*vec4(aPoint,1.);color=aColor;}`;
const fragmentShader=`#version 300 es
precision highp float;
in vec4 color;
out vec4 outputColor;
void main(){outputColor=color;}`;
function shader(gl,type,source){
 const v=gl.createShader(type);gl.shaderSource(v,source);gl.compileShader(v);
 if(!gl.getShaderParameter(v,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(v));
 return v;
}
function makeProgram(gl){
 const p=gl.createProgram();
 gl.attachShader(p,shader(gl,gl.VERTEX_SHADER,vertexShader));
 gl.attachShader(p,shader(gl,gl.FRAGMENT_SHADER,fragmentShader));gl.linkProgram(p);
 if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(p));
 return p;
}
function dot(a,b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
function norm(v){return Math.hypot(v[0],v[1],v[2]);}
function rgb(v){return "rgb("+v.map(Math.round).join(",")+")";}
function bestStep(span){
 const q=Math.max(1e-7,span/12),power=Math.pow(10,Math.floor(Math.log10(q)));
 return [1,2,5,10].map(k=>k*power).find(x=>x>=q)||10*power;
}
function createReferenceGrid(v){
 const gl=v.gl,shaderProgram=makeProgram(gl);
 const vao=gl.createVertexArray(),buffer=gl.createBuffer();
 const geometry={program:shaderProgram,vao,buffer,count:0,axes:[],step:10};
 const push=(array,a,b,color)=>{for(const p of [a,b])array.push(...p,...color);};
 function build(){
  if(!v.raw||!v.raw.length)return;
  const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
  for(const p of (v.referenceRaw||v.raw)){
   for(let i=0;i<3;i++){lo[i]=Math.min(lo[i],p[i]);hi[i]=Math.max(hi[i],p[i]);}
  }
  const size=Math.max(1,...lo.map((x,i)=>hi[i]-x));
  const step=bestStep(size),extent=Math.max(4*step,size*.85);
  const center=[(lo[0]+hi[0])/2,(lo[1]+hi[1])/2,lo[2]-step*.75];
  const x0=center[0]-extent,x1=center[0]+extent;
  const y0=center[1]-extent,y1=center[1]+extent;
  const data=[];
  for(let n=-Math.ceil(extent/step);n<=Math.ceil(extent/step);n++){
   const major=(n%5===0);
   const color=major?[.41,.64,.67,.31]:[.37,.54,.59,.16];
   const x=center[0]+n*step,y=center[1]+n*step;
   push(data,[x,y0,center[2]],[x,y1,center[2]],color);
   push(data,[x0,y,center[2]],[x1,y,center[2]],color);
  }
  const axisLength=Math.max(size*.22,step*3);
  const origin=[lo[0]-step*.35,lo[1]-step*.35,lo[2]-step*.35];
  const list=[
   ["X",[origin[0]+axisLength,origin[1],origin[2]],[1,.48,.39,1]],
   ["Y",[origin[0],origin[1]+axisLength,origin[2]],[.57,.93,.66,1]],
   ["Z",[origin[0],origin[1],origin[2]+axisLength],[.39,.69,1,1]]
  ];
  for(const [label,end,color] of list){
   push(data,origin,end,color);
  }
  geometry.axes=list.map(([label,end,color])=>({label,end,color}));
  geometry.step=step;
  const arr=new Float32Array(data);
  gl.bindVertexArray(vao);gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
  gl.bufferData(gl.ARRAY_BUFFER,arr,gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,3,gl.FLOAT,false,28,0);
  gl.enableVertexAttribArray(1);gl.vertexAttribPointer(1,4,gl.FLOAT,false,28,12);
  gl.bindVertexArray(null);
  geometry.count=arr.length/7;
  gridLabel.textContent="XYZ REFERENCE · "+fmt(step,step<1?2:0)+" mm GRID";
 }
 function draw(matrix){
  if(!geometry.count)return;
  gl.useProgram(geometry.program);gl.bindVertexArray(vao);
  gl.uniformMatrix4fv(gl.getUniformLocation(geometry.program,"uMVP"),false,matrix);
  gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);
  gl.depthMask(false);
  gl.drawArrays(gl.LINES,0,geometry.count);
  gl.depthMask(true);gl.disable(gl.BLEND);
  gl.bindVertexArray(null);
 }
 return {...geometry,build,draw,axes:geometry.axes,getAxes:()=>geometry.axes};
}
function normalizePoint(v,p){
 const x=p.map((q,i)=>(q-v.center[i])/v.extent);
 if(v.workspace==="lab"&&!v.trueScale){x[0]*=24;x[1]*=24;}
 return x;
}
function project(v,m,p){
 const q=normalizePoint(v,p),vec=[...q,1],clip=[0,0,0,0];
 for(let row=0;row<4;row++)for(let k=0;k<4;k++)clip[row]+=m[k*4+row]*vec[k];
 if(clip[3]<=0)return null;
 return {x:(clip[0]/clip[3]*.5+.5)*v.width,y:(.5-clip[1]/clip[3]*.5)*v.height,
         depth:clip[2]/clip[3],w:clip[3]};
}
function barycentric(a,b,c,x,y){
 const d=(b.y-c.y)*(a.x-c.x)+(c.x-b.x)*(a.y-c.y);
 if(Math.abs(d)<1e-8)return null;
 const u=((b.y-c.y)*(x-c.x)+(c.x-b.x)*(y-c.y))/d;
 const w=((a.y-b.y)*(x-c.x)+(b.x-a.x)*(y-c.y))/d;
 const v=1-u-w;
 return Math.min(u,v,w)>=-1e-5?[u,v,w]:null;
}
function probeAt(v,x,y){
 if(!v.raw?.length||!v.faces?.length)return null;
 const m=v.matrices(),projected=v.raw.map(p=>project(v,m,p));
 let best=null,depth=Infinity;
 for(let f=0;f<v.faces.length;f++){
  const idx=v.faces[f],a=projected[idx[0]],b=projected[idx[1]],c=projected[idx[2]];
  if(!a||!b||!c)continue;
  if(x<Math.min(a.x,b.x,c.x)-.75||x>Math.max(a.x,b.x,c.x)+.75
      ||y<Math.min(a.y,b.y,c.y)-.75||y>Math.max(a.y,b.y,c.y)+.75)continue;
  const weights=barycentric(a,b,c,x,y);if(!weights)continue;
  const d=weights[0]*a.depth+weights[1]*b.depth+weights[2]*c.depth;
  if(d>=depth)continue;
  const pers=weights.map((val,i)=>val/[a,b,c][i].w);
  const denom=pers[0]+pers[1]+pers[2];
  if(denom<=0)continue;
  const w=pers.map(z=>z/denom),nodes=v.referenceRaw||v.raw;
  const position=[0,0,0],motion=[0,0,0],display=[0,0,0];
  for(let k=0;k<3;k++)for(let j=0;j<3;j++){
   position[k]+=w[j]*nodes[idx[j]][k];
   display[k]+=w[j]*v.raw[idx[j]][k];
   if(v.actualDisplacements)motion[k]+=w[j]*v.actualDisplacements[idx[j]][k];
  }
  depth=d;
  best={face:f,position,display,motion,stress:v.scalars?.[f]??null,
        movement:v.actualDisplacements?norm(motion):null,
        screen:{x,y},mode:v.workspace};
 }
 return best;
}
function axisCompass(v,m){
 const unit=.17,raw=[0,0,0],origin=[90,86],axes=[
  ["X",[unit,0,0],"#ff9683"],["Y",[0,unit,0],"#a3efb6"],
  ["Z",[0,0,unit],"#83b9ff"]];
 const y=v.yaw,p=v.pitch;
 const right=[Math.cos(y),Math.sin(y),0];
 const up=[-Math.sin(y)*Math.sin(p),Math.cos(y)*Math.sin(p),Math.cos(p)];
 const pieces=axes.map(([name,vector,color])=>({
   name,color,x:origin[0]+dot(vector,right)*135,y:origin[1]-dot(vector,up)*135
 }));
 const strokes=pieces.map(a=>'<line x1="90" y1="86" x2="'+a.x+'" y2="'+a.y+'" stroke="'+a.color+'" stroke-width="2.7" stroke-linecap="round"/>'+
  '<circle cx="'+a.x+'" cy="'+a.y+'" r="11" fill="'+a.color+'"/>'+
  '<text x="'+a.x+'" y="'+(a.y+3.8)+'" text-anchor="middle" fill="#0a1721" font-size="11" font-weight="800">'+a.name+'</text>').join("");
 axisIndicator.innerHTML='<svg viewBox="0 0 180 170" aria-hidden="true">'+strokes+
 '<circle cx="90" cy="86" r="3.6" fill="#f2f4e9"/></svg>';
}
let activeHover=null,mouse=null,lastProbe=0;
function showHover(hit){
 if(!hit){tip.hidden=true;activeHover=null;return;}
 activeHover=hit;
 const v=view,lab=v.workspace==="lab";
 const [x,y,z]=hit.position.map(a=>fmt(a,2));
 const coords='<span class="probe-coords">X '+x+' · Y '+y+' · Z '+z+' mm</span>';
 let status="";
 if(lab){
  if(v.actualDisplacements){
   status='<div class="probe-measure"><span>FEM displacement</span><strong>'+fmt(hit.movement,5)+' mm</strong></div>';
  }else{
   const mode=ui?.params?.lab?.mode||1;
   const d=ui?.data;
   status='<div class="probe-measure"><span>Mode B'+mode+' · computed</span><strong>'+
     (d?fmt(d.frequencies_hz[mode-1],3)+' Hz':"—")+'</strong></div>';
  }
 }else{
  status='<div class="probe-measure"><span>Von Mises · face sample</span><strong>'+
    (hit.stress===null?"—":fmt(hit.stress,2)+' MPa')+'</strong></div>'+
    '<div class="probe-measure"><span>FEM |u| · interpolated</span><strong>'+
    (hit.movement===null?"—":fmt(hit.movement,5)+' mm')+'</strong></div>';
 }
 tip.innerHTML='<div class="probe-heading"><span class="probe-cross">⌖</span> SURFACE · FEM</div>'+
   coords+status+
   '<div class="probe-note">'+
   (lab&&!v.actualDisplacements?"Mode geometry is display-scaled · frequency is global":
    "Reference position · displayed deformation may be exaggerated")+'</div>';
 const w=world.clientWidth,h=world.clientHeight;
 const width=Math.min(275,Math.max(180,w-20)),estimated=145;
 tip.style.left=clamp(hit.screen.x+18,8,w-width-8)+"px";
 tip.style.top=clamp(hit.screen.y+16,80,h-estimated-85)+"px";
 tip.hidden=false;
}
let enabled=true;
function install(){
 if(typeof view==="undefined"||!view?.gl)return;
 const v=view,grid=createReferenceGrid(v);
 const originalLoad=v.load.bind(v);
 v.load=function(data){
  originalLoad(data);
  this.referenceRaw=data.mesh?.reference_vertices||data.mesh?.vertices||[];
  this.actualDisplacements=data.mesh?.displacements_mm||null;
  grid.build();showHover(null);
  this.draw();
 };
 const originalFrame=v._frame.bind(v);
 v._frame=function(){
  originalFrame();
  if(v.count>0){
   const m=v.matrices();
   grid.draw(m);
   axisCompass(v,m);
  }
 };
 canvas.addEventListener("pointermove",e=>{
  if(v.active){showHover(null);return;}
  mouse={x:e.offsetX,y:e.offsetY};
  const now=performance.now();
  if(now-lastProbe<38)return;
  lastProbe=now;
  showHover(probeAt(v,mouse.x,mouse.y));
 },{passive:true});
 canvas.addEventListener("pointerdown",()=>showHover(null));
 canvas.addEventListener("pointerleave",()=>showHover(null));
 canvas.addEventListener("pointercancel",()=>showHover(null));
 window.addEventListener("blur",()=>showHover(null));
}
install();
})();