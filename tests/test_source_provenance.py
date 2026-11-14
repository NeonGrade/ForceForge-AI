from hashlib import sha256
import pytest
from scripts.fetch_nist_step import parse_sha
from forceforge.step_mesh import _validate_step, NIST_BRIDGE_URL, NIST_DATASET_DOI


def test_nist_source_configuration_points_to_official_pdr():
    assert NIST_BRIDGE_URL.startswith('https://data.nist.gov/')
    assert NIST_BRIDGE_URL.lower().endswith('.step')
    assert NIST_DATASET_DOI=='10.18434/mds2-2607'


def test_publisher_checksum_reader_accepts_only_one_digest():
    h=sha256(b'official test bytes').hexdigest()
    assert parse_sha((h+'  published.step\n').encode())==h
    assert parse_sha(('SHA256 (file) = '+h+'\n').encode())==h
    with pytest.raises(ValueError,match='unique'):
        parse_sha(b'not a digest')
    with pytest.raises(ValueError,match='unique'):
        parse_sha((h+'\n'+h).encode())


def test_step_header_check_rejects_html_and_corrupt_input():
    with pytest.raises(ValueError):
        _validate_step(b'<!doctype html>'*20)
    _validate_step(b'ISO-10303-21;'+b' ' * 300)
