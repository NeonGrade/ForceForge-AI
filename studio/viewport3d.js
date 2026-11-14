/* ForceForge X | Precision viewport — UI v0.1 redesign.
 * GPU rendering of actual backend mesh triangles. Numerical computations remain
 * in the Python FEA solvers. No downloaded assets or third-party renderer.
 */
(function(global){
"use strict";
const VERT=`#version 300 es
precision highp float;
layout(location=0) in vec3 aPosition;
layout(location=1) in vec3 aNormal;
layout(location=2) in float aValue;
layout(location=3) in vec3 aBary;
uniform mat4 uMVP;
out vec3 vNormal;out float vValue;out vec3 vBary;out vec3 vPosition;
void main(){
  gl_Position=uMVP*vec4(aPosition,1.0);
  vNormal=aNormal;vValue=aValue;vBary=aBary;vPosition=aPosition;
}`;
const FRAG=`#version 300 es
precision highp float;
in vec3 vNormal;in float vValue;in vec3 vBary;in vec3 vPosition;
uniform int uMode;uniform float uMaximum;uniform float uOpacity;
out vec4 frag;
vec3 heat(float t){
 t=clamp(t,0.0,1.0);
 if(t<.25) return mix(vec3(.20,.39,.49),vec3(.23,.70,.72),t*4.0);
 if(t<.5) return mix(vec3(.23,.70,.72),vec3(.77,.84,.61),(t-.25)*4.0);
 if(t<.75) return mix(vec3(.77,.84,.61),vec3(.96,.67,.37),(t-.5)*4.0);
 return mix(vec3(.96,.67,.37),vec3(.86,.33,.27),(t-.75)*4.0);
}
void main(){
 vec3 n=normalize(vNormal);
 vec3 light=normalize(vec3(-.4,.7,.8));
 float diff=abs(dot(n,light));
 float rim=pow(1.0-abs(dot(n,normalize(vec3(.4,-.6,.65)))),2.5);
 vec3 base=uMode==1?heat(vValue/max(uMaximum,.000001)):vec3(.51,.69,.72);
 float lum=.40+.59*diff;
 vec3 color=base*lum+vec3(.11,.17,.18)*rim;
 color+=vec3(.025,.035,.045);
 float edge=min(vBary.x,min(vBary.y,vBary.z));
 float dw=max(fwidth(edge),.0001);
 float outline=1.0-smoothstep(dw*.8,dw*2.7,edge);
 if(uMode==2) color=mix(color,vec3(.62,.84,.85),outline*.86);
 else color=mix(color,vec3(.07,.14,.18),outline*.12);
 frag=vec4(color,uOpacity);
}`;
function shader(gl,type,text){
 const s=gl.createShader(type);gl.shaderSource(s,text);gl.compileShader(s);
 if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s;
}
function program(gl){
 const p=gl.createProgram();gl.attachShader(p,shader(gl,gl.VERTEX_SHADER,VERT));gl.attachShader(p,shader(gl,gl.FRAGMENT_SHADER,FRAG));gl.linkProgram(p);
 if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(p));return p;
}
function multiply(a,b){
 const r=new Float32Array(16);
 for(let c=0;c<4;c++)for(let row=0;row<4;row++)
   for(let k=0;k<4;k++)r[c*4+row]+=a[k*4+row]*b[c*4+k];
 return r;
}
function perspective(fovy,aspect,near,far){
 const f=1/Math.tan(fovy/2),o=new Float32Array(16);
 o[0]=f/aspect;o[5]=f;o[10]=(far+near)/(near-far);o[11]=-1;o[14]=2*far*near/(near-far);return o;
}
function normalize(v){const n=Math.hypot(...v)||1;return v.map(a=>a/n);}
function cross(a,b){return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];}
function dot(a,b){return a.reduce((s,x,i)=>s+x*b[i],0);}
function lookAt(eye,center,up){
 const z=normalize(eye.map((x,i)=>x-center[i]));
 const x=normalize(cross(up,z)),y=cross(z,x);
 const o=new Float32Array(16);
 o[0]=x[0];o[1]=y[0];o[2]=z[0];o[4]=x[1];o[5]=y[1];o[6]=z[1];o[8]=x[2];o[9]=y[2];o[10]=z[2];
 o[12]=-dot(x,eye);o[13]=-dot(y,eye);o[14]=-dot(z,eye);o[15]=1;return o;
}
const clamp=(v,lo,hi)=>Math.max(lo,Math.min(hi,v));
class ForgeViewport {
 constructor(canvas){
   this.canvas=canvas;
   this.gl=canvas.getContext("webgl2",{alpha:false,antialias:true,depth:true,preserveDrawingBuffer:false});
   if(!this.gl)throw Error("WebGL2 not available");
   this.program=program(this.gl);
   this.vao=this.gl.createVertexArray();this.buffer=this.gl.createBuffer();
   this.count=0;this.raw=[];this.sensors=[];this.center=[0,0,0];this.extent=1;this.max=1;
   this.yaw=.62;this.pitch=.22;this.targetYaw=this.yaw;this.targetPitch=this.pitch;
   this.zoom=1;this.targetZoom=1;this.active=false;this.last=[0,0];this.dragStart=null;this.raf=0;
   this.trueScale=false;this.workspace="solid";this.width=0;this.height=0;
   this.onSelect=null;this.selected=null;
   this.overlay=document.createElement("canvas");this.overlay.className="forge-overlay";
   canvas.parentElement.appendChild(this.overlay);
   this.overlayContext=this.overlay.getContext("2d");
   this.gl.enable(this.gl.DEPTH_TEST);this.gl.disable(this.gl.CULL_FACE);
   this.gl.clearColor(.035,.065,.09,1);
   this.attach();
 }
 attach(){
   this.canvas.addEventListener("pointerdown",e=>{
     this.active=true;this.dragStart=[e.clientX,e.clientY];this.last=[e.clientX,e.clientY];
     this.canvas.setPointerCapture(e.pointerId);
   });
   this.canvas.addEventListener("pointermove",e=>{
     if(!this.active)return;
     this.targetYaw+=(e.clientX-this.last[0])*.009;this.targetPitch=clamp(this.targetPitch+(e.clientY-this.last[1])*.007,-1.35,1.35);
     this.last=[e.clientX,e.clientY];this.draw();
   });
   this.canvas.addEventListener("pointerup",e=>{
     const dist=this.dragStart?Math.hypot(e.clientX-this.dragStart[0],e.clientY-this.dragStart[1]):999;
     this.active=false;if(dist<7)this.selectAt(e.offsetX,e.offsetY);
   });
   this.canvas.addEventListener("pointercancel",()=>this.active=false);
   this.canvas.addEventListener("wheel",e=>{
     e.preventDefault();this.targetZoom=clamp(this.targetZoom*Math.exp(e.deltaY*.00105),.43,4.1);this.draw();
   },{passive:false});
   if(global.ResizeObserver)new ResizeObserver(()=>this.resize()).observe(this.canvas);
   global.addEventListener("resize",()=>this.resize());
 }
 load(data){
   const mesh=data.mesh||{};
   this.workspace=data.workspace||"solid";
   this.raw=mesh.vertices||[];this.faces=mesh.faces||[];this.scalars=mesh.scalar||null;
   this.sensors=data.sensors||[];
   this.max=data.stress_cmax_mpa||1;
   this.sourceTitle=data.model_title||"FEM geometry";
   this._assemble();
   this.resize();
 }
 _assemble(){
   if(!this.raw.length||!this.faces.length)return;
   const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
   for(const p of this.raw)for(let k=0;k<3;k++){lo[k]=Math.min(lo[k],p[k]);hi[k]=Math.max(hi[k],p[k]);}
   this.center=lo.map((x,i)=>(x+hi[i])/2);
   this.extent=Math.max(1,...lo.map((x,i)=>hi[i]-x));
   const data=new Float32Array(this.faces.length*3*10);
   const lab=this.workspace==="lab",thicknessScale=lab&&!this.trueScale?24:1;
   const point=(p)=>{
     const v=p.map((x,i)=>(x-this.center[i])/this.extent);
     if(lab){v[0]*=thicknessScale;v[1]*=thicknessScale;}
     return v;
   };
   let at=0;
   for(let f=0;f<this.faces.length;f++){
     const indices=this.faces[f],a=point(this.raw[indices[0]]),b=point(this.raw[indices[1]]),c=point(this.raw[indices[2]]);
     const e=b.map((x,i)=>x-a[i]),g=c.map((x,i)=>x-a[i]),n=normalize(cross(e,g));
     const bary=[[1,0,0],[0,1,0],[0,0,1]];
     for(let k=0;k<3;k++){
       const v=[a,b,c][k];
       for(let j=0;j<3;j++)data[at++]=v[j];
       for(let j=0;j<3;j++)data[at++]=n[j];
       data[at++]=this.scalars?Number(this.scalars[f])||0:0;
       for(let j=0;j<3;j++)data[at++]=bary[k][j];
     }
   }
   const gl=this.gl;gl.bindVertexArray(this.vao);gl.bindBuffer(gl.ARRAY_BUFFER,this.buffer);
   gl.bufferData(gl.ARRAY_BUFFER,data,gl.STATIC_DRAW);
   const stride=40;
   [[0,3,0],[1,3,12],[2,1,24],[3,3,28]].forEach(([loc,size,offset])=>{
     gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,size,gl.FLOAT,false,stride,offset);
   });
   gl.bindVertexArray(null);this.count=this.faces.length*3;
 }
 setTrueScale(bool){
   this.trueScale=Boolean(bool);this._assemble();this.draw();
 }
 reset(){
   this.targetYaw=.62;this.targetPitch=.22;this.targetZoom=1;this.draw();
 }
 setView(mode){
   if(mode==="front"){this.targetYaw=0;this.targetPitch=0;}
   else if(mode==="right"){this.targetYaw=Math.PI/2;this.targetPitch=0;}
   else if(mode==="top"){this.targetYaw=0;this.targetPitch=1.34;}
   else {this.targetYaw=.62;this.targetPitch=.22;}
   this.draw();
 }
 resize(){
   const w=this.canvas.clientWidth,h=this.canvas.clientHeight;if(!w||!h)return;
   this.width=w;this.height=h;
   const dpr=Math.min(2,global.devicePixelRatio||1);
   this.canvas.width=Math.floor(w*dpr);this.canvas.height=Math.floor(h*dpr);
   this.overlay.width=Math.floor(w*dpr);this.overlay.height=Math.floor(h*dpr);
   this.overlayContext.setTransform(dpr,0,0,dpr,0,0);
   this.gl.viewport(0,0,this.canvas.width,this.canvas.height);
   this.draw();
 }
 matrices(){
   // Unitized geometry. The fixed field of view fits tall and wide parts.
   const fov=36*Math.PI/180;
   const r=2.05*this.zoom;
   const eye=[Math.sin(this.yaw)*Math.cos(this.pitch)*r,-Math.cos(this.yaw)*Math.cos(this.pitch)*r,Math.sin(this.pitch)*r];
   const v=lookAt(eye,[0,0,0],[0,0,1]);
   return multiply(perspective(fov,Math.max(.2,this.width/Math.max(this.height,1)),.02,45),v);
 }
 projectNormalized(v,m){
   const vec=[v[0],v[1],v[2],1];
   const out=[0,0,0,0];for(let row=0;row<4;row++)for(let k=0;k<4;k++)out[row]+=m[k*4+row]*vec[k];
   if(out[3]<=0)return null;
   return {x:(out[0]/out[3]*.5+.5)*this.width,y:(.5-out[1]/out[3]*.5)*this.height,depth:out[2]/out[3]};
 }
 projectRaw(p,m){
   const v=p.map((x,i)=>(x-this.center[i])/this.extent);
   if(this.workspace==="lab"&&!this.trueScale){v[0]*=24;v[1]*=24;}
   return this.projectNormalized(v,m);
 }
 draw(){
   if(this.raf)return;
   this.raf=global.requestAnimationFrame(()=>this._frame());
 }
 _frame(){
   this.raf=0;
   const smooth=global.matchMedia&&global.matchMedia("(prefers-reduced-motion:reduce)").matches?1:.24;
   this.yaw+=(this.targetYaw-this.yaw)*smooth;
   this.pitch+=(this.targetPitch-this.pitch)*smooth;
   this.zoom+=(this.targetZoom-this.zoom)*smooth;
   const m=this.matrices(),gl=this.gl;
   gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
   if(this.count>0){
     const shader=this.program;
     gl.useProgram(shader);gl.bindVertexArray(this.vao);
     gl.uniformMatrix4fv(gl.getUniformLocation(shader,"uMVP"),false,m);
     const mode=global.forceForgeViz==="wire"?2:global.forceForgeViz==="stress"&&this.workspace==="solid"?1:0;
     gl.uniform1i(gl.getUniformLocation(shader,"uMode"),mode);
     gl.uniform1f(gl.getUniformLocation(shader,"uMaximum"),this.max);
     gl.uniform1f(gl.getUniformLocation(shader,"uOpacity"),1);
     gl.drawArrays(gl.TRIANGLES,0,this.count);gl.bindVertexArray(null);
   }
   this._drawGuides(m);
   if(Math.abs(this.targetYaw-this.yaw)>.0001||Math.abs(this.targetPitch-this.pitch)>.0001||Math.abs(this.targetZoom-this.zoom)>.0001)this.draw();
 }
 _drawGuides(matrix){
   const ctx=this.overlayContext,w=this.width,h=this.height;
   ctx.clearRect(0,0,w,h);
   // Keep the overlay clean: the model and picked sensors take priority.
   // A fixed HUD grid would render over the physical solid and obscure stress.
   const p0=this.projectNormalized([0,0,-.56],matrix),p1=this.projectNormalized([0,0,.56],matrix);
   if(p0&&p1){
     ctx.strokeStyle="rgba(169,215,213,.22)";ctx.setLineDash([3,8]);ctx.beginPath();ctx.moveTo(p0.x,p0.y);ctx.lineTo(p1.x,p1.y);ctx.stroke();ctx.setLineDash([]);
   }
   if(this.workspace==="lab"&&global.forceForgeSensors!==false){
     ctx.textBaseline="middle";ctx.font="700 10px -apple-system,sans-serif";
     for(const sensor of this.sensors){
       const p=this.projectRaw(sensor.position,matrix);if(!p)continue;
       const highlighted=this.selected===sensor.id;
       ctx.beginPath();ctx.arc(p.x,p.y,highlighted?6.2:4,0,Math.PI*2);ctx.fillStyle=highlighted?"#fbad83":"#d3eea4";ctx.fill();
       ctx.strokeStyle="#111d28";ctx.lineWidth=1.7;ctx.stroke();
       ctx.beginPath();ctx.strokeStyle="rgba(211,238,164,.75)";ctx.moveTo(p.x+6,p.y);ctx.lineTo(p.x+20,p.y-9);ctx.stroke();
       ctx.fillStyle=highlighted?"#ffd1b0":"#e4eee7";ctx.fillText(sensor.id,p.x+25,p.y-10);
     }
   }
   ctx.font="800 9px -apple-system,sans-serif";ctx.fillStyle="rgba(166,189,201,.42)";
   const axes=[["X",[.7,0,-.6]],["Y",[0,.7,-.6]],["Z",[0,0,.68]]];
   for(const [label,p]of axes){const a=this.projectNormalized(p,matrix);if(a)ctx.fillText(label,a.x,a.y);}
   if(this.workspace==="lab"&&!this.trueScale){
     ctx.font="700 10px -apple-system,sans-serif";ctx.fillStyle="rgba(214,232,227,.8)";
     ctx.fillText("SECTION EXPANDED ×24 · DISPLAY ONLY",20,h-100);
   }
 }
 selectAt(x,y){
   let nearest=null,min=23;const m=this.matrices();
   if(this.workspace==="lab")for(const p of this.sensors){
     const q=this.projectRaw(p.position,m);if(!q)continue;
     const d=Math.hypot(x-q.x,y-q.y);if(d<min){nearest=p;min=d;}
   }
   this.selected=nearest?nearest.id:null;
   this.draw();
   if(typeof this.onSelect==="function")this.onSelect(nearest?{...nearest,type:"sensor"}:{type:"model",name:this.sourceTitle});
 }
}
global.ForgeViewport=ForgeViewport;
})(window);
