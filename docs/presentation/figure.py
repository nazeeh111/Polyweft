"""Exact native triangles with one verified orthonormal camera and common scale."""
import json,math,html,hashlib
from fractions import Fraction
from pathlib import Path
p=Path(__file__).parent
records=[json.loads((p/f'{name}-inspection.json').read_text())for name in ['crossing','revised']]
yaw,pitch=.6,.4
right=(math.cos(yaw),-math.sin(yaw),0)
up=(math.sin(yaw)*math.sin(pitch),math.cos(yaw)*math.sin(pitch),math.cos(pitch))
assert abs(sum(x*y for x,y in zip(right,up)))<1e-14
assert all(abs(sum(x*x for x in v)-1)<1e-14 for v in [right,up])
center=(.75,0,0)
def project(v):return[sum((v[j]-center[j])*row[j]for j in range(3))for row in [right,up]]
for variant in ('desktop', 'phone', 'compact'):
 mobile = variant != 'desktop'
 compact = variant == 'compact'
 w,h=(375,540) if compact else (375,980) if mobile else (1120,610)
 scale=66 if mobile else 90;pad=22 if mobile else 36
 parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 {w} {h}" role="img" aria-labelledby="title desc"><title id="title">Revise the branch. Recompute the inspection.</title><desc id="desc">Two actual native combined surfaces from Blender 5.1.2. The original independent edits create 20 crossing face pairs. Revising the right branch from minus 3 to minus 1 X translation gives zero crossings within this complete represented-face inspection. Both use the same orthographic camera and equal horizontal and vertical scale. This is not whole-scene collision or physical clearance.</desc><rect width="{w}" height="{h}" fill="#17191d"/>']
 def text(x,y,t,size=16,color='#f4f5f7'):parts.append(f'<text x="{x}" y="{y}" font-family="Arial, Helvetica, sans-serif" font-size="{size}" fill="{color}">{html.escape(t)}</text>')
 if not compact:
  text(pad,35,'Polyweft / Native branch revision',12,'#b1bac6')
  for i,line in enumerate(['Revise the branch.','Recompute the inspection.']if mobile else['Revise the branch. Recompute the inspection.']):text(pad,78+i*34,line,26 if mobile else 36)
 for index,(name,d)in enumerate(zip(['Original edits','Revised right branch'],records)):
  ox=pad if mobile else pad+index*550;oy=(177+index*354)if mobile else 170;cx=(w/2)if mobile else ox+248;cy=oy+(141 if mobile else 145)
  if compact:
   oy=31+index*247
   cy=oy+114+22*index
   count=d['summaries']['merged']['crossings']
   heading = 'Original merge' if index == 0 else 'Revised merge'
   text(ox,oy,f'{heading} · {count} crossing pairs',21)
   text(ox,oy+24,'Right branch: −3 X from ancestor' if index==0 else 'Right branch: −1 X from ancestor',17,'#b1bac6')
  else:
   text(ox,oy,name,18)
  g=d['geometry']['merged'];vertices={v['id']:v['co']for v in g['vertices']}
  def xy(v):u,v=project(v);return(cx+u*scale,cy-v*scale)
  triangles=sorted(g['triangles'],key=lambda t:sum(vertices[k][1]for k in t['vertices']))
  for t in triangles:
   points=' '.join(f'{x:.9f},{y:.9f}'for x,y in[xy(vertices[k])for k in t['vertices']]);color='#ff8976'if all(k<=8 for k in t['vertices'])else'#55d6e8'
   parts.append(f'<polygon data-case="{index}" data-face="{t["face"]}" data-scale="{scale}" points="{points}" fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="1.2"/>')
  if index==0:
   witness=d['findings'][0]['history']['merged']['witnesses'][0]['points'];points=' '.join(f'{x:.9f},{y:.9f}'for x,y in[xy([float(Fraction(c))for c in v])for v in witness]);parts.append(f'<polyline data-witness="0" points="{points}" fill="none" stroke="#f3e36b" stroke-width="5"/>')
  if not compact:
   count=d['summaries']['merged']['crossings'];text(ox,oy+(286 if mobile else 300),f'{count} crossing face pairs',18);text(ox,oy+(310 if mobile else 324),'Right edit: −3 X from ancestor'if index==0 else'Right edit: −1 X from ancestor',12,'#b1bac6')
 if compact:
  text(pad,522,'Same camera · Same scale',17,'#b1bac6')
 else:
  fy=912 if mobile else 550;text(pad,fy,'Same camera and scale. Native surfaces reopened.',12,'#b1bac6');text(pad,fy+24,'Target-face inspection only; no physical clearance claim.',11 if mobile else 14,'#b1bac6')
 output={'desktop':'revision.svg','phone':'revision-mobile.svg','compact':'revision-compact.svg'}[variant]
 parts.append('</svg>');(p/output).write_text(''.join(parts))
(p/'figure-manifest.json').write_text(json.dumps({'inputs':{name:hashlib.sha256((p/name).read_bytes()).hexdigest()for name in ['crossing-inspection.json','revised-inspection.json']},'camera':{'right':right,'up':up,'center':center,'projection':'orthographic','orthonormal':True},'scales':{'desktop':90,'phone':66},'triangleCounts':[len(r['geometry']['merged']['triangles'])for r in records],'meaning':'Each polygon is a native triangle; exact common scale on X/Y within each variant. Yellow line is first recorded crossing witness, not invented clearance.'},indent=2)+'\n')
