"""Standard-library hash/geometry reader, separate from an actual Blender replay."""
import json,hashlib,math,xml.etree.ElementTree as ET
from pathlib import Path
from fractions import Fraction
p=Path(__file__).parent;m=json.loads((p/'MANIFEST.json').read_text())
for name,digest in m['sha256'].items():assert hashlib.sha256((p/name).read_bytes()).hexdigest()==digest,name
f=json.loads((p/'figure-manifest.json').read_text());right=f['camera']['right'];up=f['camera']['up'];center=f['camera']['center'];assert abs(sum(x*y for x,y in zip(right,up)))<1e-14;assert all(abs(sum(x*x for x in row)-1)<1e-14 for row in [right,up])
records=[json.loads((p/(n+'-inspection.json')).read_text())for n in ['crossing','revised']]
for mobile in [False,True]:
 root=ET.parse(p/('revision-mobile.svg'if mobile else'revision.svg')).getroot();polys=list(root.iter('{http://www.w3.org/2000/svg}polygon'));assert len(polys)==48
 for poly in polys:
  i=int(poly.attrib['data-case']);scale=66 if mobile else 90;ox=22 if mobile else 36+i*550;oy=177+i*354 if mobile else 170;cx=187.5 if mobile else ox+248;cy=oy+(141 if mobile else 145)
  g=records[i]['geometry']['merged'];verts={v['id']:v['co']for v in g['vertices']};tri=next(t for t in g['triangles']if t['face']==int(poly.attrib['data-face']));expected=[]
  for key in tri['vertices']:
   v=verts[key];u,y=[sum((v[j]-center[j])*row[j]for j in range(3))for row in [right,up]];expected.append((cx+u*scale,cy-y*scale))
  actual=[tuple(map(float,q.split(',')))for q in poly.attrib['points'].split()]
  assert all(abs(x-y)<1e-7 for a,b in zip(actual,expected)for x,y in zip(a,b))
for mobile in [False,True]:
 root=ET.parse(p/('revision-mobile.svg' if mobile else 'revision.svg')).getroot();line=next(root.iter('{http://www.w3.org/2000/svg}polyline'));scale=66 if mobile else 90;cx=187.5 if mobile else 284;cy=318 if mobile else 315
 witness=records[0]['findings'][0]['history']['merged']['witnesses'][0]['points'];expected=[]
 for point in witness:
  v=[float(Fraction(x)) for x in point];u,y=[sum((v[j]-center[j])*row[j]for j in range(3))for row in[right,up]];expected.append((cx+u*scale,cy-y*scale))
 actual=[tuple(map(float,q.split(',')))for q in line.attrib['points'].split()];assert all(abs(x-y)<1e-7 for a,b in zip(actual,expected)for x,y in zip(a,b))
assert records[0]['summaries']['merged']['crossings']==20 and records[1]['summaries']['merged']['crossings']==0
print(f"Verified {len(m['sha256'])} exact payloads, all 48 native triangle polygons per variant, and common orthonormal projection. Stored artifacts only; run replay.py separately for native computation.")
