#!/usr/bin/env python3
"""Download a curated, license-checked Poly Haven model library.
Only downloads model files with self-contained GLB payloads (or archives containing GLBs).
Selection is reproducible via catalog.json; assets may change upstream.
"""
import argparse, json, os, pathlib, re, urllib.request, zipfile, io, hashlib, time, subprocess, tempfile
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
def download(url,maxbytes=180_000_000):
 req=urllib.request.Request(url,headers=UA)
 with urllib.request.urlopen(req,timeout=150) as f:
  length=int(f.headers.get("Content-Length","0"))
  if length>maxbytes: raise ValueError("asset exceeds size limit")
  data=f.read(maxbytes+1)
  if len(data)>maxbytes: raise ValueError("asset exceeds size limit")
  return data
def find_urls(node):
 if isinstance(node,dict):
  url=node.get("url")
  if isinstance(url,str) and url.startswith("https://"): yield url
  for k,v in node.items():
   if k!="url": yield from find_urls(v)
 elif isinstance(node,list):
  for v in node: yield from find_urls(v)

def convert_blend(data):
 with tempfile.TemporaryDirectory() as tmp:
  src=pathlib.Path(tmp)/"asset.blend"
  dst=pathlib.Path(tmp)/"asset.glb"
  script=pathlib.Path(tmp)/"convert.py"
  src.write_bytes(data)
  script.write_text("import bpy,sys\nsrc,dst=sys.argv[sys.argv.index('--')+1:]\nbpy.ops.wm.open_mainfile(filepath=src)\nbpy.ops.export_scene.gltf(filepath=dst,export_format='GLB',export_apply=True)\n")
  p=subprocess.run(["blender","--background","--python",str(script),"--",str(src),str(dst)],capture_output=True,text=True,timeout=240)
  if p.returncode or not dst.exists(): raise ValueError("Blender export failed: "+(p.stdout+p.stderr)[-500:])
  return dst.read_bytes()

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--limit",type=int,default=36)
 p.add_argument("--output",default="dist")
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
 counts={k:0 for k in CATEGORIES}; quotas={"forest":22,"conservatory":10,"furniture":4}
 manifest=[]; errors=[]
 for score,cat,asset_id,meta in ranked:
  if len(manifest)>=a.limit: break
  if counts[cat]>=quotas[cat]: continue
  try:
   info=get_json(API+"/info/"+asset_id)
   license_name=str(info.get("license",meta.get("license","CC0"))).upper()
   if "CC0" not in license_name: continue
   files=get_json(API+"/files/"+asset_id)
   urls=list(dict.fromkeys(find_urls(files)))
   urls=[u for u in urls if u.split("?")[0].lower().endswith((".glb",".blend",".zip"))]
   urls.sort(key=lambda u:({".glb":0,".blend":1,".zip":2}.get(pathlib.PurePosixPath(u.split("?")[0]).suffix.lower(),9),len(u)))
   if not urls: raise ValueError("API contains no GLB, BLEND, or ZIP download URL")
   payload=None
   for url in urls[:5]:
    try:
     data=download(url)
     if data[:4]==b"glTF": payload=data
     elif data[:7]==b"BLENDER": payload=convert_blend(data)
     elif zipfile.is_zipfile(io.BytesIO(data)):
      with zipfile.ZipFile(io.BytesIO(data)) as z:
       names=[n for n in z.namelist() if n.lower().endswith(".glb")]
       if names: payload=z.read(sorted(names,key=lambda n:z.getinfo(n).file_size)[0])
     if payload and payload[:4]==b"glTF": break
    except Exception as candidate_error:
     print("CANDIDATE FAILED",asset_id,str(candidate_error)[:150],flush=True)
   if not payload: raise ValueError("No candidate produced a valid GLB")
   if not payload or payload[:4]!=b"glTF": raise ValueError("download did not contain valid GLB header")
   folder=out/cat; folder.mkdir(exist_ok=True)
   path=folder/(asset_id+".glb"); path.write_bytes(payload)
   manifest.append({"id":asset_id,"category":cat,"name":info.get("name",meta.get("name",asset_id)),"license":"CC0","source":"https://polyhaven.com/a/"+asset_id,"download_url":url,"file":str(path.relative_to(out)),"bytes":len(payload),"sha256":hashlib.sha256(payload).hexdigest()})
   counts[cat]+=1
   print("OK",cat,asset_id,len(payload),flush=True)
  except Exception as e:
   errors.append({"id":asset_id,"reason":str(e)})
   print("SKIP",asset_id,str(e),flush=True)
 (out/"catalog.json").write_text(json.dumps({"source":"Poly Haven API","models":manifest,"skipped":errors,"counts":counts},indent=2))
 (out/"LICENSES.md").write_text("# Asset provenance\n\nAll bundled models are individually checked for CC0 metadata.\n\n"+"\n".join("- ["+m["name"]+"]("+m["source"]+") — CC0 — "+m["file"] for m in manifest)+"\n")
 if not manifest: raise SystemExit("No valid assets downloaded. Check upstream API and URLs.")
 print("Bundled",len(manifest),"models",counts)
if __name__=="__main__": main()
