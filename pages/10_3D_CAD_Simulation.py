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

from forceforge.reliability import UncertaintyBox, evaluate_robust, search_robust

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
    st.plotly_chart(plotly_surface(current,exaggeration=zoom),width="stretch",key="current_surface_main")
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

if st.button('Find the lightest design that meets the modeled limits',type='primary',width="stretch"):
    st.session_state['static_redesign']={'inputs':asdict(case),'output':redesign(case)}
result=st.session_state.get('static_redesign')
if result is not None and result['inputs']!=asdict(case):
    st.warning('Inputs changed after the last redesign. The previous comparison is hidden to avoid mixing results from two loading conditions. Press the redesign button to recalculate.')
    result=None
if result is not None:
    optimum,search=result['output']
    st.caption(f'{len(search)} physically re-solved candidate thicknesses; constraints were assessed by the FEM for each.')
    if optimum is None:
        st.error('No feasible candidate in this thickness grid. Do not assume a design outside the search has passed.')
    else:
        before_mass=current.mass_kg
        st.subheader('Before and After')
        b1,b2,b3=st.columns(3)
        b1.metric('Redesigned thickness / reference',f'{optimum.case.thickness_ratio:.2f}×',
                  delta=f'{(optimum.case.thickness_ratio/case.thickness_ratio-1)*100:+.1f}% vs current design',
                  delta_color='off')
        b2.metric('FE tip displacement',f'{optimum.tip_mm:.3f} mm')
        b3.metric('Mass change',f'{(optimum.mass_kg/before_mass-1)*100:+.1f}%')
        before_state='EXCEEDS' if current.governing_utilization>1 else 'WITHIN'
        after_state='EXCEEDS' if optimum.governing_utilization>1 else 'WITHIN'
        st.markdown(
            f"**Modeled displacement target ({deflection_limit:.2f} mm):** "
            f"original {current.tip_mm:.3f} mm (**{before_state}** target) → "
            f"redesigned {optimum.tip_mm:.3f} mm (**{after_state}** target)."
        )
        shared_stress=max(current.stress_max_mpa,optimum.stress_max_mpa)*1.001
        x_extent=max(40.,1.25*(max(abs(current.tip_mm),abs(optimum.tip_mm))*zoom
                                 + max(current.case.thickness_ratio,optimum.case.thickness_ratio)*5.2/2))
        st.caption(
            f"Both 3D plots use the same 0–{shared_stress:.2f} MPa absolute stress color range, "
            "camera orientation and transverse axis range. The section aspect ratio and "
            "displacements are visually exaggerated; numerical coordinates are in mm."
        )
        a,b=st.columns(2)
        with a:
            st.markdown(f'**Original · {case.thickness_ratio:.2f}× reference thickness**')
            st.plotly_chart(plotly_surface(
                current,exaggeration=zoom,shared_stress_max_mpa=shared_stress,
                view_x_limit_mm=x_extent
            ),width="stretch",key="original_surface_comparison")
        with b:
            st.markdown(f'**Redesigned · {optimum.case.thickness_ratio:.2f}× reference thickness**')
            st.plotly_chart(plotly_surface(
                optimum,exaggeration=zoom,shared_stress_max_mpa=shared_stress,
                view_x_limit_mm=x_extent
            ),width="stretch",key="redesigned_surface_comparison")
        st.dataframe(pd.DataFrame({
            'Check':['Tip movement (mm)','Peak bending stress (MPa)','Mass (kg)','Modeled limit use (%)'],
            'Original':[current.tip_mm,current.stress_max_mpa,current.mass_kg,100*current.governing_utilization],
            'Improved':[optimum.tip_mm,optimum.stress_max_mpa,optimum.mass_kg,100*optimum.governing_utilization]
        }),hide_index=True,width="stretch")
        payload={'source':'Published Hannover beam geometry reconstructed from article; load simulated',
                 'validation':'Published modal frequencies are measured; static loading is NOT experimentally validated.',
                 'original':{**asdict(case),'tip_mm':current.tip_mm,'mass_kg':current.mass_kg},
                 'redesign':{'thickness_ratio':optimum.case.thickness_ratio,
                             'tip_mm':optimum.tip_mm,'max_stress_mpa':optimum.stress_max_mpa,
                             'mass_kg':optimum.mass_kg,'limit_utilization':optimum.governing_utilization}}
        st.download_button('Export before / after FE calculation (JSON)',
                           json.dumps(payload,indent=2),file_name='forceforge_static_redesign.json',
                           mime='application/json')

st.divider()
st.subheader('3. Test reliability before accepting the lightest design')
st.write(
    'A nominally feasible design can have almost no spare capacity. '
    'Challenge load, material stiffness and manufacturing thickness together; '
    'every limit below is recomputed using the beam FEM.'
)
r1,r2,r3=st.columns(3)
with r1:
    load_extra=st.slider('Possible additional load (%)',0,30,10,5,key='robust_load')
with r2:
    e_loss=st.slider('Possible stiffness reduction (%)',0,30,10,5,key='robust_modulus')
with r3:
    t_loss=st.slider('Possible thickness reduction (%)',0,10,5,1,key='robust_thickness')
box=UncertaintyBox(load_extra/100,e_loss/100,t_loss/100)
inputs_key=(asdict(case),asdict(box))

if st.button('Check worst-case margin and find a robust design',
             type='primary',width='stretch'):
    with st.spinner('Re-solving FEM at uncertainty corners and checking candidate sections...'):
        st.session_state['beam_robust']={
            'inputs':inputs_key,'output':search_robust(case,box)
        }
robust=st.session_state.get('beam_robust')
if robust is not None and robust['inputs']!=inputs_key:
    st.warning('These uncertainty or load inputs changed. Re-run the robust calculation before using the previous results.')
    robust=None
if robust is not None:
    search_result=robust['output']
    initial=search_result.check
    a1,a2,a3=st.columns(3)
    a1.metric('Current displacement · nominal',
              f'{initial.nominal.tip_mm:.3f} mm')
    a2.metric('Current displacement · worst case',
              f'{initial.worst.tip_mm:.3f} mm')
    a3.metric('Current worst-case limit usage',
              f'{initial.worst_utilization*100:.1f}%')
    if initial.passes:
        st.success('The current design passes all 8 sampled corners of this stated uncertainty box.')
    else:
        st.error(
            'The current design fails the modeled uncertainty envelope. '
            'A nominal pass is not enough to guarantee the chosen margin.'
        )
    if search_result.best is None:
        st.warning('No robustly feasible candidate exists within the selected section grid.')
    else:
        best=search_result.best
        wc=search_result.best_worst
        st.markdown('#### Robust redesign — FEA verified')
        b1,b2,b3=st.columns(3)
        b1.metric('Selected reference thickness',f'{best.case.thickness_ratio:.2f}×')
        b2.metric('Redesign · worst tip movement',f'{wc.tip_mm:.3f} mm')
        b3.metric('Redesign · worst limit usage',f'{wc.governing_utilization*100:.1f}%')
        st.caption(
            f'The nominal section mass changes by '
            f'{(best.mass_kg/current.mass_kg-1)*100:+.1f}% versus current design. '
            f'{search_result.feasible} of {search_result.tested} sampled sections '
            'satisfy all eight modeled uncertainty corners.'
        )
        fig=go.Figure()
        fig.add_bar(
            x=['Current · nominal','Current · worst','Robust redesign · worst'],
            y=[current.tip_mm,initial.worst.tip_mm,wc.tip_mm],
            marker_color=['#2d819f','#d36d57','#25866f']
        )
        fig.add_hline(y=deflection_limit,line_dash='dash',
                      line_color='#c24d4d',annotation_text='Chosen displacement limit')
        fig.update_layout(height=340,showlegend=False,
                          yaxis_title='FEA tip displacement (mm)',
                          margin=dict(l=4,r=4,t=10,b=20))
        st.plotly_chart(fig,width='stretch',key='robust_disp_comparison')
    st.caption(
        'Uncertainty values are user-assumed bounds, not measured distributions '
        'or calibrated reliability probabilities. The eight corners are exhaustive '
        'for this monotonic linear-elastic cantilever model only; manufacturing '
        'and joint uncertainty outside these parameters is not included.'
    )

with st.expander('Engineering verification, experimental attribution and model limitations'):
    st.write('1.524 m × 30 mm × 5.2 mm nominal steel beam (5.0 mm at two reduced regions).')
    st.write('Euler-Bernoulli 2 DOF/node static bending FEM; 84 or more axial sections; unit tests against piecewise-section curvature integral and equilibrium.')
    st.write('E=210 GPa, density=7850 kg/m³ and yield=250 MPa are **assumed**, not independently tested steel data.')
    st.write('This page uses a hypothesized tip force and arbitrary service deflection target. Do not call this stress-map verified by the laboratory.')
    st.write('The real experiment in the main page validates first three natural frequencies; source DOI 10.5194/wes-11-3359-2026, data DOI 10.25835/lyav246d.')
    st.write('For 3D local holes, contact and plastic stresses, future work requires STEP → volume mesh → 3D solid FE solver and independent numerical/experimental checks.')

st.caption('ForceForge X · correct physical units and traceable beam FE stress field · not a production-design certification')
