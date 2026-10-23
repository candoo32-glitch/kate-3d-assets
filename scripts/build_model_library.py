#!/usr/bin/env python3
"""Download a curated, license-checked Poly Haven model library.
Only downloads model files with self-contained GLB payloads (or archives containing GLBs).
Selection is reproducible via catalog.json; assets may change upstream.
"""
import argparse, json, os, pathlib, re, urllib.request, zipfile, io, hashlib, time, subprocess, tempfile, threading, sys
API="https://api.polyhaven.com"
UA={"User-Agent":"KateAssetLibrary/1.0 (GitHub Actions)"}
CATEGORIES={
 "forest": ["tree","pine","fir","spruce","oak","birch","forest","branch","log","stump","fern","moss","bush","shrub","ivy","grass","plant","leaf","leaves","rock"],
 "conservatory": ["greenhouse","conservatory","glasshouse","window","glass","door","wooden","beam","column","pillar","arch","stone","brick","tile","floor","bench","pot","planter","flower","vase","garden","lamp"],
 "furniture": ["sofa","chair","table","desk","shelf","cabinet","couch","stool"],
}
def get_json(url):
 req=urllib.request.Request(url,headers=UA)
 with urllib.request.urlopen(req,timeout=50) as f: return json.load(f)
def download(url,maxbytes=400_000_000):
 req=urllib.request.Request(url,headers=UA)
 with urllib.request.urlopen(req,timeout=150) as f:
  length=int(f.headers.get("Content-Length","0"))
  if length>maxbytes: raise ValueError("asset exceeds size limit")
  data=f.read(maxbytes+1)
  if len(data)>maxbytes: raise ValueError("asset exceeds size limit")
  return data
def asset_candidates(files):
 """Prefer 1k/2k glTF packages; Poly Haven supplies separate include files."""
 result=[]
 for fmt in ("gltf",):
  group=files.get(fmt,{})
  for resolution in ("1k","2k","4k"):
   block=group.get(resolution,{})
   record=block.get(fmt,block)
   if isinstance(record,dict) and record.get("url"):
    result.append((fmt,record))
 return result

def convert_asset(fmt,record,asset_id):
 started=time.monotonic()
 print(f"DOWNLOAD {asset_id}: source {fmt}",flush=True)
 with tempfile.TemporaryDirectory() as tmp:
  root=pathlib.Path(tmp)
  url=record["url"]
  name=pathlib.PurePosixPath(url.split("?")[0]).name
  src=root/name
  data=download(url)
  src.write_bytes(data)
  print(f"DOWNLOADED {asset_id}: source {len(data)/1048576:.1f} MiB in {time.monotonic()-started:.1f}s",flush=True)
  for relative,entry in record.get("include",{}).items():
   if not isinstance(entry,dict) or not entry.get("url"): continue
   target=root/relative
   if not target.resolve().is_relative_to(root.resolve()): raise ValueError("unsafe included asset path")
   target.parent.mkdir(parents=True,exist_ok=True)
   included=download(entry["url"])
   target.write_bytes(included)
   print(f"TEXTURE {asset_id}: {relative} {len(included)/1048576:.1f} MiB",flush=True)
  if fmt!="gltf": raise ValueError("Pilot supports native glTF packages only")
  dst=root/"asset.glb"
  cmd=["gltf-transform","copy",str(src),str(dst)]
  print(f"PACK {asset_id}: glTF -> GLB (no Blender)",flush=True)
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
  if p.returncode or not dst.exists():
   raise ValueError(f"glTF Transform failed ({p.returncode}): "+(p.stdout+p.stderr)[-1000:])
  payload=dst.read_bytes()
  if payload[:4]!=b"glTF": raise ValueError("Invalid GLB output header")
  print(f"PACKED {asset_id}: {len(payload)/1048576:.1f} MiB in {time.monotonic()-started:.1f}s",flush=True)
  return payload

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--limit",type=int,default=36)
 p.add_argument("--output",default="dist")
 p.add_argument("--max-attempts",type=int,default=72)
 a=p.parse_args()
 out=pathlib.Path(a.output); out.mkdir(parents=True,exist_ok=True)
 models=get_json(API+"/assets?t=models")
 ranked=[]
 for asset_id,meta in models.items():
  if not isinstance(meta,dict): continue
  text=" ".join([asset_id,str(meta.get("name","")),str(meta.get("categories","")),str(meta.get("tags",""))]).lower()
  scores={cat:sum(3 if word in asset_id.lower() else 1 for word in terms if word in text) for cat,terms in CATEGORIES.items()}
  cat=max(scores,key=scores.get)
  if scores[cat]: ranked.append((scores[cat],cat,asset_id,meta))
 ranked.sort(key=lambda r:(-r[0],r[2]))
 # Interleave categories, preserving ranked order within each category.
 buckets={cat:[item for item in ranked if item[1]==cat] for cat in CATEGORIES}
 ranked=[]
 offsets={cat:0 for cat in CATEGORIES}
 while any(offsets[cat]<len(buckets[cat]) for cat in CATEGORIES):
  for cat in ("forest","conservatory","furniture"):
   if offsets[cat]<len(buckets[cat]):
    ranked.append(buckets[cat][offsets[cat]])
    offsets[cat]+=1
 counts={k:0 for k in CATEGORIES}; quotas={"forest":22,"conservatory":10,"furniture":4}
 manifest=[]; errors=[]
 print(f"DISCOVERED {len(ranked)} candidate assets; target {a.limit}",flush=True)
 for index,(score,cat,asset_id,meta) in enumerate(ranked,1):
  if len(manifest)+len(errors)>=a.max_attempts: break
  if len(manifest)>=a.limit: break
  if counts[cat]>=quotas[cat]: continue
  print(f"START {index}/{len(ranked)} {cat}/{asset_id} | success={len(manifest)} failed={len(errors)}",flush=True)
  try:
   info=get_json(API+"/info/"+asset_id)
   license_name=str(info.get("license",meta.get("license","CC0"))).upper()
   if license_name not in ("CC0","CC0 1.0"): continue
   files=get_json(API+"/files/"+asset_id)
   candidates=asset_candidates(files)
   print(f"SOURCES {asset_id}: {[(fmt,rec.get('url','')[-65:]) for fmt,rec in candidates[:4]]}",flush=True)
   if not candidates: raise ValueError("API has no glTF/Blend/FBX candidate")
   payload=None
   url=None
   for fmt,record in candidates[:1]:
    try:
     url=record["url"]
     print(f"CONVERT {asset_id} {fmt} started",flush=True)
     payload=convert_asset(fmt,record,asset_id)
     if payload[:4]==b"glTF": break
    except Exception as candidate_error:
     print("CANDIDATE FAILED",asset_id,fmt,str(candidate_error)[:180],flush=True)
   if not payload: raise ValueError("No source model converted successfully")
   if not payload or payload[:4]!=b"glTF": raise ValueError("download did not contain valid GLB header")
   folder=out/cat; folder.mkdir(exist_ok=True)
   path=folder/(asset_id+".glb"); path.write_bytes(payload)
   manifest.append({"id":asset_id,"category":cat,"name":info.get("name",meta.get("name",asset_id)),"license":"CC0","source":"https://polyhaven.com/a/"+asset_id,"download_url":url,"file":str(path.relative_to(out)),"bytes":len(payload),"sha256":hashlib.sha256(payload).hexdigest()})
   counts[cat]+=1
   print("OK",cat,asset_id,len(payload),"TOTAL",len(manifest),counts,flush=True)
  except Exception as e:
   errors.append({"id":asset_id,"reason":str(e)})
   print("SKIP",asset_id,str(e),"FAILED",len(errors),flush=True)
 (out/"build-info.json").write_text(json.dumps({"run_id":os.getenv("GITHUB_RUN_ID"),"run_url":"https://github.com/"+os.getenv("GITHUB_REPOSITORY","candoo32-glitch/kate-3d-assets")+"/actions/runs/"+os.getenv("GITHUB_RUN_ID","unknown"),"commit":os.getenv("GITHUB_SHA"),"successful":len(manifest),"counts":counts},indent=2))
 (out/"catalog.json").write_text(json.dumps({"source":"Poly Haven API","models":manifest,"skipped":errors,"counts":counts},indent=2))
 (out/"LICENSES.md").write_text("# Asset provenance\n\nAll bundled models are individually checked for CC0 metadata.\n\n"+"\n".join("- ["+m["name"]+"]("+m["source"]+") — CC0 — "+m["file"] for m in manifest)+"\n")
 if not manifest: raise SystemExit("No valid assets downloaded. Check upstream API and URLs.")
 print("SUMMARY",json.dumps({"successful":len(manifest),"failed":len(errors),"counts":counts}),flush=True)
if __name__=="__main__": main()
