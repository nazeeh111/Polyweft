// SPDX-License-Identifier: GPL-3.0-or-later
// Display validation for a recorded native inspection. Native CLI owns predicates.
import {validatePlan, decisionDocument, previewVertices} from './geometry.mjs';

const states=['base','left','right','merged'];
const kinds=new Set(['separated','adjacent-boundary','crossing','coplanar-overlap','contact','unknown']);
const interference=new Set(['crossing','coplanar-overlap']);
const hash=x=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
const canonical=x=>Array.isArray(x)?x.map(canonical):x&&typeof x==='object'?Object.fromEntries(Object.keys(x).sort().map(k=>[k,canonical(x[k])])):x;
const equal=(a,b)=>JSON.stringify(canonical(a))===JSON.stringify(canonical(b));
const count=x=>Number.isSafeInteger(x)&&x>=0;
function require(value,message){if(!value)throw Error('Invalid inspection: '+message);}
function sameChoices(a,b){return equal(Object.entries(a).sort(),Object.entries(b).sort());}

export async function parseInspectionText(text) {
  require(typeof text==='string'&&text.length<=32*1024*1024,'file size');
  const raw=text.trim(),report=JSON.parse(raw);
  require(hash(report.id),'report checksum');
  const marker=`"id":"${report.id}",`,start=raw.indexOf(marker);
  require(start>=0&&raw.indexOf(marker,start+marker.length)<0,'use the original inspection.json file without editing or reformatting');
  const content=raw.slice(0,start)+raw.slice(start+marker.length);
  require(globalThis.crypto?.subtle,'browser needs a secure context for checksum verification');
  const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(content));
  const digest=Array.from(new Uint8Array(bytes),x=>x.toString(16).padStart(2,'0')).join('');
  require(digest===report.id,'report checksum changed; use the original inspection.json file');
  return report;
}

export function validateInspection(r,p) {
  validatePlan(p);
  require(r&&r.schema==='polyweft.inspection.v1'&&hash(r.id)&&r.plan_id===p.id,'schema or plan identity');
  require(r.decisions?.schema==='polyweft.decisions.v1'&&r.decisions.plan_id===p.id,'decision identity');
  const decisions=decisionDocument(p,r.decisions.choices||{});
  require(sameChoices(decisions.choices,r.decisions.choices),'decision fields');
  require(typeof r.complete==='boolean'&&['all pairs','bounded inspected pairs'].includes(r.summary_scope),'coverage');
  require(!r.complete||r.summary_scope==='all pairs','complete coverage scope');
  require(typeof r.scope==='string'&&r.scope.length<=3000,'scope');
  require(r.runtime&&typeof r.runtime.version==='string'&&r.runtime.version.length<=200&&typeof r.runtime.build_hash==='string'&&r.runtime.build_hash.length<=200,'runtime');
  require(r.limits&&typeof r.limits==='object'&&r.work&&typeof r.work==='object','work bounds');
  require(Array.isArray(r.incomplete_reasons)&&r.incomplete_reasons.length<=100&&r.incomplete_reasons.every(x=>typeof x==='string'&&x.length<=3000),'coverage reasons');
  for(const field of ['broadphase_visits','candidate_polygon_pairs','exact_tests','inspected_polygon_pairs','reported_findings','unreported_findings','witnesses_truncated','unknown_pair_states','provenance_entries','provenance_omitted'])require(count(r.work[field]),'work counter '+field);
  for(const [counter,limit] of [['broadphase_visits','max_broadphase_visits'],['candidate_polygon_pairs','max_polygon_pairs'],['exact_tests','max_exact_tests'],['reported_findings','max_findings'],['provenance_entries','max_provenance_entries']])require(count(r.limits[limit])&&r.work[counter]<=r.limits[limit],'work exceeded '+limit);
  require(r.work.inspected_polygon_pairs<=r.work.candidate_polygon_pairs,'pair coverage');
  if(r.complete)require(!r.incomplete_reasons.length&&r.work.inspected_polygon_pairs===r.work.candidate_polygon_pairs&&['unreported_findings','witnesses_truncated','unknown_pair_states','provenance_omitted'].every(k=>r.work[k]===0),'complete report has incomplete work');
  for(const side of ['base','left','right'])require(hash(r.source_sha256?.[side])&&r.source_sha256[side]===p.sources?.[side]?.sha256,'source bytes');
  const expectedMerged=previewVertices(p,decisions.choices);
  require(r.geometry&&equal(Object.keys(r.geometry).sort(),[...states].sort()),'four states');
  let exactUpperBound=0;
  for(const side of states) {
    const g=r.geometry[side],snapshot=p.snapshots[side==='merged'?'right':side];
    require(g&&Array.isArray(g.vertices)&&g.vertices.length<=20000&&equal(g.vertices,side==='merged'?expectedMerged:snapshot.vertices),'captured vertices');
    require(Array.isArray(g.faces)&&equal(g.faces,snapshot.faces),'face correspondence');
    require(Array.isArray(g.triangles)&&g.triangles.length<=80000,'native triangle bounds');
    require(typeof g.complete==='boolean'&&count(g.triangle_count)&&g.triangles.length<=g.triangle_count&&(!g.complete||g.triangle_count===g.triangles.length),'native capture coverage');
    if(r.complete)require(g.complete,'complete report has partial native capture');
    const cornerOrder=snapshot.guards?.corner_order,offsets=[];
    let offset=0;for(const f of g.faces){offsets.push(offset);offset+=f.length;}
    const faceCounts=new Array(g.faces.length).fill(0),seen=new Set();
    for(const t of g.triangles) {
      require(t&&count(t.face)&&t.face<g.faces.length&&Array.isArray(t.vertices)&&t.vertices.length===3&&Array.isArray(t.corners)&&t.corners.length===3,'native triangle');
      for(let i=0;i<3;i++) {
        const face=g.faces[t.face];
        require(face.includes(t.vertices[i])&&Number.isSafeInteger(t.corners[i])&&t.corners[i]>0,'triangle membership');
        if(cornerOrder)require(face.some((id,j)=>id===t.vertices[i]&&cornerOrder[offsets[t.face]+j]===t.corners[i]),'triangle corner correspondence');
      }
      const signature=t.face+':'+[...t.corners].sort((a,b)=>a-b).join(',');
      require(!seen.has(signature),'duplicate native triangle');seen.add(signature);faceCounts[t.face]++;
    }
    if(r.complete)require(faceCounts.every((n,i)=>n===g.faces[i].length-2),'complete report omitted a face surface');
    exactUpperBound+=g.triangles.length*(g.triangles.length-1)/2-faceCounts.reduce((n,x)=>n+x*(x-1)/2,0);
    const s=r.summaries?.[side];
    require(s&&['crossings','coplanar_overlaps','contacts'].every(k=>count(s[k]))&&Array.isArray(s.unknown_faces)&&s.unknown_faces.length<=g.faces.length&&s.unknown_faces.every(i=>count(i)&&i<g.faces.length),'state counts');
    require(count(s.unknown_pairs)&&s.crossings+s.coplanar_overlaps+s.contacts+s.unknown_pairs<=r.work.inspected_polygon_pairs,'state pair counts');
    if(r.complete)require(!s.unknown_faces.length&&s.unknown_pairs===0,'complete report has unknown geometry');
  }
  require(r.work.exact_tests<=exactUpperBound,'exact work exceeds represented triangle pairs');
  require(Array.isArray(r.findings)&&r.findings.length<=10000,'finding bounds');
  require(r.work.reported_findings===r.findings.length,'retained finding count');
  if(r.complete)require(r.summaries.merged.crossings+r.summaries.merged.coplanar_overlaps===r.findings.length,'complete report omitted interference findings');
  const changes=new Map(p.changes.filter(c=>c.domain==='vertex').map(c=>[c.key,c]));
  let provenanceCount=0;
  for(const finding of r.findings) {
    require(finding&&Array.isArray(finding.faces)&&finding.faces.length===2&&finding.faces[0]<finding.faces[1]&&finding.faces.every(i=>count(i)&&i<r.geometry.merged.faces.length),'witness faces');
    require(['merge-only','prior-interference','prior-contact','uncertain-history'].includes(finding.classification),'classification');
    for(const side of states) {
      const h=finding.history?.[side],g=r.geometry[side];
      require(h&&kinds.has(h.kind)&&Array.isArray(h.witnesses)&&h.witnesses.length<=64,'pair history');
      for(const w of h.witnesses) {
        require(Array.isArray(w.triangles)&&w.triangles.length===2&&w.triangles.every((i,j)=>count(i)&&i<g.triangles.length&&g.triangles[i].face===finding.faces[j]),'witness triangle identity');
        require(Array.isArray(w.points)&&w.points.length<=8&&w.points.every(point=>Array.isArray(point)&&point.length===3&&point.every(x=>typeof x==='string'&&x.length<=2048&&/^-?\d+(?:\/[1-9]\d*)?$/.test(x))),'exact witness coordinates');
      }
    }
    if(finding.classification==='merge-only')require(interference.has(finding.history.merged.kind)&&['base','left','right'].every(s=>['separated','adjacent-boundary'].includes(finding.history[s].kind)),'merge-only history');
    require(Array.isArray(finding.provenance)&&finding.provenance.length<=100000,'provenance bounds');
    provenanceCount+=finding.provenance.length;
    for(const v of finding.provenance) {
      const c=changes.get(v.key),selected=c?.kind==='conflict'?decisions.choices[c.key]:c?.kind==='left'?'left':'right';
      require(c&&v.vertex===Number(c.key.slice(7))&&v.selected===selected&&v.explicit_choice===(c.kind==='conflict')&&equal(v.base,c.base)&&equal(v.value,c[selected])&&v.source_sha256===r.source_sha256[selected],'accepted edit');
      require(Array.isArray(v.faces)&&v.faces.length>0&&v.faces.every(i=>finding.faces.includes(i)&&r.geometry.merged.faces[i].includes(v.vertex)),'edit face membership');
    }
  }
  require(provenanceCount===r.work.provenance_entries,'retained provenance count');
  return r;
}

export function inspectionMatches(r,p,choices) {
  try {return r.plan_id===p.id&&sameChoices(r.decisions.choices,decisionDocument(p,choices).choices);}
  catch {return false;}
}

export function inspectionStatus(r) {
  const introduced=r.findings.filter(f=>f.classification==='merge-only').length;
  if(!r.complete)return `Inspection incomplete · ${introduced} retained merge-only pairs`;
  return introduced?`${introduced} retained pairs interfere only after this merge`:'No merge-only interference observed in these native triangles';
}
