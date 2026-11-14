"""Real STEP mesh-sensitivity acceptance, Gmsh optional, Mac CI enabled."""
from hashlib import sha256
import pytest

pytest.importorskip("gmsh")
from forceforge.cad_solid import CadLoad
from forceforge.isolated_cad import (
    analyze_step_safely, generate_bracket_safely, MAX_INTERACTIVE_TETS,
)
from forceforge.mesh_verification import run_mesh_evidence


def test_real_drilled_bracket_3_resolution_volume_fe_screen():
    source = generate_bracket_safely(8)
    case = CadLoad(force_n=120, force_axis=0, boundary_axis=2)
    first = analyze_step_safely(
        source, source_label="8 mm real BRep bracket", mesh_size_mm=12,
        unit="mm", load=case,
    )
    evidence = run_mesh_evidence(
        source, first, source_label="8 mm real BRep bracket",
        unit="mm", solve_at=analyze_step_safely,
    )
    assert len(evidence.ordered_rows) == 3
    assert evidence.source_sha256 == sha256(source).hexdigest()
    assert [r.target_size_mm for r in evidence.ordered_rows] == [15.,12.,10.]
    assert all(r.tetrahedra <= MAX_INTERACTIVE_TETS
               for r in evidence.ordered_rows)
    assert all(r.reaction_residual < 1e-6
               for r in evidence.ordered_rows)
    assert evidence.decision in (
        "PRELIMINARY_GLOBAL_DISPLACEMENT_STABILITY",
        "MESH_SENSITIVE",
        "INCONCLUSIVE_REFINEMENT",
        "INSUFFICIENT_REFINEMENT",
    )
    assert "certify safety" in evidence.limitations
