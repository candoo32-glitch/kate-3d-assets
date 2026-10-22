import io, json, math, pathlib, struct, subprocess, urllib.request, zipfile
import numpy as np
import trimesh
BASE="https://raw.githubusercontent.com/yadneshSalvi/hearth-webmcp/main/public/assets/"
SPEC=[
("sofa-fjord.glb",(-3.85,0,-1.2),(2.45,1.15,0.95),2),
("sofa-endre.glb",(3.85,0,-1.2),(2.45,1.15,0.95),2),
("table-elm.glb",(-2.95,0,-4.25),(1.05,0.75,0.90),2),
("table-bord.glb",(2.95,0,-4.25),(1.05,0.75,0.90),2),
("plant-fern.glb",(-5.25,0,-2.5),(1.35,1.65,1.35),3),
("plant-fig.glb",(5.25,0,-2.5),(1.35,1.65,1.35),3),
("plant-ivy.glb",(-5.25,0,-11.5),(1.45,1.75,1.45),3),
("plant-palm.glb",(5.25,0,-11.5),(1.45,1.75,1.45),3)]
pathlib.Path("dist").mkdir(exist_ok=True)
pathlib.Path("temp").mkdir(exist_ok=True)
count=0
originals=[]
with open("dist/external_scene.bin","wb") as f:
 f.write(b"\x00"*4)
 for name,center,size,mat in SPEC:
  req=urllib.request.Request(BASE+"glb/"+name,headers={"User-Agent":"Kate-Converter"})
  data=urllib.request.urlopen(req,timeout=90).read()
  input=pathlib.Path("temp")/name;input.write_bytes(data)
  output=pathlib.Path("temp")/("decoded-"+name)
  subprocess.run(["./node_modules/.bin/gltf-transform","copy",str(input),str(output)],check=True)
  originals.append((name,output.read_bytes()))
  scene=trimesh.load(str(output),file_type="glb",force="scene")
  mesh=scene.dump(concatenate=True)
  vertices=np.asarray(mesh.vertices)
  bounds=np.asarray(mesh.bounds)
  extent=np.maximum(bounds[1]-bounds[0],1e-6)
  vertices=(vertices-bounds[0])*(np.asarray(size)/extent)+np.asarray(center)-np.asarray([size[0]/2,0,size[2]/2])
  faces=np.asarray(mesh.faces,dtype=np.int64)
  # Preserve every original triangle; no decimation.
  for face in faces:
   f.write(struct.pack("<I",mat))
   f.write(vertices[face].astype("<f4").tobytes())
   count+=1
  print(name,len(faces))
 f.seek(0);f.write(struct.pack("<I",count))
assert count>100
credits=urllib.request.urlopen(BASE+"CREDITS.md",timeout=90).read()
with zipfile.ZipFile("dist/Kate-Converted-Metal-Assets.zip","w",zipfile.ZIP_DEFLATED) as z:
 z.write("dist/external_scene.bin","external_scene.bin")
 for name, data in originals:
  z.writestr("original_decoded_glb/"+name, data)
 z.writestr("THIRD_PARTY_CREDITS.md",credits)
 z.writestr("manifest.json",json.dumps({"triangles":count,"format":"legacy geometry-only triangle stream; NOT an exact PBR conversion","models":[x[0] for x in SPEC],"decoded_originals":"original_decoded_glb/ preserves original GLB normals, UVs, textures and materials"},indent=2))
print("converted triangles",count)
