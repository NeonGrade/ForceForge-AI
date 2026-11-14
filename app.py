"""ForceForge X | real physical specimen and independently published measurements.

This is the primary entry point of the engineering platform. Other industrial
scenarios remain accessible under Industry Explorer and Engineering Workspace.
"""
from __future__ import annotations
from dataclasses import asdict
from io import BytesIO
from pathlib import Path
import json
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from forceforge.modal_benchmark import (
    LENGTH_M, WIDTH_M, THICKNESS_M, SENSOR_HEIGHTS_M, MEASURED_HZ,
    PUBLISHED_FE_HZ, PUBLISHED_MAC, solve_modes, solve_static,
    fit_base_stiffness, frequency_comparison, holdout_mape,
    prism_surface, read_abaqus_inp,
)

ROOT=Path(__file__).resolve().parent
STL=ROOT/'assets/benchmark/hannover_steel_beam_reconstructed_ascii.stl'
STEP=ROOT/'assets/benchmark/hannover_steel_beam_reconstructed.step'
SOURCE_DATA='https://data.uni-hannover.de/en/dataset/a-benchmark-structure-for-virtual-sensing-on-tower-structures'
SOURCE_PAPER='https://wes.copernicus.org/articles/11/3359/2026/index.html'
SOURCE_INP='https://data.uni-hannover.de/dataset/3aceac8e-e8ee-4497-8ea1-90acaa57dda0/resource/39842a05-385c-4b39-ad3e-306bc95c9675/download/beam_model.inp'

st.set_page_config(page_title='ForceForge X · Real Experiment',page_icon='🔬',layout='wide',initial_sidebar_state='expanded')
st.markdown('''
<style>
.block-container{max-width:1280px;padding-top:1.5rem;padding-bottom:3rem}
[data-testid="stSidebar"]{background:#f6f8fa}
.ff-overline{color:#0b7d85;font-weight:700;font-size:.75rem;letter-spacing:.11em}
.ff-h1{font-size:2.55rem;font-weight:800;line-height:1.10;color:#163745;margin:5px 0 12px}
.ff-p{color:#4f6471;font-size:1.07rem;line-height:1.5;max-width:890px}
</style>
''',unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def _solve(log10k:float,E_gpa:float,rho:float,n:int,gauges:bool):
    return solve_modes(base_stiffness_nm_rad=10**log10k,E_pa=E_gpa*1e9,
                       rho_kg_m3=rho,n_elements=n,reduce_gauges=gauges)

@st.cache_data(show_spinner=False)
def _fitted(E_gpa:float,rho:float,n:int,gauges:bool):
    return fit_base_stiffness(E_pa=E_gpa*1e9,rho_kg_m3=rho,
                              n_elements=n,reduce_gauges=gauges)


def set_calibration():
    # This callback executes before the new Streamlit widget pass.
    k,_=_fitted(st.session_state['lab_E'],st.session_state['lab_rho'],
                st.session_state['lab_n'],st.session_state['lab_gauges'])
    st.session_state['lab_logk']=float(np.log10(k))
    st.session_state['lab_fitted']=True


def manual_change():
    st.session_state['lab_fitted']=False


def plot_beam(z_m:np.ndarray,w_m:np.ndarray,*,mode_label:str):
    nodes,faces,colors=prism_surface(z_m,w_m)
    f=go.Figure()
    f.add_trace(go.Mesh3d(x=nodes[:,0]*1e3,y=nodes[:,1]*1e3,z=nodes[:,2]*1e3,
        i=faces[:,0],j=faces[:,1],k=faces[:,2],intensity=colors,
        colorscale=[[0,'#2a718a'],[1,'#f49f55']],flatshading=False,
        lighting={'ambient':.55,'diffuse':.7,'specular':.3},
        showscale=False,hovertemplate='Height %{z:.1f} mm<extra>Steel beam surface</extra>',
        name='Reconstructed 3D specimen'))
    f.add_trace(go.Scatter3d(x=np.zeros(len(z_m)),y=np.zeros(len(z_m)),z=z_m*1e3,
        mode='lines',line={'color':'#9cabb3','dash':'dash','width':4},name='Undeformed centreline'))
    f.add_trace(go.Scatter3d(x=w_m*1e3,y=np.zeros(len(z_m)),z=z_m*1e3,
        mode='lines',line={'color':'#d35242','width':6},name=mode_label))
    heights=np.array(list(SENSOR_HEIGHTS_M.values()))
    labels=list(SENSOR_HEIGHTS_M.keys())
    offsets=np.interp(heights,z_m,w_m)*1e3
    f.add_trace(go.Scatter3d(x=offsets,y=np.full(5,27.),z=heights*1e3,
        mode='markers+text',text=labels,textposition='middle right',
        marker={'size':6,'color':['#e48d3e']*3+['#40a6a1']*2},
        hovertemplate='Measurement point %{text}: %{z:.0f} mm<extra>Published sensor location</extra>',
        name='Published measurement points'))
    f.update_layout(height=575,margin={'l':0,'r':0,'t':10,'b':0},
        scene={'xaxis_title':'Lateral motion (mm)','yaxis_title':'Width (mm)',
               'zaxis_title':'Height (mm)',
               'xaxis':{'range':[-100,100]},
               'yaxis':{'range':[-35,45]},
               'zaxis':{'range':[-60,1570]},
               'aspectmode':'manual','aspectratio':{'x':.70,'y':.42,'z':2.5},
               'camera':{'eye':{'x':1.7,'y':1.3,'z':1.2}}},
        showlegend=True,legend={'orientation':'h','yanchor':'bottom','y':1.0,'x':0})
    return f

with st.sidebar:
    st.markdown('### ForceForge X')
    st.caption('Real Experiment · Model Validation')
    st.markdown('**Explore applications**')
    st.page_link('pages/9_Industry_Explorer.py',label='Building / Industrial / Automotive',icon='🏗️')
    st.markdown('**Engineering tools**')
    st.page_link('pages/7_Engineering_Workbench.py',label='Structural optimization & ML',icon='📈')
    st.page_link('pages/5_Advanced_Structural_Lab.py',label='Advanced thermal / joint mechanics',icon='⚙️')
    st.divider()
    st.markdown('**Model controls**')
    if 'lab_logk' not in st.session_state:st.session_state['lab_logk']=3.0
    if 'lab_fitted' not in st.session_state:st.session_state['lab_fitted']=False
    logk=st.slider('Base rotational stiffness, log10(N·m/rad)',0.0,6.0,step=.05,
                   key='lab_logk',on_change=manual_change)
    view=st.radio('3D visualization',['Natural vibration','Lateral loading'],horizontal=False)
    mode=st.selectbox('Vibration mode',[1,2,3],disabled=view!='Natural vibration')
    amplitude=st.slider('Visual mode-shape amplitude (mm)',5,65,28,1,
                         disabled=view!='Natural vibration')
    lateral_force=st.slider('Illustrative lateral tip load (N)',.05,1.0,.30,.05,
                             disabled=view!='Lateral loading')
    deformation_factor=st.slider('Static displacement display exaggeration',1,30,15,
                                  disabled=view!='Lateral loading')
    with st.expander('Advanced material / discretization assumptions'):
        E_gpa=st.number_input('Assumed Young modulus (GPa)',150.,240.,210.,5.,key='lab_E')
        density=st.number_input('Assumed steel density (kg/m³)',6500.,8500.,7850.,50.,key='lab_rho')
        elements=st.select_slider('Beam finite elements',[16,24,32,48,64],value=32,key='lab_n')
        reduce_gauges=st.checkbox('Model reduced thickness at strain gauges',value=True,key='lab_gauges')
    st.caption('The paper documents geometry and measured frequencies. The E and density inputs here are assumed, not certified specimen tests.')

st.markdown('<div class="ff-overline">PHYSICALLY MEASURED LABORATORY BENCHMARK · CC BY</div>',unsafe_allow_html=True)
st.markdown('<div class="ff-h1">Can an FEA model predict a real steel beam?</div>',unsafe_allow_html=True)
st.markdown('<div class="ff-p">Rotate a reconstructed 3D test specimen, adjust its support stiffness, and compare our independently calculated natural frequencies against published laboratory measurements.</div>',unsafe_allow_html=True)
st.caption('Leibniz University Hannover · Thurn et al. (2025/2026). Real measured frequencies; reconstructed geometry and our own reduced-order FEA. No safety approval is implied.')

try:
    result=_solve(logk,E_gpa,density,elements,reduce_gauges)
except Exception as error:
    st.error(f'Finite-element calculation failed: {error}')
    st.stop()

with st.container():
    m1,m2,m3,m4=st.columns(4)
    m1.metric('Actual specimen free length','1.524 m')
    m2.metric('Measured first frequency','1.569 Hz')
    m3.metric('Our FE first frequency',f'{result.frequencies_hz[0]:.3f} Hz')
    m4.metric('First-mode deviation',f'{100*(result.frequencies_hz[0]/MEASURED_HZ[0]-1):+.2f}%')

st.divider()
a,b=st.columns([1.65,1],gap='large')
with a:
    st.subheader('1 · Explore the documented physical specimen')
    if view=='Natural vibration':
        shape=result.transverse_shapes[:,mode-1]*amplitude/1000
        tag=f'Normalized FE mode B{mode}x (visual amplitude only)'
    else:
        _,w,_,_,_ = solve_static(tip_force_n=lateral_force,n_elements=elements,
                        E_pa=E_gpa*1e9,rho_kg_m3=density,
                        base_stiffness_nm_rad=10**logk,reduce_gauges=reduce_gauges)
        shape=w*deformation_factor
        tag=f'Calculated static lateral shape ×{deformation_factor}'
    st.plotly_chart(plot_beam(result.heights_m,shape,mode_label=tag),use_container_width=True)
    st.caption('Rotate / zoom the 3D model. Beam thickness and sensor elevations are reconstructed from the published article; visualization displacement is exaggerated. Not the original Abaqus solid model.')
with b:
    st.subheader('Physical specimen data')
    st.write('**Measured laboratory steel beam**')
    st.write('- 1,524 mm free length')
    st.write('- 30 × 5.2 mm rectangular section')
    st.write('- 5.0 mm reduced thickness near strain gauge regions')
    st.write('- 600 Hz measurement sampling')
    st.write('**Published measurement points**')
    points=pd.DataFrame([{'Point':k,'Height (mm)':int(round(v*1000)),
                          'Sensor':'Accelerometer / laser' if k in ('MP1','MP2','MP3') else 'Strain gauge'}
                           for k,v in SENSOR_HEIGHTS_M.items()])
    st.dataframe(points,hide_index=True,use_container_width=True)
    st.markdown('**Real geometry files you can inspect in CAD:**')
    if STEP.exists():
        st.download_button('Download reconstructed STEP',STEP.read_bytes(),
                           'hannover_steel_beam_reconstructed.step',mime='application/step',use_container_width=True)
    if STL.exists():
        st.download_button('Download reconstructed STL',STL.read_bytes(),
                           'hannover_steel_beam_reconstructed.stl',mime='model/stl',use_container_width=True)
    st.caption('STEP/STL geometry is our documented reconstruction. Sensor packages, magnets and precise clamps are omitted.')
    st.link_button('Open original experiment / Abaqus model',SOURCE_DATA,use_container_width=True)

st.divider()
st.subheader('2 · Compare our FEA with physical measurements')
real=pd.DataFrame(frequency_comparison(result.frequencies_hz))
fig=go.Figure()
fig.add_bar(name='Measured in physical lab',x=real['Mode'],y=real['Measured (Hz)'],marker_color='#1a8382')
fig.add_bar(name='Our simplified FEM',x=real['Mode'],y=real['Our reduced FEM (Hz)'],marker_color='#d78b4a')
fig.add_bar(name='Published updated Abaqus model',x=real['Mode'],y=real['Published Abaqus FE (Hz)'],marker_color='#869ba8')
fig.update_layout(barmode='group',height=360,margin=dict(l=10,r=10,t=10,b=35),yaxis_title='Natural frequency (Hz)')
st.plotly_chart(fig,use_container_width=True)
st.dataframe(real.style.format({'Measured (Hz)':'{:.3f}','Our reduced FEM (Hz)':'{:.3f}',
    'Published Abaqus FE (Hz)':'{:.3f}','Our error (%)':'{:+.2f}',
    'Published FE error (%)':'{:+.2f}'}),hide_index=True,use_container_width=True)
st.caption('Measured and published Abaqus frequencies come from Table 2 of Thurn et al. (2026). Our FEM results are computed live. The author model uses different physics and calibration objectives; lower frequency errors alone do not establish greater general validity.')

st.subheader('3 · Calibrate one parameter, validate on unseen modes')
st.markdown('**Test the scientific claim:** Use only measured Mode 1 to estimate an effective support stiffness. Then evaluate Mode 2 and Mode 3 as held-out laboratory references.')
if st.button('Calibrate using measured Mode 1',on_click=set_calibration,type='primary',use_container_width=True):
    pass
fit_k,fitted=_fitted(E_gpa,density,elements,reduce_gauges)
if np.isclose(10**logk,fit_k,rtol=1e-4):
    valid=holdout_mape(result)
    r1,r2,r3=st.columns(3)
    r1.metric('Fitted effective support stiffness',f'{fit_k:.1f} N·m/rad')
    r2.metric('Mode 2 held-out error',f'{100*(result.frequencies_hz[1]/MEASURED_HZ[1]-1):+.2f}%')
    r3.metric('Mode 3 held-out error',f'{100*(result.frequencies_hz[2]/MEASURED_HZ[2]-1):+.2f}%')
    st.success(f'Independent held-out modal frequency MAPE (Modes 2 & 3): {valid:.2f}%.')
    st.caption('Effective support stiffness is fitted to Mode 1 and is not a directly measured physical joint property. The published model includes sensors and other effects absent from this beam formulation.')
else:
    st.info(f'Calibration target produces kθ ≈ {fit_k:.1f} N·m/rad under the current simplifying assumptions. Click Calibrate to update the 3D model and compute held-out errors.')

with st.expander('4 · Import original institutional Abaqus .inp or raw MATLAB .mat data'):
    st.markdown('The university publishes an original Abaqus ".inp" file and an experimental MATLAB measurement file. You can download the originals from the source page and load them here. Unrecognized channel names are not silently treated as displacement or strain.')
    uploaded_inp=st.file_uploader('Import original Abaqus model (.inp)',type=['inp'],key='original_inp')
    if uploaded_inp is not None:
        model=read_abaqus_inp(uploaded_inp.getvalue().decode('utf-8',errors='replace'))
        st.write(f'Parsed {model["node_count"]:,} nodes, {model["element_count"]:,} element records. Element types: {model["types"] or "not identified"}.')
        st.caption('Connectivity preview only; Abaqus assembly transforms, material assignments and boundary conditions are NOT automatically solved.')
        if model['nodes']:
            n=list(model['nodes'].items())
            stride=max(1,len(n)//4000)
            xyz=np.array([v for _,v in n[::stride]])
            preview=go.Figure(go.Scatter3d(x=xyz[:,0],y=xyz[:,1],z=xyz[:,2],mode='markers',marker={'size':2,'color':'#26809f'}))
            preview.update_layout(height=350,scene={'aspectmode':'data'},margin={'l':0,'r':0,'t':0,'b':0})
            st.plotly_chart(preview,use_container_width=True)
    uploaded_mat=st.file_uploader('Import real laboratory MATLAB signal (.mat)',type=['mat'],key='lab_mat')
    if uploaded_mat is not None:
        try:
            from scipy.io import loadmat
            raw=loadmat(BytesIO(uploaded_mat.getvalue()),squeeze_me=True,struct_as_record=False)
            metadata=[{'Variable':k,'Shape':str(np.shape(v)),'Dtype':str(getattr(v,'dtype',type(v)))}
                      for k,v in raw.items() if not k.startswith('__')]
            st.dataframe(pd.DataFrame(metadata),hide_index=True,use_container_width=True)
            signals={k:v.ravel() for k,v in raw.items() if not k.startswith('__') and
                     isinstance(v,np.ndarray) and v.ndim==1 and
                     np.issubdtype(v.dtype,np.number) and len(v)>=20}
            if signals:
                channel=st.selectbox('Preview an imported numeric channel (not automatically calibrated)',list(signals))
                arr=np.asarray(signals[channel],float)
                stride=max(1,len(arr)//2000)
                st.line_chart(pd.DataFrame({'Sample index':np.arange(0,len(arr),stride),
                                            'Imported value (original units)':arr[::stride]}).set_index('Sample index'))
                st.caption('Axis uses sample index; physical units/channel alignment must be confirmed from the dataset README before any FE-vs-measurement error is reported.')
            else:
                st.info('MAT file imported. Signals appear nested; mapping requires the dataset variable documentation.')
        except NotImplementedError:
            st.warning('This MATLAB file uses HDF5 v7.3; convert to a documented CSV with the original variable labels before importing.')
        except Exception as exc:
            st.error(f'MAT import could not be parsed safely: {exc}')

st.divider()
with st.expander('Traceability, limitations, original sources'):
    st.markdown('**Published measured data:** Mode frequencies, sensor elevations, and specimen geometry from Thurn et al., Wind Energy Science (2026), CC BY 4.0.')
    st.markdown('**Original lab data and author .inp:** Thurn, Jonscher & Rolfes (2025), CC BY 3.0; DOI 10.25835/lyav246d.')
    st.markdown('**Our changes:** rectangular STEP reconstruction with thin gauge regions; independent Euler–Bernoulli modal solver and support-stiffness calibration. The original Abaqus .inp is offered via source link and is not included by default.')
    st.warning('Remaining validation gaps: unknown precise sensor/magnet point masses, E and density assumed, reduced-order beam theory, no physical fatigue qualification, no 3D joint/contact model, no actual structural certification.')
    st.link_button('Read peer-reviewed source article',SOURCE_PAPER)
    st.link_button('Access raw university dataset',SOURCE_DATA)

st.caption('ForceForge X · real experiment correlation | user-adjustable physics | measured data cited | NO safety certification')
