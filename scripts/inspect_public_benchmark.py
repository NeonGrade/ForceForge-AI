"""Optional acquisition of publicly licensed raw Hannover laboratory data.

Source: https://doi.org/10.25835/lyav246d (CC BY 3.0).
Run this manually or through the dedicated GitHub Actions workflow.
Downloads are NOT silently committed to the ForceForge repository.
"""
from __future__ import annotations
import hashlib
from io import BytesIO
import json
from pathlib import Path
import urllib.request

BASE="https://data.uni-hannover.de/dataset/3aceac8e-e8ee-4497-8ea1-90acaa57dda0/resource"
RESOURCES={
  "Beam_model.inp":BASE+"/39842a05-385c-4b39-ad3e-306bc95c9675/download/beam_model.inp",
  "Data_strain_estimation_laboratory_beam.mat":BASE+"/0afe150f-df81-41f6-82a2-a4c53f597b8f/download/measurement_data_virtual_sensing_benchmark_beam.mat",
}
MAX_BYTES=30*1024*1024


def download(url:str,output:Path)->dict:
    request=urllib.request.Request(url,headers={"User-Agent":"ForceForge-X-Open-Benchmark-Research/0.4","Accept":"*/*"})
    with urllib.request.urlopen(request,timeout=100) as response:
        content=response.read(MAX_BYTES+1)
        if len(content)>MAX_BYTES:
            raise ValueError("Resource larger than 30 MiB; manual inspection needed")
        if content[:10].lower().startswith(b"<html"):
            raise ValueError("Unexpected HTML instead of actual scientific data")
    output.write_bytes(content)
    return {"bytes":len(content),"sha256":hashlib.sha256(content).hexdigest(),"official_url":url}


def main()->None:
    out=Path("data/third_party/hannover")
    out.mkdir(parents=True,exist_ok=True)
    manifest={"source_doi":"10.25835/lyav246d","license":"CC BY 3.0","files":{}}
    for name,url in RESOURCES.items():
        try:
            item=download(url,out/name)
            manifest["files"][name]=item
            print("DOWNLOADED",name,item["bytes"],"sha256",item["sha256"])
        except Exception as err:
            print("DOWNLOAD_FAILED",name,type(err).__name__,str(err))
    mat_file=out/"Data_strain_estimation_laboratory_beam.mat"
    if mat_file.exists():
        from scipy.io import whosmat
        try:
            variables=whosmat(str(mat_file))
            manifest["mat_variables"]=[{"name":name,"shape":list(shape),"type":dtype} for name,shape,dtype in variables]
            print("RAW MAT VARIABLES:")
            for x in manifest["mat_variables"]:
                print(" ",x)
        except Exception as err:
            print("MAT_INTROSPECTION_FAILED",type(err).__name__,str(err))
            try:
                import h5py
                with h5py.File(mat_file,"r") as f:
                    manifest["mat_hdf5_keys"]=list(f.keys())
                    print("MAT_HDF5_KEYS",manifest["mat_hdf5_keys"])
            except Exception as error:
                print("MAT_HDF5_FAILED",type(error).__name__,str(error))
    inp_file=out/"Beam_model.inp"
    if inp_file.exists():
        from forceforge.modal_benchmark import read_abaqus_inp
        parsed=read_abaqus_inp(inp_file.read_text(errors="replace"))
        manifest["abaqus_summary"]={k:v for k,v in parsed.items() if k not in ("nodes","elements")}
        print("ABAQUS_SUMMARY",manifest["abaqus_summary"])
    (out/"source_manifest.json").write_text(json.dumps(manifest,indent=2))
    if len(manifest["files"])<2:
        raise SystemExit("Not all raw source resources downloaded. Artifact includes only partial source; do not claim full raw validation.")


if __name__=="__main__":
    main()
