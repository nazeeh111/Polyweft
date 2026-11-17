"""Actual native replay from trusted included scenes; no user settings or GUI."""
import argparse,json,tempfile,hashlib
from pathlib import Path
from polyweft.native import create_plan,inspect_plan,apply_plan,bridge
p=argparse.ArgumentParser();p.add_argument('--blender',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=Path(__file__).parent
if a.output.exists():raise FileExistsError('Replay output must be new')
a.output.mkdir(parents=True)
summary={}
for name,right in [('crossing','right.blend'),('revised','right-revised.blend')]:
 review=a.output/(name+'-review');plan=create_plan(root/'native/base.blend',root/'native/left.blend',root/'native'/right,review,a.blender)
 report=inspect_plan(review,a.output/(name+'-inspection'),None,a.blender)
 expected=json.loads((root/(name+'-inspection.json')).read_text());assert report['geometry']==expected['geometry'];assert report['summaries']==expected['summaries'];assert report['complete']
 choices=root/'decisions.json' if name=='revised' else None
 receipt=apply_plan(review,a.output/(name+'.blend'),choices,a.blender,True)
 with tempfile.TemporaryDirectory(prefix='polyweft-reader-reopen-')as temp:
  final=bridge(a.blender,{'mode':'surface','source':str(a.output/(name+'.blend')),'mesh_id':plan['snapshots']['base']['guards']['mesh_id']},temp)
 assert final['geometry']==report['geometry']['merged']
 summary[name]={'crossing_face_pairs':report['summaries']['merged']['crossings'],'native_fresh_reopen_geometry_exact':True,'input_bytes_unchanged':receipt['input_bytes_unchanged'],'new_output_sha256':receipt['output']['sha256']}
print(json.dumps(summary,indent=2))
