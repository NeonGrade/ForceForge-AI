"""Judge-focused design cycle: real-dimension CAD, FEM stress, automatic redesign.

The static solver is an Euler-Bernoulli *beam* FEM whose bending-stress field
is rendered on a dimension-faithful 3D surface; it is not a 3D solid FEA.
"""
from dataclasses import asdict, replace
import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from forceforge.beam_stress import (
    LENGTH_M, WIDTH_M, StaticCase, solve_static,
    displacement_at, axial_stress_at, thickness_at,
    redesign, plotly_surface,
)

st.set_page_config(page_title='ForceForge X | CAD-to-FEA Studio', page_icon='🛠️', layout='wide')
st.markdown('''<style>
.block-container {max-width:1300px;padding-top:1.6rem}
[data-testid="stSidebar"] {background:#f4f7fb}
.stMetricValue {font-size:1.55rem}
</style>''',unsafe_allow_html=True)

with st.sidebar:
    st.markdown('### ForceForge X / Simulation Studio')
    st.markdown('[← Back to measured benchmark](/)')
    st.caption('Model: documented 1.524 m laboratory steel beam')
    st.header('1. Apply the challenge')
    tip_load=st.slider('Tip side load (N)',.02,.40,.15,.01,
                       help='Illustrative simulated static point load; the study has real modal, not static-load validation.')
    thickness=st.slider('Thickness design factor',.75,1.50,1.00,.05,
                        help='1.00 = nominal reconstructed beam; alters both gauge and nominal thickness.')
    deflection_limit=st.slider('Allowable tip movement (mm)',.5,5.,2.,.25,
                               help='User-set illustrative service target, not a building or automotive code limit.')
    zoom=st.slider('Exaggerate deformation',1,70,30,1)
    st.divider()
    st.markdown('**Model validity**')
    st.caption('Real published specimen geometry and real modal frequencies; assumed E, density and static load.')
    st.caption('Euler–Bernoulli **1D beam FEM** with calculated bending stress mapped onto reconstructed 3D surface.')
    st.caption('No CFD, fluid forces, thermal flow or 3D solid stress solver in this page.')

st.title('CAD → Stress Map → Improved Design')
st.markdown('Rotate the 3D part, change its physical load, identify a modeled limit, then run a verified redesign.')
st.caption('Source specimen: Leibniz University Hannover (CC BY); CAD is our own reconstruction from published dimensions.')

case=StaticCase(force_n=tip_load,thickness_ratio=thickness,
                displacement_limit_mm=deflection_limit)
current=solve_static(case)

col1,col2,col3,col4=st.columns(4)
col1.metric('Tip movement',f'{current.tip_mm:.3f} mm')
col2.metric('Peak bending stress',f'{current.stress_max_mpa:.3f} MPa')
col3.metric('Member mass',f'{current.mass_kg:.3f} kg')
col4.metric('Displacement target used',f'{100*current.displacement_utilization:.0f}%')

if current.governing_utilization>1.0:
    st.error('MODEL LIMIT EXCEEDED: the calculated tip movement exceeds the chosen service displacement target. No physical specimen failed in an experiment.')
else:
    st.success('This modeled loading case is within the illustrative displacement and material-limit assumptions. This does not establish real service safety.')

left,right=st.columns([7,3])
with left:
    st.plotly_chart(plotly_surface(current,exaggeration=zoom),use_container_width=True)
    st.caption('Color = axial bending stress magnitude computed from the beam FE section forces. The surface is shown in 3D; the underlying stiffness model is 1D.')
with right:
    st.subheader('What is physically happening?')
    st.markdown('**Blue:** low calculated bending stress near the unloaded tip.\n\n**Yellow / magenta:** high relative stress nearer the fixed root or reduced-thickness gauge region.')
    st.metric('Support shear',f'{abs(current.support_reaction_n):.3f} N')
    st.metric('Support bending moment',f'{abs(current.support_reaction_nm):.3f} N·m')
    st.caption(f'Numerical equilibrium residual: {current.relative_equilibrium_residual:.2e} (normalized).')
    st.markdown('**Real measurement link**')
    st.write('Original experiment includes measured bending-mode frequencies and sensor locations; static stress in this tab is predicted and **not** measured.')

st.divider()
st.subheader('2. Generate a revised CAD section and re-run FEM')
st.write('The search varies the beam thickness, changes its section stiffness/mass, and recomputes displacements and stress for every candidate.')

if st.button('Find the lightest design that meets the modeled limits',type='primary',use_container_width=True):
    st.session_state['static_redesign']={'inputs':asdict(case),'output':redesign(case)}
result=st.session_state.get('static_redesign')
if result is not None:
    if result['inputs']!=asdict(case):
        st.warning('Inputs have changed since the last redesign. Press the redesign button to update the comparison.')
    optimum,search=result['output']
    st.caption(f'{len(search)} physically re-solved candidate thicknesses; constraints were assessed by the FEM for each.')
    if optimum is None:
        st.error('No feasible candidate in this thickness grid. Do not assume a design outside the search has passed.')
    else:
        before_mass=current.mass_kg
        st.subheader('Before and After')
        b1,b2,b3=st.columns(3)
        b1.metric('Thickness factor',f'{optimum.case.thickness_ratio:.2f}×')
        b2.metric('FE tip displacement',f'{optimum.tip_mm:.3f} mm')
        b3.metric('Mass change',f'{(optimum.mass_kg/before_mass-1)*100:+.1f}%')
        a,b=st.columns(2)
        with a:
            st.markdown('**Original**')
            st.plotly_chart(plotly_surface(current,exaggeration=zoom),use_container_width=True)
        with b:
            st.markdown('**Redesigned section — independently re-solved**')
            st.plotly_chart(plotly_surface(optimum,exaggeration=zoom),use_container_width=True)
        st.dataframe(pd.DataFrame({
            'Check':['Tip movement (mm)','Peak bending stress (MPa)','Mass (kg)','Modeled limit use (%)'],
            'Original':[current.tip_mm,current.stress_max_mpa,current.mass_kg,100*current.governing_utilization],
            'Improved':[optimum.tip_mm,optimum.stress_max_mpa,optimum.mass_kg,100*optimum.governing_utilization]
        }),hide_index=True,use_container_width=True)
        payload={'source':'Published Hannover beam geometry reconstructed from article; load simulated',
                 'validation':'Published modal frequencies are measured; static loading is NOT experimentally validated.',
                 'original':{**asdict(case),'tip_mm':current.tip_mm,'mass_kg':current.mass_kg},
                 'redesign':{'thickness_ratio':optimum.case.thickness_ratio,
                             'tip_mm':optimum.tip_mm,'max_stress_mpa':optimum.stress_max_mpa,
                             'mass_kg':optimum.mass_kg,'limit_utilization':optimum.governing_utilization}}
        st.download_button('Export before / after FE calculation (JSON)',
                           json.dumps(payload,indent=2),file_name='forceforge_static_redesign.json',
                           mime='application/json')

with st.expander('Engineering verification, experimental attribution and model limitations'):
    st.write('1.524 m × 30 mm × 5.2 mm nominal steel beam (5.0 mm at two reduced regions).')
    st.write('Euler-Bernoulli 2 DOF/node static bending FEM; 84 or more axial sections; unit tests against piecewise-section curvature integral and equilibrium.')
    st.write('E=210 GPa, density=7850 kg/m³ and yield=250 MPa are **assumed**, not independently tested steel data.')
    st.write('This page uses a hypothesized tip force and arbitrary service deflection target. Do not call this stress-map verified by the laboratory.')
    st.write('The real experiment in the main page validates first three natural frequencies; source DOI 10.5194/wes-11-3359-2026, data DOI 10.25835/lyav246d.')
    st.write('For 3D local holes, contact and plastic stresses, future work requires STEP → volume mesh → 3D solid FE solver and independent numerical/experimental checks.')

st.caption('ForceForge X · correct physical units and traceable beam FE stress field · not a production-design certification')
