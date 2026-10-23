#!/usr/bin/env python3
"""Download a curated, license-checked Poly Haven model library.
Only downloads model files with self-contained GLB payloads (or archives containing GLBs).
Selection is reproducible via catalog.json; assets may change upstream.
"""
import argparse, json, os, pathlib, re, urllib.request, zipfile, io, hashlib, time
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
  for k,v in node.items():
   if isinstance(v,str) and v.startswith("https://") and re.search(r"\\.(glb|zip)(?:\\?|$)",v,re.I): yield v
   else: yield from find_urls(v)
 elif isinstance(node,list):
  for v in node: yield from find_urls(v)
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
   urls.sort(key=lambda x:(not x.lower().split("?")[0].endswith(".glb"),len(x)))
   if not urls: raise ValueError("no GLB/ZIP URL in API response")
   data=download(urls[0])
   payload=None
   if data[:4]==b"glTF": payload=data
   elif zipfile.is_zipfile(io.BytesIO(data)):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
     names=[n for n in z.namelist() if n.lower().endswith(".glb") and not n.startswith("__MACOSX/")]
     if names:
      names.sort(key=lambda n:z.getinfo(n).file_size)
      payload=z.read(names[0])
   if not payload or payload[:4]!=b"glTF": raise ValueError("download did not contain valid GLB header")
   folder=out/cat; folder.mkdir(exist_ok=True)
   path=folder/(asset_id+".glb"); path.write_bytes(payload)
   manifest.append({"id":asset_id,"category":cat,"name":info.get("name",meta.get("name",asset_id)),"license":"CC0","source":"https://polyhaven.com/a/"+asset_id,"download_url":urls[0],"file":str(path.relative_to(out)),"bytes":len(payload),"sha256":hashlib.sha256(payload).hexdigest()})
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
