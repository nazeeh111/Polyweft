// SPDX-License-Identifier: GPL-3.0-or-later
import {validatePlan,previewVertices,decisionDocument,meshFrame,projectMesh} from './geometry.mjs';
import {parseInspectionText,validateInspection,inspectionMatches,inspectionStatus} from './inspection.mjs';
const $=s=>document.querySelector(s), sides=['base','left','right','result'];
const colors={base:'#929aa5',left:'#ff8976',right:'#55d6e8',same:'#c7ced9',conflict:'#f9d464'};
let plan=null,choices={},filter='all',selected=null,yaw=-.58,pitch=.46,zoom=1,wire=false,visibleLimit=100,frame=null;
let inspection=null,selectedPair=0,geometryVariant='merged',choiceRevision=0;
const notice=message=>{const el=$('#notice');el.textContent=message;el.hidden=!message;};
function fmt(value){return Array.isArray(value)?'['+value.map(v=>Number(v.toPrecision(6))).join(', ')+']':String(Number(value.toPrecision(6)));}
function node(tag,text,className){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;}
function setPlan(p){
  validatePlan(p);plan=p;choices={};selected=null;visibleLimit=100;
  inspection=null;selectedPair=0;geometryVariant='merged';choiceRevision=0;$('#inspection').hidden=true;
  frame=meshFrame(['base','left','right'].flatMap(s=>p.snapshots[s].vertices));
  $('#mesh-name').textContent=p.snapshots.base.name||'Prepared target';
  $('#mesh-count').textContent=`${p.snapshots.base.vertices.length.toLocaleString()} vertices · ${p.snapshots.base.faces.length.toLocaleString()} faces · one prepared target`;
  $('#identity').textContent='Plan '+p.id.slice(0,16)+' · local review';
  for(const side of ['base','left','right']){
    const source=p.sources?.[side];$('#hash-'+side).textContent=source?.sha256?.slice(0,12)||'captured snapshot';
    $('#hash-'+side).title=source?.sha256||'';
  }
  const select=$('#uv-layer');select.replaceChildren();
  for(const name of Object.keys(p.snapshots.base.uv_layers||{})) {const opt=node('option',name);opt.value=name;select.append(opt);}
  $('.uv-section').hidden=!select.options.length;
  const excluded=p.observed_exclusions||[];$('#exclusions').hidden=!excluded.length;
  $('#exclusion-list').replaceChildren(...excluded.slice(0,100).map(x=>node('li',typeof x==='string'?x:JSON.stringify(x))));
  notice(p.blockers.length?'Native apply blocked:\n'+p.blockers.map(b=>b.message||b.code||String(b)).join('\n'):'');
  refresh();
}
function refresh(){
  if(!plan)return;
  const conflicts=plan.changes.filter(c=>c.kind==='conflict'),unresolved=conflicts.filter(c=>!choices[c.key]);
  $('#status').textContent=plan.blockers.length?'Refused native plan':unresolved.length?`${unresolved.length} choices remaining`:'Decisions ready for native apply';
  $('#change-count').textContent=`${plan.changes.length.toLocaleString()} payload edits`;
  $('#conflict-count').textContent=`${conflicts.length} competing values · ${conflicts.length-unresolved.length} resolved`;
  $('#preview-label').textContent=unresolved.length?'Unresolved values show right':'All choices reflected';
  $('#export-decisions').disabled=!!plan.blockers.length||!!unresolved.length;
  $('#export-summary').textContent=plan.blockers.length?'Resolve structural blockers in Blender before merging.':unresolved.length?`Choose an entire value for each of ${unresolved.length} remaining conflicts.`:'Export choices, then let Blender save and verify a fresh scene.';
  renderChanges();renderInspection();drawAll();
}
function usableInspection(){return inspection&&plan&&inspectionMatches(inspection,plan,choices);}
function pairFinding(){return usableInspection()?inspection.findings[selectedPair]:null;}
function setInspection(r){
  validateInspection(r,plan);
  inspection=r;selectedPair=0;geometryVariant='merged';
  if(choiceRevision===0)choices={...r.decisions.choices};
  refresh();
}
function renderInspection(){
  const section=$('#inspection');section.hidden=!inspection;
  document.body.classList.toggle('has-inspection',!!inspection);
  for(const side of sides)$('#pair-state-'+side).textContent='';
  $('#pair-history-summary').textContent='';
  if(!inspection)return;
  const usable=usableInspection();section.classList.toggle('stale',!usable);
  if(usable)$('#preview-label').textContent=geometryVariant==='merged'?'Inspected configured merge':geometryVariant+' branch alone · geometry comparison';
  $('#inspection-status').textContent=usable?inspectionStatus(inspection):'Choices changed. This recorded inspection is stale. Rerun polyweft inspect with your exported choices.';
  $('#inspection-runtime').textContent=`Blender ${inspection.runtime.version} · ${inspection.id.slice(0,12)}`;
  $('#inspection-counts').replaceChildren();
  for(const side of ['base','left','right','merged']){
    const s=inspection.summaries[side],card=node('article',undefined,'inspection-count');
    card.append(node('small',side==='base'?'ANCESTOR':side==='merged'?'COMBINED':side.toUpperCase()),node('strong',usable?String(s.crossings+s.coplanar_overlaps):'—'),node('span',usable?`${s.crossings} crossing · ${s.coplanar_overlaps} overlap · ${s.contacts} contact`:'Recorded result is stale'));
    $('#inspection-counts').append(card);
  }
  $('#inspection-coverage').textContent=usable?`${inspection.summary_scope}. ${inspection.complete?'Complete within the declared represented-surface model.':'Incomplete coverage; zero counts do not establish separation.'} ${Object.values(inspection.summaries).reduce((n,s)=>n+s.unknown_faces.length,0)} state faces remain unknown.`:'Recorded face witnesses are disabled until choices match again.';
  $('#inspection-work').textContent=JSON.stringify({reasons:inspection.incomplete_reasons,limits:inspection.limits,work:inspection.work},null,2);
  const select=$('#inspection-pair'),previous=selectedPair;select.replaceChildren();
  inspection.findings.slice(0,1000).forEach((f,i)=>{const o=node('option',`Faces ${f.faces[0]} ↔ ${f.faces[1]} · ${f.classification}`);o.value=String(i);select.append(o);});
  selectedPair=Math.min(previous,Math.max(0,select.options.length-1));select.value=String(selectedPair);select.disabled=!usable||!inspection.findings.length;
  for(const b of document.querySelectorAll('[data-geometry]')){b.disabled=!usable;b.setAttribute('aria-pressed',String(b.dataset.geometry===geometryVariant));}
  const detail=$('#inspection-detail');detail.replaceChildren();
  if(!usable){$('#pair-history-summary').textContent='Inspection is stale. Export choices and inspect again.';return;}
  if(!inspection.findings.length){detail.append(node('p','No retained interfering face pairs. Read the coverage limits before treating this as a negative result.'));return;}
  const f=inspection.findings[selectedPair];
  $('#pair-history-summary').textContent=`Selected faces ${f.faces[0]} (yellow) / ${f.faces[1]} (violet) · ancestor ${f.history.base.kind} · left ${f.history.left.kind} · right ${f.history.right.kind} · combined ${f.history.merged.kind}`;
  for(const side of sides){const kind=f.history[side==='result'?geometryVariant:side].kind;$('#pair-state-'+side).textContent=kind;$('#pair-state-'+side).dataset.kind=kind;}
  detail.append(node('h3',`Same faces, four states: ${f.faces.join(' ↔ ')}`));
  const history=node('div',undefined,'pair-history');
  for(const side of ['base','left','right','merged']){const p=node('p');p.append(node('b',side==='merged'?'Combined':side),node('span',f.history[side].kind));history.append(p);}detail.append(history);
  const points=f.history.merged.witnesses[0]?.points||[];
  if(points.length){detail.append(node('p','Exact coordinates of one native triangle witness:'));const pre=node('pre',points.map(p=>'('+p.join(', ')+')').join('\n'));detail.append(pre);}
  detail.append(node('h4','Accepted edits on these faces'));
  const list=node('ul');
  for(const edit of f.provenance.slice(0,30)){list.append(node('li',`${edit.key} · ${edit.selected}${edit.explicit_choice?' (explicit choice)':''} · ${fmt(edit.base)} → ${fmt(edit.value)} · source ${edit.source_sha256.slice(0,12)}`));}
  if(f.provenance.length>30)list.append(node('li',`${f.provenance.length-30} more edits retained in inspection.json.`));detail.append(list);
  detail.append(node('p','These are contributing accepted edits, not a minimal causal set. Left/right alone compares complete branch geometry for this same face pair.'));
}
function renderChanges(){
  const query=$('#search').value.toLocaleLowerCase();
  const matches=plan.changes.filter(c=>(filter==='all'||c.kind===filter||c.domain===filter)&&`${c.key} ${c.label||''}`.toLocaleLowerCase().includes(query));
  const list=$('#changes');list.replaceChildren();
  for(const c of matches.slice(0,visibleLimit)){
    const article=node('article',undefined,'change'),heading=node('div',undefined,'change-heading');
    const label=node('button',c.label||c.key);label.className='locate-edit';label.title='Locate this edit in the geometry preview';
    label.onclick=()=>{selected=c.key;drawAll();};
    const badge=node('span',c.kind==='same'?'SAME EDIT':c.kind==='conflict'?(choices[c.key]?'RESOLVED':'CHOOSE'):c.kind.toUpperCase(),`badge ${c.kind}`);
    heading.append(label,badge);article.append(heading);
    const values=node('dl',undefined,'change-values');
    for(const side of ['base','left','right']){const dt=node('dt',side.toUpperCase(),side);const dd=node('dd',fmt(c[side]),side);values.append(dt,dd);}
    article.append(values);
    if(c.kind==='conflict'){
      const buttons=node('div',undefined,'choices');buttons.setAttribute('role','group');buttons.setAttribute('aria-label','Resolve '+(c.label||c.key));
      for(const side of ['base','left','right']){const button=node('button',side==='base'?'Ancestor':side==='left'?'Keep left':'Keep right');button.setAttribute('aria-pressed',String(choices[c.key]===side));button.onclick=()=>{choices[c.key]=side;choiceRevision++;selected=c.key;geometryVariant='merged';refresh();};buttons.append(button);}
      article.append(buttons);
    }
    list.append(article);
  }
  if(!matches.length)list.append(node('p','No changes match this view.','empty'));
  if(matches.length>visibleLimit){const more=node('button',`Show next ${Math.min(100,matches.length-visibleLimit)} of ${matches.length.toLocaleString()}`);more.className='more-edits';more.onclick=()=>{visibleLimit+=100;renderChanges();};list.append(more);}
}
function setupCanvas(canvas){
  const rect=canvas.getBoundingClientRect(),dpr=Math.min(devicePixelRatio||1,2);
  const width=Math.max(1,rect.width),height=Math.max(1,rect.height);
  if(canvas.width!==Math.round(width*dpr)||canvas.height!==Math.round(height*dpr)){canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);}
  const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height);return {ctx,width,height};
}
function drawMesh(side){
  const canvas=$('#mesh-'+side),{ctx,width,height}=setupCanvas(canvas);
  ctx.strokeStyle='#30353e';ctx.lineWidth=.5;
  for(let x=20;x<width;x+=28){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,height);ctx.stroke();}
  for(let y=20;y<height;y+=28){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(width,y);ctx.stroke();}
  if(!plan){ctx.fillStyle='#a4acb8';ctx.font='11px ui-monospace,monospace';ctx.textAlign='center';ctx.fillText('NATIVE MESH SNAPSHOT',width/2,height/2);return;}
  const native=usableInspection()?inspection.geometry[side==='result'?geometryVariant:side]:null;
  const snapshot=side==='result'?plan.snapshots.right:plan.snapshots[side];
  const vertices=native?native.vertices:side==='result'?previewVertices(plan,choices):snapshot.vertices;
  const projected=projectMesh(vertices,native?.faces||snapshot.faces,yaw,pitch,zoom,width,height,frame,native?.triangles||null);
  const finding=pairFinding();
  const edits=new Map(plan.changes.filter(c=>c.domain==='vertex').map(c=>[Number(c.key.slice(7)),c]));
  for(const tri of projected.triangles){
    const [a,b,c]=tri.points;const area=(b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);
    const shade=area>0?44:30;
    let editColor=null;
    if(side!=='base')for(const id of tri.ids){const e=edits.get(id);if(!e)continue;const visible=side==='result'||e.kind==='same'||e.kind==='conflict'||e.kind===side;if(visible){editColor=colors[e.kind];if(e.kind==='conflict')break;}}
    ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.lineTo(c.x,c.y);ctx.closePath();
    const witnessIndex=finding?.faces.indexOf(tri.face)??-1;
    const faceColor=witnessIndex===0?'#ffe36d':witnessIndex===1?'#ad9dff':null;
    ctx.fillStyle=faceColor||editColor||`hsl(220 6% ${shade}%)`;ctx.globalAlpha=faceColor?.95:editColor?.86:1;ctx.fill();ctx.globalAlpha=1;
    ctx.strokeStyle=wire?'#101216cc':editColor?'#17191d88':'#b0b9c438';ctx.lineWidth=wire?.6:.35;ctx.stroke();
  }
  if(projected.omittedFaces){ctx.fillStyle='#f9d464';ctx.font='10px ui-monospace,monospace';ctx.textAlign='left';ctx.fillText(`${projected.omittedFaces} degenerate/complex faces omitted; inspect in Blender`,12,height-12);}
  if(native){ctx.fillStyle='#c7ced9';ctx.font='10px ui-monospace,monospace';ctx.textAlign='left';ctx.fillText(`Native triangles${side==='result'&&geometryVariant!=='merged'?' · '+geometryVariant+' branch alone':''}`,12,height-12);}
  if(selected?.startsWith('vertex:')){
    const v=projected.points.find(v=>v.id===Number(selected.slice(7)));
    if(v){ctx.beginPath();ctx.arc(v.x,v.y,6,0,2*Math.PI);ctx.strokeStyle='#ffe36d';ctx.lineWidth=2;ctx.stroke();ctx.fillStyle='#ffe36d';ctx.font='10px ui-monospace,monospace';ctx.fillText(selected,v.x+10,v.y-10);}
  }
}
function drawUV(){
  const {ctx,width,height}=setupCanvas($('#uv-view'));const name=$('#uv-layer').value;
  if(!plan||!name){ctx.fillStyle='#b1bac6';ctx.font='11px ui-monospace,monospace';ctx.fillText('No UV layer captured.',16,30);return;}
  const layers=['base','left','right'].map(side=>plan.snapshots[side].uv_layers?.[name]||[]),all=layers.flat();
  let minU=0,maxU=1,minV=0,maxV=1;for(const c of all){minU=Math.min(minU,c.uv[0]);maxU=Math.max(maxU,c.uv[0]);minV=Math.min(minV,c.uv[1]);maxV=Math.max(maxV,c.uv[1]);}
  const scale=Math.min((width-40)/(maxU-minU||1),(height-30)/(maxV-minV||1));
  const x=u=>width/2+(u-(maxU+minU)/2)*scale,y=v=>height/2-(v-(maxV+minV)/2)*scale;
  ctx.strokeStyle='#46505f';ctx.strokeRect(x(0),y(1),scale,scale);
  layers.forEach((layer,i)=>{
    const side=['base','left','right'][i];ctx.strokeStyle=colors[side];ctx.lineWidth=i===0?.6:1;ctx.globalAlpha=i===0?.45:.7;
    let offset=0;
    for(const face of plan.snapshots[side].faces){
      const corners=layer.slice(offset,offset+face.length);offset+=face.length;if(corners.length!==face.length)break;
      ctx.beginPath();corners.forEach((c,j)=>j?ctx.lineTo(x(c.uv[0]),y(c.uv[1])):ctx.moveTo(x(c.uv[0]),y(c.uv[1])));ctx.closePath();ctx.stroke();
    }
    ctx.globalAlpha=1;
    if(selected?.startsWith('uv:'+encodeURIComponent(name)+':')){const id=Number(selected.split(':').at(-1)),c=layer.find(c=>c.id===id);if(c){ctx.fillStyle=colors[side];ctx.beginPath();ctx.arc(x(c.uv[0]),y(c.uv[1]),4,0,2*Math.PI);ctx.fill();}}
  });
}
function drawAll(){for(const side of sides)drawMesh(side);drawUV();}
$('#open-plan').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;if(file.size>32*1024*1024)throw Error('Plan exceeds the studio 32 MiB limit.');setPlan(JSON.parse(await file.text()));}catch(error){notice(error.message);}finally{e.target.value='';}};
$('#open-inspection').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;if(!plan)throw Error('Load the matching plan first.');if(file.size>32*1024*1024)throw Error('Inspection exceeds the studio 32 MiB limit.');setInspection(await parseInspectionText(await file.text()));}catch(error){notice(error.message);}finally{e.target.value='';}};
$('#inspection-pair').onchange=e=>{selectedPair=Number(e.target.value);renderInspection();drawAll();};
function selectView(side){
  if(!sides.includes(side))return;
  for(const card of document.querySelectorAll('.mesh-card'))card.classList.toggle('selected-view',card.dataset.state===side);
  for(const b of document.querySelectorAll('[data-view]'))b.setAttribute('aria-pressed',String(b.dataset.view===side));
  drawAll();
}
for(const b of document.querySelectorAll('[data-view]'))b.onclick=()=>{
  if(b.dataset.view==='result'){geometryVariant='merged';renderInspection();}
  selectView(b.dataset.view);
};
for(const b of document.querySelectorAll('[data-geometry]'))b.onclick=()=>{geometryVariant=b.dataset.geometry;renderInspection();selectView('result');};
$('#help-toggle').onclick=()=>{const hidden=!$('#workflow').hidden;$('#workflow').hidden=hidden;$('#help-toggle').setAttribute('aria-expanded',String(!hidden));};
for(const b of document.querySelectorAll('[data-filter]'))b.onclick=()=>{filter=b.dataset.filter;visibleLimit=100;for(const x of document.querySelectorAll('[data-filter]'))x.setAttribute('aria-pressed',String(x===b));if(plan)renderChanges();};
$('#search').oninput=()=>{visibleLimit=100;if(plan)renderChanges();};
$('#rotate-left').onclick=()=>{yaw-=.2;drawAll();};$('#rotate-right').onclick=()=>{yaw+=.2;drawAll();};
$('#reset-view').onclick=()=>{yaw=-.58;pitch=.46;zoom=1;$('#zoom').value=1;drawAll();};
$('#wireframe').onchange=e=>{wire=e.target.checked;drawAll();};$('#zoom').oninput=e=>{zoom=Number(e.target.value);drawAll();};$('#uv-layer').onchange=drawUV;
for(const side of sides){const canvas=$('#mesh-'+side);let drag=null;canvas.onpointerdown=e=>{drag=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);};canvas.onpointermove=e=>{if(!drag)return;yaw+=(e.clientX-drag[0])*.008;pitch=Math.max(-1.4,Math.min(1.4,pitch+(e.clientY-drag[1])*.008));drag=[e.clientX,e.clientY];drawAll();};canvas.onpointerup=()=>{drag=null;};canvas.onpointercancel=()=>{drag=null;};}
$('#export-decisions').onclick=()=>{
  try{const data=decisionDocument(plan,choices),blob=new Blob([JSON.stringify(data,null,2)+'\n'],{type:'application/json'}),url=URL.createObjectURL(blob),a=node('a');a.href=url;a.download='decisions.json';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);notice('Decisions exported. No Blender file has been written. Run the native apply command to save and verify the result.');}catch(error){notice(error.message);}
};
new ResizeObserver(()=>drawAll()).observe($('#workspace'));
try{const response=await fetch('./plan.json',{cache:'no-store'});if(response.ok){const text=await response.text();if(text.length>32*1024*1024)throw Error('Plan exceeds the studio size limit.');setPlan(JSON.parse(text));}else if(response.status!==404)notice('Could not load plan.json. Use Open plan to select a local review.');}catch(error){notice('Open a local plan to begin. '+error.message);}
if(plan){const loadedPlan=plan;try{const response=await fetch('./inspection.json',{cache:'no-store'});if(response.ok&&plan===loadedPlan){const text=await response.text();if(text.length>32*1024*1024)throw Error('Inspection exceeds the studio size limit.');const r=await parseInspectionText(text);if(plan===loadedPlan)setInspection(r);}else if(response.status!==404)notice('Could not load inspection.json.');}catch(error){notice('Inspection not loaded: '+error.message);}}
drawAll();
