"""Actual CAD rigid-body frame geometry never fabricates CFD fields."""
import numpy as np
import pytest

from forceforge.rotor_visual import sample_real_stl_triangles,rotating_triangle_frames


def sample():
    return (
        b"solid fan\n"
        b"facet normal 0 0 1\nouter loop\n"
        b"vertex 0.1 0 2.6\nvertex 0.2 0 2.6\n"
        b"vertex 0.1 0.1 2.6\n"
        b"endloop\nendfacet\n"
        b"endsolid fan\n"
    )


def test_geometry_rotation_preserves_blade_length_and_source_positions():
    tri=sample_real_stl_triangles(sample())
    t,positions=rotating_triangle_frames(
        tri,rpm=1500,duration_s=.04,center_m=(0,0,2.6),count=13,
    )
    assert len(t)==13
    assert positions.shape==(13,3,3)
    assert positions[0]==pytest.approx(tri.reshape(-1,3))
    # 1500 RPM -> one revolution in 0.04 seconds.
    assert positions[-1]==pytest.approx(positions[0],abs=1e-12)
    center=np.array([0,0,2.6])
    distances=np.linalg.norm(positions-center,axis=2)
    assert np.allclose(distances,distances[0][None,:])


def test_invalid_stl_and_unphysical_preview_rejected():
    with pytest.raises(ValueError,match="Actual ASCII"):
        sample_real_stl_triangles(b"pretend this is CFD")
    with pytest.raises(ValueError):
        rotating_triangle_frames(
            np.zeros((1,3,3)),rpm=5000,duration_s=.04,
        )
