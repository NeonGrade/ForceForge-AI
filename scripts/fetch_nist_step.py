"""Download official NIST STEP geometry and optionally verify publisher hash.

Never modifies the data file. Official source: DOI 10.18434/mds2-2607.
On network failure, use the direct NIST dataset link, not a fabricated CAD file.
"""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
import re
import urllib.request

from forceforge.step_mesh import (
    NIST_BRIDGE_URL, NIST_BRIDGE_HASH_URL, NIST_DATASET_DOI,
    MAX_CAD_BYTES, _validate_step
)

OUTPUT=Path('data/external/nist/AMB2022-01-AMMT-PartCAD.STEP')


def fetch_bytes(url: str) -> bytes:
    req=urllib.request.Request(url,headers={
        'User-Agent':'ForceForge-X-Open-Engineering-Research/0.8',
        'Accept':'application/octet-stream,text/plain,*/*'
    })
    with urllib.request.urlopen(req,timeout=45) as response:
        data=response.read(MAX_CAD_BYTES+1)
    if len(data)>MAX_CAD_BYTES:
        raise ValueError('Exceeded maximum CAD source size (32 MiB)')
    return data


def parse_sha(data:bytes) -> str:
    matches=re.findall(rb'(?i)\b[a-f0-9]{64}\b',data)
    if len(matches)!=1:
        raise ValueError('Publisher hash file did not contain a unique SHA-256 digest')
    return matches[0].decode('ascii').lower()


def main():
    original=fetch_bytes(NIST_BRIDGE_URL)
    _validate_step(original)
    measured_hash=sha256(original).hexdigest()
    publisher_verified=False
    try:
        claimed=parse_sha(fetch_bytes(NIST_BRIDGE_HASH_URL))
        if measured_hash != claimed:
            raise ValueError('NIST published SHA-256 mismatch: reject untrusted file')
        publisher_verified=True
    except (OSError,TimeoutError,ValueError) as exc:
        if 'mismatch' in str(exc):
            raise
        print('Publisher checksum URL unavailable; local checksum recorded:',exc)
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_bytes(original)
    metadata={
        'publisher':'NIST','doi':NIST_DATASET_DOI,'url':NIST_BRIDGE_URL,
        'file':str(OUTPUT),'bytes':len(original),
        'sha256':measured_hash,
        'publisher_checksum_verified':publisher_verified,
        'experiment':'NIST IN718 additively manufactured bridge geometry',
        'warning':'No measured force-displacement static benchmark is asserted'
    }
    (OUTPUT.parent/'source_manifest.json').write_text(json.dumps(metadata,indent=2))
    print(json.dumps(metadata,indent=2))


if __name__=='__main__':
    main()
