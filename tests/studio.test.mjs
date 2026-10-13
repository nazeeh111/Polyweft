import test from 'node:test';
import assert from 'node:assert/strict';
import {previewVertices, decisionDocument, projectMesh, validatePlan} from '../src/polyweft/studio/geometry.mjs';

const snap = co => ({name:'Mesh', vertices:co.map((v,i)=>({id:i,co:v})), faces:[[0,1,2]], uv_layers:{}});
const plan = () => ({schema:'polyweft.plan.v1',id:'a'.repeat(64),sources:{},snapshots:{base:snap([[0,0,0],[1,0,0],[0,1,0]]),left:snap([[0,0,1],[2,0,0],[0,1,0]]),right:snap([[0,0,0],[1,0,1],[0,2,0]])},changes:[{key:'vertex:0',domain:'vertex',kind:'left',base:[0,0,0],left:[0,0,1],right:[0,0,0]},{key:'vertex:1',domain:'vertex',kind:'conflict',base:[1,0,0],left:[2,0,0],right:[1,0,1]},{key:'vertex:2',domain:'vertex',kind:'right',base:[0,1,0],left:[0,1,0],right:[0,2,0]}],blockers:[],observed_exclusions:[]});
test('preview combines independent edits, retains right, never blends vector axes',()=>{
  const p=plan(), before=JSON.stringify(p), v=previewVertices(p,{'vertex:1':'left'});
  assert.deepEqual(v.map(x=>x.co),[[0,0,1],[2,0,0],[0,2,0]]);
  assert.equal(JSON.stringify(p),before);
  assert.deepEqual(previewVertices(p,{'vertex:1':'base'})[1].co,[1,0,0]);
});
test('export binds plan and refuses unknown, unresolved and blocked choices',()=>{
  const p=plan();
  assert.throws(()=>decisionDocument(p,{}),/Unresolved/);
  assert.throws(()=>decisionDocument(p,{'vertex:1':'blend'}),/Invalid/);
  assert.throws(()=>decisionDocument(p,{'vertex:1':'right','vertex:9':'left'}),/Unknown/);
  assert.equal(decisionDocument(p,{'vertex:1':'right'}).plan_id,p.id);
  p.blockers=[{message:'Topology changed'}];
  assert.throws(()=>decisionDocument(p,{'vertex:1':'right'}),/blocked/);
});
test('finite admission and topology display reject malformed plan',()=>{
  const p=plan(); validatePlan(p);
  p.snapshots.base.vertices[0].co[1]=NaN;
  assert.throws(()=>validatePlan(p),/finite/);
  const q=plan(); q.snapshots.right.faces[0][2]=88;
  assert.throws(()=>validatePlan(q),/vertex/);
});
test('projection handles flat mesh and produces finite visible geometry',()=>{
  const p=plan(), projected=projectMesh(p.snapshots.base.vertices,p.snapshots.base.faces,0,0,1,500,300);
  assert.equal(projected.triangles.length,1);
  assert.ok(projected.points.every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)));
});
test('concave polygon preview preserves the U-shaped notch instead of filling it',()=>{
  const coordinates=[[0,0],[3,0],[3,3],[2,3],[2,1],[1,1],[1,3],[0,3]];
  const vertices=coordinates.map(([x,y],id)=>({id,co:[x,y,0]}));
  const result=projectMesh(vertices,[vertices.map(v=>v.id)],0,0,1,500,300);
  let area=0;
  for(const tri of result.triangles){const [a,b,c]=tri.ids.map(id=>coordinates[id]);area+=Math.abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2;}
  assert.equal(area,7);
});
