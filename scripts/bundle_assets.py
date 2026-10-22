#!/usr/bin/env python3
"""Download selected CC0 models from an attributed GitHub asset library."""
import hashlib, json, pathlib, struct, urllib.request, zipfile
BASE = "https://raw.githubusercontent.com/yadneshSalvi/hearth-webmcp/main/public/assets/"
NAMES = [
 "sofa-endre.glb", "sofa-fjord.glb",
 "table-elm.glb", "table-bord.glb",
 "plant-fern.glb", "plant-fig.glb", "plant-ivy.glb", "plant-palm.glb"
]
OUT = pathlib.Path("dist/Kate-Furniture-Plants.zip")
def get(url):
    req = urllib.request.Request(url, headers={"User-Agent":"Kate-Asset-Bundler/1.0"})
    with urllib.request.urlopen(req, timeout=90) as response:
        return response.read()
def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    credits = get(BASE + "CREDITS.md")
    manifest = {"source_repository":"https://github.com/yadneshSalvi/hearth-webmcp",
                "license":"See CREDITS.md (listed models CC0)",
                "assets":[]}
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("CREDITS.md", credits)
        for name in NAMES:
            data = get(BASE + "glb/" + name)
            if len(data)<20 or data[:4]!=b"glTF" or struct.unpack_from("<I",data,8)[0]!=len(data):
                raise ValueError(f"Invalid GLB: {name}")
            archive.writestr("models/"+name, data)
            manifest["assets"].append({"file":"models/"+name,"bytes":len(data),
                                       "sha256":hashlib.sha256(data).hexdigest()})
            print(f"Bundled {name}: {len(data):,} bytes")
        archive.writestr("manifest.json",json.dumps(manifest,indent=2))
    print(f"Created {OUT} ({OUT.stat().st_size:,} bytes)")
if __name__ == "__main__": main()
