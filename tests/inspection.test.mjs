import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {parseInspectionText, validateInspection, inspectionMatches, inspectionStatus} from '../src/polyweft/studio/inspection.mjs';
import {projectMesh} from '../src/polyweft/studio/geometry.mjs';

function fixture() {
  const vertices=[[0,0,0],[1,0,0],[1,1,0],[0,1,0]].map((co,i)=>({id:i+1,co}));
  const snapshot={name:'Quad',vertices,faces:[[1,2,3,4]],uv_layers:{},guards:{corner_order:[1,2,3,4]}};
  const p={schema:'polyweft.plan.v1',id:'a'.repeat(64),sources:Object.fromEntries(['base','left','right'].map((s,i)=>[s,{path:s+'.blend',sha256:String(i+1).repeat(64)}])),snapshots:{base:structuredClone(snapshot),left:structuredClone(snapshot),right:structuredClone(snapshot)},changes:[],blockers:[]};
  p.snapshots.left.vertices[0].co=[0,0,1];p.snapshots.right.vertices[0].co=[0,0,2];
  p.changes=[{key:'vertex:1',domain:'vertex',kind:'conflict',base:[0,0,0],left:[0,0,1],right:[0,0,2]}];
  const choices={'vertex:1':'left'};
  const geometry=Object.fromEntries(['base','left','right','merged'].map(s=>[s,{vertices:structuredClone(p.snapshots[s==='merged'?'left':s].vertices),faces:[[1,2,3,4]],triangles:[{face:0,vertices:[1,2,4],corners:[1,2,4]},{face:0,vertices:[2,3,4],corners:[2,3,4]}]}]));
  const r={schema:'polyweft.inspection.v1',id:'b'.repeat(64),plan_id:p.id,decisions:{schema:'polyweft.decisions.v1',plan_id:p.id,choices},source_sha256:Object.fromEntries(Object.entries(p.sources).map(([s,x])=>[s,x.sha256])),runtime:{version:'4.5.14',build_hash:'native-build'},scope:'Native represented triangles; not a safety certificate.',complete:true,summary_scope:'all pairs',limits:{},work:{},geometry,summaries:Object.fromEntries(Object.keys(geometry).map(s=>[s,{crossings:0,coplanar_overlaps:0,contacts:0,unknown_faces:[]}])),findings:[]};
  r.incomplete_reasons=[];
  r.limits={max_broadphase_visits:100000,max_polygon_pairs:20000,max_exact_tests:50000,max_findings:200,max_provenance_entries:10000};
  r.work=Object.fromEntries(['broadphase_visits','candidate_polygon_pairs','exact_tests','inspected_polygon_pairs','reported_findings','unreported_findings','witnesses_truncated','unknown_pair_states','provenance_entries','provenance_omitted'].map(k=>[k,0]));
  for(const g of Object.values(r.geometry)){g.complete=true;g.triangle_count=2;}
  for(const s of Object.values(r.summaries))s.unknown_pairs=0;
  return {p,r,choices};
}
test('inspection preserves exact native tessellation instead of choosing a preview diagonal',()=>{
  const {p,r}=fixture(), before=JSON.stringify({p,r});validateInspection(r,p);
  const g=r.geometry.base, rendered=projectMesh(g.vertices,g.faces,0,0,1,400,300,undefined,g.triangles);
  assert.deepEqual(rendered.triangles.map(x=>x.ids).sort(),[[1,2,4],[2,3,4]].sort());
  assert.ok(rendered.triangles.every(x=>x.face===0));assert.equal(JSON.stringify({p,r}),before);
});
test('changing a conflict choice makes the native report stale',()=>{
  const {p,r,choices}=fixture();assert.equal(inspectionMatches(r,p,choices),true);
  assert.equal(inspectionMatches(r,p,{'vertex:1':'right'}),false);
  assert.equal(inspectionMatches(r,p,{}),false);
  assert.equal(inspectionMatches(r,p,{...choices,'vertex:999':'left'}),false);
});
test('source hash, coordinates and native face/corner membership are bound to the plan',()=>{
  for(const mutate of [r=>r.source_sha256.left='f'.repeat(64),r=>r.geometry.left.vertices[0].co[0]=.01,r=>r.geometry.merged.triangles[0].face=8,r=>r.geometry.merged.triangles[0].corners[0]=99,r=>r.geometry.right.faces[0].reverse()]){
    const {p,r}=fixture();mutate(r);assert.throws(()=>validateInspection(r,p));
  }
});
test('incomplete zero counts never become a clear inspection',()=>{
  const {p,r}=fixture();r.complete=false;r.summary_scope='bounded inspected pairs';
  validateInspection(r,p);assert.match(inspectionStatus(r),/incomplete/i);assert.doesNotMatch(inspectionStatus(r),/safe|clear/i);
});
test('malformed state counts and witness indices refuse before rendering',()=>{
  const {p,r}=fixture();r.summaries.merged.crossings=-1;assert.throws(()=>validateInspection(r,p));
  const q=fixture();q.r.findings=[{faces:[0,88],classification:'merge-only',history:{},provenance:[]}];assert.throws(()=>validateInspection(q.r,q.p));
});
test('recorded native witnesses bind accepted edits and their selected source',()=>{
  const original=JSON.parse(readFileSync(new URL('./fixtures/native-inspection.json',import.meta.url),'utf8'));
  validateInspection(original.inspection,original.plan);
  assert.equal(original.inspection.findings.length,20);
  for(const mutate of [r=>r.findings[0].provenance[0].source_sha256='f'.repeat(64),r=>r.findings[0].provenance[0].selected='base',r=>r.findings[0].history.base.kind='contact',r=>r.findings[0].history.merged.witnesses[0].triangles[0]=99999]) {
    const d=structuredClone(original);mutate(d.inspection);assert.throws(()=>validateInspection(d.inspection,d.plan));
  }
});
test('missing capture, unknown geometry and truncated work cannot claim completeness',()=>{
  for(const mutate of [r=>r.geometry.merged.complete=false,r=>r.geometry.merged.triangles=[],r=>r.geometry.merged.triangle_count=100,r=>r.incomplete_reasons=['Limit reached'],r=>r.summaries.base.unknown_faces=[0],r=>r.work.exact_tests=50000,r=>r.work.provenance_omitted=1]){
    const {p,r}=fixture();mutate(r);assert.throws(()=>validateInspection(r,p));
  }
});
test('browser verifies original native report bytes and rejects edited or reformatted data',async()=>{
  const raw=readFileSync(new URL('./fixtures/native-inspection-canonical.json',import.meta.url),'utf8');
  const parsed=await parseInspectionText(raw);assert.equal(parsed.complete,true);
  await assert.rejects(parseInspectionText(raw.replace('"complete":true','"complete":false')),/checksum/);
  await assert.rejects(parseInspectionText(JSON.stringify(JSON.parse(raw),null,2)),/original/);
  await assert.rejects(parseInspectionText(raw.replace(/"id":"[a-f0-9]{64}",/,'')),/checksum/);
});
