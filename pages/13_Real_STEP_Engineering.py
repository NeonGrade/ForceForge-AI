"""Real STEP import, volumetric tetra FEA and externally traceable CAD revision."""
from __future__ import annotations
from hashlib import sha256
import json
import urllib.request
import streamlit as st
import numpy as np
from forceforge.step_mesh import mesh_step_bytes, generated_bracket_step, NIST_BRIDGE_URL, NIST_DATASET_DOI, MAX_CAD_BYTES, NIST_PINNED_SHA256
from forceforge.cad_solid import CadLoad, solve_cad_mesh
from forceforge.solid3d import surface_figure

st.set_page_config(page_title='ForceForge X | Real STEP to 3D FEA',page_icon='🧩',layout='wide')
st.title('Real CAD → 3D Solid FEA → Design Revision')
st.write('Import real STEP BRep geometry, discretize its actual solid volume, apply controlled boundary conditions and compute a full 3D stress field. The same calculations can compare a second CAD revision.')
st.caption('Single watertight solid only · linear isotropic elasticity · NO inferred bolt/contact details · NO actual engineering certification')
with st.sidebar:
    st.markdown('### CAD source')
    selection=st.radio('Choose model', ['NIST original bridge STEP','Editable 3D L-bracket','Upload your STEP'], index=1)
    st.caption('NIST original is a real, published IN718 additive-manufacturing specimen; L-bracket is a newly generated CAD test model.')
    mesh_size=st.slider('Target tetra size (mm)',2.,15.,5.,1.)
    st.caption('For complex NIST thin walls a coarse tetra mesh may not satisfy the geometry volume guard; invalid/oversize meshes are rejected.')
    st.divider()
    force=st.slider('Applied transverse force (N)',20,2000,250,10)
    direction=st.selectbox('Load direction', ['+X','-X','+Y','-Y'])
    boundary=st.selectbox('Base-to-tip direction', ['Z','X','Y'])
    st.caption('All nodes on the minimum-coordinate boundary face are clamped. Uniform traction is imposed on the maximum-coordinate face. Confirm physical relevance.')
    st.divider()
    E=st.number_input('Assumed Young modulus (GPa)',min_value=10.,max_value=400.,value=200.,step=10.)
    nu=st.number_input('Assumed Poisson ratio',min_value=.10,max_value=.45,value=.29,step=.01)
    yield_mpa=st.number_input('Assumed yield limit (MPa)',min_value=10.,max_value=1800.,value=900.,step=50.)
    rho=st.number_input('Assumed density (kg/m³)',min_value=1000.,max_value=20000.,value=8190.,step=100.)

@st.cache_data(show_spinner=False)
def _generated(web):
    return generated_bracket_step(web_mm=float(web))

@st.cache_data(show_spinner=False)
def _mesh(blob,source,mesh_size,unit):
    return mesh_step_bytes(blob,source_label=source,mesh_size_mm=mesh_size,unit=unit,max_tets=5000)

@st.cache_data(show_spinner=False)
def _solve(mesh,case):
    return solve_cad_mesh(mesh,case)

source=None;name=None;unit='mm';web=None
if selection=='NIST original bridge STEP':
    st.markdown('**NIST AMB2022-01** · actually manufactured nickel-alloy bridge geometry (75 mm long, hollow features and measurement tabs).')
    st.markdown(f'[Official NIST original STEP]({NIST_BRIDGE_URL}) · [Dataset DOI](https://doi.org/{NIST_DATASET_DOI})')
    if st.button('Fetch original STEP from NIST (one-time download)',type='primary'):
        try:
            with st.spinner('Retrieving NIST official file; network access required...'):
                req=urllib.request.Request(NIST_BRIDGE_URL,headers={'User-Agent':'ForceForge-X-research/0.8'})
                with urllib.request.urlopen(req,timeout=35) as answer:
                    raw=answer.read(MAX_CAD_BYTES+1)
                if len(raw)>MAX_CAD_BYTES:
                    raise ValueError('NIST CAD file exceeds 32 MiB upload limit')
                if sha256(raw).hexdigest()!=NIST_PINNED_SHA256:
                    raise ValueError('NIST original STEP SHA-256 differs from the independently verified source; do not silently replace geometry')
                st.session_state['nist_step_blob']=raw
        except Exception as exc:
            st.error(f'NIST download unsuccessful: {exc}. Download manually from NIST and choose Upload your STEP.')
    source=st.session_state.get('nist_step_blob')
    name='NIST AMB2022-01 original STEP'
elif selection=='Editable 3D L-bracket':
    st.info('An original editable CAD demonstration bracket with mounting holes. It is NOT a physically measured NIST specimen.')
    web=st.select_slider('Vertical web thickness (mm)',options=[8,10,12,14],value=8)
    source=_generated(web)
    name=f'Generated L-bracket / web {web} mm'
else:
    uploaded=st.file_uploader('Upload permission-cleared STEP or STP',type=['step','stp'])
    if uploaded:
        source=uploaded.getvalue()
        name=uploaded.name
        unit=st.selectbox('Verify actual STEP coordinate units',['mm','m'])

if source is None:
    st.info('Choose the generated L-bracket, fetch the NIST STEP, or upload a STEP to begin.')
    st.stop()

sha=sha256(source).hexdigest()
st.caption(f'Source SHA-256: {sha} · {name}. Every FE result is associated with exact CAD hash and inputs.')
if selection=='NIST original bridge STEP':
    st.caption('Original NIST STEP hash pinned to the published data source; modified versions must be uploaded and reviewed separately.')
if selection=='Editable 3D L-bracket':
    st.download_button('Download current parametric STEP',data=source,
        file_name=f'forceforge_L_bracket_web_{web}mm.step',mime='application/step')
st.subheader('1 · Volume mesh from STEP')
try:
    with st.spinner('Importing BRep and tetrahedralizing the CAD solid...'):
        mesh=_mesh(source,name,float(mesh_size),unit)
except Exception as exc:
    st.error(f'CAD import / mesh rejected: {type(exc).__name__}: {exc}')
    st.stop()

m1,m2,m3,m4=st.columns(4)
m1.metric('Solid tetrahedra',f'{mesh.num_tets:,}')
m2.metric('Source CAD volume',f'{mesh.cad_volume_m3*1e9:,.0f} mm³')
m3.metric('Mesh / CAD volume difference',f'{mesh.relative_volume_difference*100:.2f}%')
m4.metric('Minimum shape-quality proxy',f'{mesh.min_shape_quality:.4f}')
st.caption('The STEP surface is meshed by Gmsh with straight-sided tetrahedra; midside FE displacement nodes yield tet10 elements. Narrow details/curvature need mesh-convergence checks.')

axis_index={'X':0,'Y':1,'Z':2}[boundary]
force_index={'X':0,'Y':1}[direction[-1]]
sign=1 if direction.startswith('+') else -1
try:
    case=CadLoad(force_n=float(force),force_axis=force_index,force_sign=sign,
                 boundary_axis=axis_index,E_pa=E*1e9,nu=nu,density=rho,yield_pa=yield_mpa*1e6)
except ValueError as exc:
    st.error(str(exc));st.stop()

st.subheader('2 · 3D stress / displacement')
try:
    with st.spinner('Assembling 3D tetra10 stiffness and solving sparse FE equations...'):
        result=_solve(mesh,case)
except Exception as exc:
    st.error(f'3D Solid FEA failed: {type(exc).__name__}: {exc}')
    st.stop()

c1,c2,c3,c4=st.columns(4)
c1.metric('Tip displacement',f'{result.tip_mm:.4f} mm')
c2.metric('Sampled peak von Mises',f'{result.peak_von_mises_mpa:.1f} MPa')
c3.metric('FE model member mass',f'{result.mass_kg:.3f} kg')
c4.metric('Reaction residual',f'{result.relative_reaction_residual:.2e}')
ratio=result.peak_von_mises_mpa/yield_mpa
if ratio>1:
    st.error(f'Computed elastic stress exceeds the assumed yield ({ratio:.2f}×). This is outside the elastic model validity.')
else:
    st.info(f'Sampled stress is {ratio*100:.1f}% of an illustrative yield limit. No real structural certification.')
visual=st.slider('Visual-only deformation multiplier',1,150,35,5)
st.plotly_chart(surface_figure(result,deformation_scale=visual),width='stretch',key='real_cad_solid')

st.subheader('3 · Re-mesh a revised CAD')
st.write('A revision is a SECOND actual STEP geometry, independently meshed and re-solved—not recoloring the first model.')
revision=None;revision_name=None
if selection=='Editable 3D L-bracket':
    revision_mm=st.select_slider('Proposed revised web thickness (mm)',options=[8,10,12,14],value=12)
    revision=_generated(revision_mm)
    revision_name=f'Generated revised bracket / {revision_mm} mm web'
else:
    revfile=st.file_uploader('Upload revised STEP geometry from CAD',type=['step','stp'],key='revised_step')
    if revfile:
        revision=revfile.getvalue();revision_name=revfile.name
if revision is not None and st.button('Re-mesh revised CAD and re-run 3D FEA',type='primary'):
    try:
        with st.spinner('Importing changed CAD, meshing and recomputing FE...'):
            mesh2=_mesh(revision,revision_name,float(mesh_size),unit)
            revised=_solve(mesh2,case)
        st.session_state['real_cad_revision']={
            'inputs':(sha,sha256(revision).hexdigest(),mesh_size,case),
            'result':revised,'source':revision,'label':revision_name}
    except Exception as exc:
        st.error(f'Revised STEP solve failed: {type(exc).__name__}: {exc}')
record=st.session_state.get('real_cad_revision')
valid=(sha,sha256(revision).hexdigest(),mesh_size,case) if revision is not None else None
if record is not None and record['inputs']!=valid:
    st.warning('Input CAD/loads changed. The old redesign result is hidden until re-solved.')
    record=None
if record is not None:
    new=record['result']
    same_cmax=1.01*max(result.peak_von_mises_mpa,new.peak_von_mises_mpa)
    d1,d2=st.columns(2)
    with d1:
        st.markdown('**Original STEP solid**')
        st.plotly_chart(surface_figure(result,deformation_scale=visual,stress_cmax_mpa=same_cmax),width='stretch',key='cad_before')
    with d2:
        st.markdown('**Revised STEP · independently meshed**')
        st.plotly_chart(surface_figure(new,deformation_scale=visual,stress_cmax_mpa=same_cmax),width='stretch',key='cad_after')
    st.caption(f'Identical 0–{same_cmax:.2f} MPa stress color scale. Tets: {mesh.num_tets} → {new.mesh.num_tets}.')
    st.write('FE member mass change:',f'{(new.mass_kg/result.mass_kg-1)*100:+.1f}%')
    st.write('Tip movement:',f'{result.tip_mm:.4f} → {new.tip_mm:.4f} mm')
    st.write('Sampled stress:',f'{result.peak_von_mises_mpa:.1f} → {new.peak_von_mises_mpa:.1f} MPa')
    st.download_button('Download revised STEP',record['source'],file_name='forceforge_redesigned.step',mime='application/step')
    audit={'original_sha256':sha,'revision_sha256':new.mesh.source_sha256,
           'source':name,'revised_source':record['label'],'force_n':case.force_n,
           'material':{'E_pa':E*1e9,'nu':nu,'rho':rho,'yield_mpa':yield_mpa},
           'original':{'mass_kg':result.mass_kg,'tip_mm':result.tip_mm,'stress_mpa':result.peak_von_mises_mpa},
           'revision':{'mass_kg':new.mass_kg,'tip_mm':new.tip_mm,'stress_mpa':new.peak_von_mises_mpa},
           'scope':'Unvalidated linear elastic use case, no code certification'}
    st.download_button('Download FE audit JSON',json.dumps(audit,indent=2),file_name='real_cad_fea_audit.json',mime='application/json')
with st.expander('Limits and evidence needed for real engineering approval'):
    st.markdown('**Numerically checked:** imported volume vs tetra mesh volume, 3D tetra10 stiffness, global reaction equilibrium and sampled Gauss stress.')
    st.markdown('**Not validated physically:** static loads, fixture geometry, actual material properties, bolt contact, plasticity, fatigue, static measured strain/displacement or converged local peak stress.')
    st.markdown('**NIST context:** Published additive-manufacturing thermal/distortion data do not validate this separate assumed static loading problem.')
    st.write('Imported bounding dimensions (mm):',np.round((mesh.bbox_m[1]-mesh.bbox_m[0])*1000,2))
