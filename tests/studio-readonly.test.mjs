// Ordinary DOM/handler tests. Synthetic stored geometry only; no Blender runtime.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import * as geometry from '../src/polyweft/studio/geometry.mjs';
import * as inspectionApi from '../src/polyweft/studio/inspection.mjs';

const appSource=readFileSync(new URL('../src/polyweft/studio/app.mjs',import.meta.url),'utf8');
const html=readFileSync(new URL('../src/polyweft/studio/index.html',import.meta.url),'utf8');
class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.attributes={};this.dataset={};this.value='';this.textContent='';this.hidden=false;this.disabled=false;this.className='';this.classes=new Set();this.classList={add:x=>this.classes.add(x),toggle:(x,on)=>{if(on??!this.classes.has(x))this.classes.add(x);else this.classes.delete(x);}};}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=[...children];}
  setAttribute(k,v){this.attributes[k]=v;}
  get options(){return this.children;}
  getBoundingClientRect(){return {width:320,height:240};}
  getContext(){return new Proxy({},{get:(_,key)=>key==='measureText'?()=>({width:0}):()=>{},set:()=>true});}
  setPointerCapture(){}
  remove(){}
  click(){this.onclick?.();}
}
function data(){
  const snapshot={name:'Synthetic triangle',vertices:[[0,0,0],[1,0,0],[0,1,0]].map((co,i)=>({id:i+1,co})),faces:[[1,2,3]],uv_layers:{},guards:{corner_order:[1,2,3]}};
  const plan={schema:'polyweft.plan.v1',id:'a'.repeat(64),sources:Object.fromEntries(['base','left','right'].map((s,i)=>[s,{path:s+'.blend',sha256:String(i+1).repeat(64)}])),snapshots:Object.fromEntries(['base','left','right'].map(s=>[s,structuredClone(snapshot)])),changes:[{key:'vertex:1',domain:'vertex',kind:'conflict',base:[0,0,0],left:[0,0,1],right:[0,0,2]}],blockers:[]};
  plan.snapshots.left.vertices[0].co=[0,0,1];plan.snapshots.right.vertices[0].co=[0,0,2];
  const states=['base','left','right','merged'];
  const report={schema:'polyweft.inspection.v1',plan_id:plan.id,decisions:{schema:'polyweft.decisions.v1',plan_id:plan.id,choices:{'vertex:1':'left'}},source_sha256:Object.fromEntries(Object.entries(plan.sources).map(([s,x])=>[s,x.sha256])),runtime:{version:'synthetic',build_hash:'test'},scope:'Synthetic represented triangles.',complete:true,summary_scope:'all pairs',incomplete_reasons:[],limits:{max_broadphase_visits:100,max_polygon_pairs:100,max_exact_tests:100,max_findings:100,max_provenance_entries:100},work:Object.fromEntries(['broadphase_visits','candidate_polygon_pairs','exact_tests','inspected_polygon_pairs','reported_findings','unreported_findings','witnesses_truncated','unknown_pair_states','provenance_entries','provenance_omitted'].map(k=>[k,0])),geometry:Object.fromEntries(states.map(s=>[s,{vertices:structuredClone(plan.snapshots[s==='merged'?'left':s].vertices),faces:[[1,2,3]],triangles:[{face:0,vertices:[1,2,3],corners:[1,2,3]}],complete:true,triangle_count:1}])),summaries:Object.fromEntries(states.map(s=>[s,{crossings:0,coplanar_overlaps:0,contacts:0,unknown_faces:[],unknown_pairs:0}])),findings:[]};
  const id=createHash('sha256').update(JSON.stringify(report)).digest('hex');
  return {plan,inspectionText:JSON.stringify({id,...report}),inspectionId:id};
}
async function studio({search='?readonly=1',inspectionStatus=200,planStatus=200,inspectionText}={}){
  const fixture=data(),els=new Map([...html.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],new Element()]));
  els.get('notice').hidden=true;els.get('workflow').hidden=true;els.get('snapshot-mode').hidden=true;
  const buttons=(key,values)=>values.map(value=>{const el=new Element('button');el.dataset[key]=value;return el;});
  const lists={'[data-geometry]':buttons('geometry',['merged','left','right']),'[data-view]':buttons('view',['base','left','right','result']),'[data-filter]':buttons('filter',['all','conflict','vertex','uv','material']),'.mesh-card':buttons('state',['base','left','right','result']),'.open-files .file-button':[new Element('label'),new Element('label')]};
  const uv=new Element(),body=new Element('body');
  const document={body,querySelector:s=>s==='.uv-section'?uv:els.get(s.slice(1)),querySelectorAll:s=>lists[s]||[],createElement:tag=>new Element(tag)};
  let downloads=0;
  const fetch=async path=>{const isPlan=path==='./plan.json',status=isPlan?planStatus:inspectionStatus;return {ok:status===200,status,text:async()=>isPlan?JSON.stringify(fixture.plan):inspectionText??fixture.inspectionText};};
  const values={...geometry,...inspectionApi,document,location:{search},fetch,devicePixelRatio:1,ResizeObserver:class{observe(){}},URL:{createObjectURL:()=>{downloads++;return 'blob:test';},revokeObjectURL:()=>{}},Blob,setTimeout:()=>{}};
  const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
  const run=new AsyncFunction(...Object.keys(values),appSource.replace(/^import .*;$/gm,'')+'\nreturn {state:()=>({planId:plan?.id,choices:{...choices},choiceRevision,geometryVariant,yaw,filter,inspectionId:inspection?.id})};');
  const app=await run(...Object.values(values));
  return {els,lists,body,app,fixture,downloads:()=>downloads};
}
function choices(ui){return ui.els.get('changes').children[0].children.at(-1).children;}

test('native snapshot shows full identities and disables every decision control',async()=>{
  const ui=await studio();
  assert.equal(ui.els.get('snapshot-mode').hidden,false);
  assert.equal(ui.els.get('snapshot-plan').textContent,ui.fixture.plan.id);
  assert.equal(ui.els.get('snapshot-inspection').textContent,ui.fixture.inspectionId);
  assert.equal(ui.els.get('status').textContent,'Fixed inspection snapshot');
  assert.match(ui.els.get('export-summary').textContent,/managed in Blender/);
  for(const id of ['open-plan','open-inspection','export-decisions'])assert.equal(ui.els.get(id).disabled,true);
  assert.ok(choices(ui).every(b=>b.disabled));
  assert.equal(choices(ui)[1].attributes['aria-pressed'],'true');
  assert.match(ui.els.get('workflow').children[1].textContent,/does not update/);
});

test('direct handler calls cannot mutate choices, import files or export a native snapshot',async()=>{
  const ui=await studio(),before=ui.app.state();let reads=0;
  for(const b of choices(ui))b.onclick();
  for(const id of ['open-plan','open-inspection']){
    const target={files:[{size:10,text:async()=>{reads++;return '{}';}}],value:'selected.json'};
    await ui.els.get(id).onchange({target});assert.equal(target.value,'');
  }
  ui.els.get('export-decisions').onclick();
  assert.equal(reads,0);assert.equal(ui.downloads(),0);assert.deepEqual(ui.app.state(),before);
  assert.match(ui.els.get('notice').textContent,/managed in Blender/);
});

test('snapshot keeps branch geometry, filters, selection and camera controls usable',async()=>{
  const ui=await studio(),before=ui.app.state();
  ui.lists['[data-geometry]'][1].onclick();assert.equal(ui.app.state().geometryVariant,'left');
  ui.lists['[data-filter]'][1].onclick();assert.equal(ui.app.state().filter,'conflict');
  ui.els.get('changes').children[0].children[0].children[0].onclick();
  ui.els.get('rotate-left').onclick();assert.notEqual(ui.app.state().yaw,before.yaw);
  ui.lists['[data-view]'].at(-1).onclick();assert.equal(ui.app.state().geometryVariant,'merged');
  assert.deepEqual(ui.app.state().choices,before.choices);assert.equal(ui.app.state().inspectionId,before.inspectionId);
  assert.equal(ui.els.get('export-decisions').disabled,true);
});

test('missing or invalid snapshot never offers apply-ready decisions or local imports',async()=>{
  for(const options of [{inspectionStatus:404},{inspectionText:'{}'},{planStatus:404}]){
    const ui=await studio(options);
    assert.equal(ui.els.get('status').textContent,'Inspection snapshot unavailable');
    assert.equal(ui.els.get('preview-label').textContent,'Uninspected preview only');
    assert.equal(ui.els.get('export-decisions').disabled,true);
    assert.equal(ui.els.get('snapshot-inspection').textContent,'Unavailable');
    assert.equal(ui.els.get('notice').hidden,false);
  }
});

test('ordinary editable studio retains choices, imports, staleness and export',async()=>{
  const ui=await studio({search:''});
  assert.equal(ui.els.get('snapshot-mode').hidden,true);
  assert.ok(choices(ui).every(b=>!b.disabled));
  choices(ui)[2].onclick();
  assert.deepEqual(ui.app.state().choices,{'vertex:1':'right'});assert.equal(ui.app.state().choiceRevision,1);
  assert.match(ui.els.get('inspection-status').textContent,/stale/);
  assert.equal(ui.els.get('export-decisions').disabled,false);
  ui.els.get('export-decisions').onclick();assert.equal(ui.downloads(),1);
  let reads=0;
  await ui.els.get('open-plan').onchange({target:{files:[{size:1,text:async()=>{reads++;return JSON.stringify(ui.fixture.plan);}}],value:'p.json'}});
  assert.equal(reads,1);assert.deepEqual(ui.app.state().choices,{});
  await ui.els.get('open-inspection').onchange({target:{files:[{size:1,text:async()=>{reads++;return ui.fixture.inspectionText;}}],value:'i.json'}});
  assert.equal(reads,2);assert.deepEqual(ui.app.state().choices,{'vertex:1':'left'});
});
