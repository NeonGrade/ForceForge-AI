"""Continuous source-STL rotor kinematics beside VERIFIED, frozen CFD U/p.

This is a geometry loop, not a new OpenFOAM transient solution.
"""
from __future__ import annotations
import gzip
from hashlib import sha256
from pathlib import Path
import re
import struct
import numpy as np

MAX_STL=48*1024*1024
MAX_FACES=220000
DISPLAY_FACES=360
FRAMES=49


def read_stl_payload(path:Path) -> bytes:
    if not path.is_file() or path.stat().st_size>MAX_STL:
        raise ValueError("Original case STL missing or too large")
    if path.suffix==".gz":
        with gzip.open(path,"rb") as f:
            data=f.read(MAX_STL+1)
    elif path.suffix==".stl":
        data=path.read_bytes()
    else:
        raise ValueError("Actual rotor source must be STL or gzip STL")
    if len(data)>MAX_STL:
        raise ValueError("Actual uncompressed STL exceeds limit")
    return data


def sample_stl(payload:bytes,limit:int=DISPLAY_FACES) -> np.ndarray:
    if not payload or len(payload)>MAX_STL or not 20<=limit<=800:
        raise ValueError("Bounded actual rotor STL is required")
    triangles=None
    if len(payload)>=84:
        count=struct.unpack_from("<I",payload,80)[0]
        if 1<=count<=MAX_FACES and 84+50*count==len(payload):
            dtype=np.dtype([
                ("normal","<f4",(3,)),("points","<f4",(9,)),("flag","<u2")
            ])
            record=np.frombuffer(payload,dtype=dtype,count=count,offset=84)
            triangles=record["points"].reshape(count,3,3)
    if triangles is None:
        if not payload.lstrip().startswith(b"solid"):
            raise ValueError("Original rotor is not a valid STL")
        points=[]
        for line in payload.splitlines():
            part=line.strip().split()
            if part and part[0].lower()==b"vertex":
                if len(part)!=4:
                    raise ValueError("Malformed real STL vertex")
                points.append([float(v) for v in part[1:]])
        if not points or len(points)%3:
            raise ValueError("Original STL has incomplete triangles")
        triangles=np.asarray(points,dtype=float).reshape(-1,3,3)
    if len(triangles)>MAX_FACES or not np.isfinite(triangles).all():
        raise ValueError("Real STL faces are invalid or exceed limit")
    take=np.linspace(0,len(triangles)-1,min(len(triangles),limit)).astype(int)
    return np.asarray(triangles[take],dtype=float).copy()


def source_motion(dictionary:str) -> tuple[np.ndarray,np.ndarray]:
    if "rotatingMotion" not in dictionary:
        raise ValueError("Original mesh has no rotatingMotion")
    number=r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
    def vec(name):
        pattern=rf"(?m)^\s*{name}\s*\(\s*{number}\s+{number}\s+{number}\s*\)\s*;"
        values=re.findall(pattern,dictionary)
        if len(values)!=1:
            raise ValueError("Cannot establish unique source rotor "+name)
        return np.asarray(list(map(float,values[0])),dtype=float)
    origin,axis=vec("origin"),vec("axis")
    norm=np.linalg.norm(axis)
    if not (np.isfinite(origin).all() and np.isfinite(norm) and norm>1e-9):
        raise ValueError("Invalid source rotor axis or origin")
    return origin,axis/norm


def load_completed_case_rotor(job_id:str) -> dict:
    from .rotating_cfd import _valid_job_root,job_status
    state=job_status(job_id)
    if state.get("status")!="COMPLETED" or not state.get("solved"):
        raise ValueError("Source rotor playback requires verified finished CFD")
    kind=state.get("geometry_origin")
    if kind not in (
        "OFFICIAL_OPENFOAM_ROTATING_FAN_REFERENCE_GEOMETRY",
        "USER_STEP_ROTOR_IN_OFFICIAL_REFERENCE_ROOM",
    ):
        raise ValueError("Unknown rotating geometry provenance")
    root=_valid_job_root(job_id)
    folder=root/"case"/"constant"/"triSurface"
    sources=[p for p in (folder/"fan.stl.gz",folder/"fan.stl") if p.is_file()]
    if len(sources)!=1:
        raise ValueError("Original rotor fan.stl(.gz) absent or ambiguous")
    data=read_stl_payload(sources[0])
    digest=sha256(data).hexdigest()
    if kind=="USER_STEP_ROTOR_IN_OFFICIAL_REFERENCE_ROOM":
        if digest!=state.get("verified_mesh_input_rotor_stl_sha256"):
            raise ValueError("Original STEP rotor SHA mismatch with CFD mesh input")
    dict_path=root/"case"/"constant"/"dynamicMeshDict"
    if not dict_path.is_file():
        raise ValueError("Original rotatingMotion dictionary missing")
    origin,axis=source_motion(dict_path.read_text(encoding="utf-8"))
    return {
        "triangles":sample_stl(data),
        "origin_m":origin,"axis":axis,
        "sha256":digest,"source":str(sources[0].relative_to(root)),
        "rpm":float(state["controls"]["rpm"]),
    }


def rigid_loop(triangles:np.ndarray,*,origin:np.ndarray,axis:np.ndarray,
               rpm:float,count:int=FRAMES):
    tri=np.asarray(triangles,dtype=float)
    origin=np.asarray(origin,dtype=float)
    axis=np.asarray(axis,dtype=float)
    if (tri.ndim!=3 or tri.shape[1:]!=(3,3) or not 1<=len(tri)<=800
            or origin.shape!=(3,) or axis.shape!=(3,)
            or not 100<=rpm<=2400 or not 13<=count<=73
            or not all(np.isfinite(x).all() for x in (tri,origin,axis))):
        raise ValueError("Invalid source rigid rotor request")
    length=np.linalg.norm(axis)
    if length<=1e-9:
        raise ValueError("Zero rotor axis")
    unit=axis/length
    flat=tri.reshape(-1,3)-origin
    cross=np.cross(unit,flat)
    dot=(flat@unit)[:,None]
    times=np.linspace(0,60/rpm,count)
    positions=[]
    for t in times:
        angle=2*np.pi*rpm*t/60
        rotated=origin+flat*np.cos(angle)+cross*np.sin(angle)+unit[None,:]*dot*(1-np.cos(angle))
        positions.append(rotated)
    return times,np.stack(positions)


def make_loop_html(source:dict,actual:dict) -> str:
    """Offline JS loop of real rotor with frozen last genuinely solved U/p."""
    import plotly.graph_objects as go
    tri=source["triangles"]
    times,vertices=rigid_loop(
        tri,origin=source["origin_m"],axis=source["axis"],rpm=source["rpm"]
    )
    xyz=np.asarray(actual["sample_points"],dtype=float)
    vel=np.asarray(actual["velocity_m_s"],dtype=float)
    pressure=np.asarray(actual["kinematic_pressure_m2_s2"],dtype=float)
    if (xyz.ndim!=3 or xyz.shape!=vel.shape or
            pressure.shape!=xyz.shape[:2] or xyz.shape[0]<2 or
            not all(np.isfinite(q).all() for q in (xyz,vel,pressure))):
        raise ValueError("Verified source CFD U/p arrays required")
    last=-1
    points=xyz[last]
    speed=np.linalg.norm(vel[last],axis=1)
    p=pressure[last]
    extent=max(float(np.max(np.linalg.norm(tri.reshape(-1,3)-source["origin_m"],axis=1))),.04)
    close=np.max(np.abs(points-source["origin_m"]),axis=1)<max(extent*2,.4)
    if close.sum()>=15:
        points,speed,p=points[close],speed[close],p[close]
    cloud=go.Scatter3d(
        x=points[:,0],y=points[:,1],z=points[:,2],mode="markers",
        marker=dict(size=3,color=speed,colorscale="Turbo",cmin=0,
                    cmax=max(float(np.percentile(speed,99)),1e-8),
                    colorbar=dict(title="|U| m/s"),opacity=.75),
        customdata=np.column_stack([speed,p]),
        hovertemplate="|U|=%{customdata[0]:.3f} m/s, p=%{customdata[1]:.4f} m²/s²<extra>Actual frozen solver snapshot</extra>",
        name="Solved U/p snapshot (held)",
    )
    cells=np.arange(vertices.shape[1]).reshape(-1,3)
    def blade(k):
        frame=vertices[k]
        return go.Mesh3d(
            x=frame[:,0],y=frame[:,1],z=frame[:,2],
            i=cells[:,0],j=cells[:,1],k=cells[:,2],
            color="#13afba",flatshading=True,opacity=1,
            lighting=dict(ambient=.7,diffuse=.75,roughness=.4),
            name="Original source STL rotor, geometry-only",
            hovertemplate="Actual rotating STL geometry<extra>No intermediate CFD field</extra>",
        )
    fig=go.Figure(
        data=[cloud,blade(0)],
        frames=[go.Frame(name=str(k),traces=[1],data=[blade(k)])
                for k in range(1,len(times))],
    )
    centre=source["origin_m"]
    rad=extent*1.7
    fig.update_layout(
        height=550,margin=dict(l=0,r=0,t=50,b=0),
        title="Continuous original blade rotation + held real CFD snapshot",
        scene=dict(
            xaxis=dict(title="X (m)",range=[centre[0]-rad,centre[0]+rad]),
            yaxis=dict(title="Y (m)",range=[centre[1]-rad,centre[1]+rad]),
            zaxis=dict(title="Z (m)",range=[centre[2]-rad,centre[2]+rad]),
            aspectmode="cube",
        ),
    )
    snippet=fig.to_html(
        include_plotlyjs=True,full_html=False,div_id="ff-real-rotor",
        config={"displaylogo":False,"responsive":True}
    )
    # Transport numerical source data only. No user HTML or source STL text
    # becomes executable JS. The geometrical transformation is Rodrigues
    # rotation around the axis read from the solved OpenFOAM dictionary.
    import json
    rotor_data=json.dumps({
        "x":vertices[0,:,0].tolist(),
        "y":vertices[0,:,1].tolist(),
        "z":vertices[0,:,2].tolist(),
        "origin":np.asarray(source["origin_m"],dtype=float).tolist(),
        "axis":np.asarray(source["axis"],dtype=float).tolist(),
        "frames_per_turn":FRAMES-1,
    },separators=(",",":"))
    js="""<div style="font:13px system-ui;color:#475569">
<button id="ff-start">Play continuous rotor</button>
<button id="ff-stop">Pause rotor</button>
 <span id="ff-rotor-label">Real STL geometry, slowed playback · U/p snapshot held</span>
</div>
<script>
(function(){
 const plot=document.getElementById("ff-real-rotor");
 const data=__ROTOR_DATA__;
 const cx=data.origin[0],cy=data.origin[1],cz=data.origin[2];
 const ax=data.axis[0],ay=data.axis[1],az=data.axis[2];
 const N=data.x.length, segments=data.frames_per_turn;
 let active=false, index=0, token=0, steps=0, minX=Infinity, maxX=-Infinity;
 const label=document.getElementById("ff-rotor-label");
 async function step(t){
   if(!active||t!==token) return;
   const theta=2*Math.PI*(index+1)/segments;
   const cs=Math.cos(theta), sn=Math.sin(theta), omc=1-cs;
   const x=new Array(N),y=new Array(N),z=new Array(N);
   for(let j=0;j<N;j++){
     const px=data.x[j]-cx,py=data.y[j]-cy,pz=data.z[j]-cz;
     const dot=ax*px+ay*py+az*pz;
     x[j]=cx+px*cs+(ay*pz-az*py)*sn+ax*dot*omc;
     y[j]=cy+py*cs+(az*px-ax*pz)*sn+ay*dot*omc;
     z[j]=cz+pz*cs+(ax*py-ay*px)*sn+az*dot*omc;
   }
   try{
     await Plotly.restyle(plot,{x:[x],y:[y],z:[z]},[1]);
   }catch(error){
     active=false;
     label.textContent="Rotor 3D rendering stopped: "+String(error);
     return;
   }
   if(!active||token!==t) return;
   index=(index+1)%segments;
   steps+=1;
   minX=Math.min(minX,x[0]);
   maxX=Math.max(maxX,x[0]);
   plot.dataset.ffRotorSteps=String(steps);
   plot.dataset.ffRotorMinX=String(minX);
   plot.dataset.ffRotorMaxX=String(maxX);
   plot.dataset.ffRotorCycle=String(Math.floor(steps/segments));
   label.textContent="Source STL · loop "+Math.floor(steps/segments)+
       " · kinematic frame "+(index+1)+"/"+segments+
       " · U/p fixed at last genuine solver write";
   window.setTimeout(function(){step(t);},65);
 }
 document.getElementById("ff-start").onclick=function(){
   if(active) return;
   active=true;token+=1;step(token);
 };
 document.getElementById("ff-stop").onclick=function(){
   active=false;token+=1;
   label.textContent="Paused · source STL geometry / verified U/p snapshot";
 };
})();
</script>""".replace("__ROTOR_DATA__",rotor_data)
    measured_times=actual.get("physical_time_s")
    timestamp=(f"{float(measured_times[-1]):.6f} s"
               if measured_times is not None else "last verified VTK record")
    note=(
        f"Actual STL SHA {source['sha256'][:16]} · {source['rpm']:g} RPM · "
        f"real U/p held at {timestamp}. No computed fields between solver frames."
    )
    return snippet+js+"<p style='font:12px system-ui;color:#64748b'>"+note+"</p>"
