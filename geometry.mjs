// SPDX-License-Identifier: GPL-3.0-or-later
// Preview-only geometry. Native apply always recomputes the merge in Python.
export function validatePlan(p) {
  if (!p || p.schema !== 'polyweft.plan.v1' || !/^[a-f0-9]{64}$/.test(p.id || '')) throw Error('Unsupported plan schema or identity.');
  if (!Array.isArray(p.changes) || p.changes.length > 200000 || !Array.isArray(p.blockers)) throw Error('Invalid or oversized change list.');
  const keys = new Set();
  for (const c of p.changes) {
    if (!c || typeof c.key !== 'string' || c.key.length > 600 || keys.has(c.key)) throw Error('Invalid or duplicate change key.');
    keys.add(c.key);
    if (!['left','right','same','conflict'].includes(c.kind) || !['vertex','uv','material'].includes(c.domain)) throw Error('Invalid change domain or kind.');
    for (const v of [c.base,c.left,c.right]) {
      if (Array.isArray(v)) { if (v.length > 4 || !v.every(Number.isFinite)) throw Error('Changes must be finite vectors.'); }
      else if (typeof v !== 'number' || !Number.isFinite(v)) throw Error('Changes must be finite scalars.');
    }
  }
  for (const side of ['base','left','right']) {
    const s=p.snapshots?.[side];
    if (!s || !Array.isArray(s.vertices) || s.vertices.length > 100000 || !Array.isArray(s.faces) || s.faces.length > 200000) throw Error('Invalid or oversized mesh.');
    const ids=new Set();
    for (const v of s.vertices) {
      if (!Number.isSafeInteger(v.id) || ids.has(v.id) || !Array.isArray(v.co) || v.co.length !== 3 || !v.co.every(Number.isFinite)) throw Error('Mesh needs unique vertex identities and finite XYZ values.');
      ids.add(v.id);
    }
    let corners=0;
    for (const f of s.faces) {
      if (!Array.isArray(f) || f.length < 3 || f.length > 10000 || !f.every(id=>ids.has(id))) throw Error('Face refers to an invalid vertex.');
      corners+=f.length;
    }
    if (corners > 600000) throw Error('Mesh exceeds studio corner limit.');
    for (const layer of Object.values(s.uv_layers || {})) {
      if (!Array.isArray(layer) || layer.length > 600000 || !layer.every(c=>Number.isSafeInteger(c.id)&&ids.has(c.vertex)&&Array.isArray(c.uv)&&c.uv.length===2&&c.uv.every(Number.isFinite))) throw Error('Invalid finite UV corners.');
    }
  }
  return p;
}
export function previewVertices(plan, choices) {
  const vertices=plan.snapshots.right.vertices.map(v=>({id:v.id,co:[...v.co]}));
  const byId=new Map(vertices.map(v=>[v.id,v]));
  for (const c of plan.changes) {
    if (c.domain !== 'vertex') continue;
    const vertex=byId.get(Number(c.key.slice('vertex:'.length)));
    if (!vertex) continue;
    const side=c.kind==='left'?'left':c.kind==='conflict'?(choices[c.key]||'right'):'right';
    if (!['base','left','right'].includes(side)) throw Error('Invalid preview choice.');
    vertex.co=[...c[side]];
  }
  return vertices;
}
export function decisionDocument(plan, choices) {
  if (plan.blockers.length) throw Error('This plan is blocked. Native output is unavailable.');
  const conflicts=new Set(plan.changes.filter(c=>c.kind==='conflict').map(c=>c.key));
  for (const key of Object.keys(choices)) {
    if (!conflicts.has(key)) throw Error('Unknown conflict choice.');
    if (!['base','left','right'].includes(choices[key])) throw Error('Invalid conflict choice.');
  }
  if ([...conflicts].some(k=>!choices[k])) throw Error('Unresolved conflicts remain.');
  return {schema:'polyweft.decisions.v1',plan_id:plan.id,choices:{...choices}};
}
export function meshFrame(vertices) {
  const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
  for (const v of vertices) for (let i=0;i<3;i++){lo[i]=Math.min(lo[i],v.co[i]);hi[i]=Math.max(hi[i],v.co[i]);}
  return {center:lo.map((x,i)=>(x+hi[i])/2),radius:Math.max(...lo.map((x,i)=>hi[i]-x),1e-6)/2};
}
// Ear clipping on a dominant-axis projection. Native Blender remains authoritative.
function tessellate(face, coordinates) {
  const points=face.map(id=>coordinates.get(id));
  if (!points.every(Boolean)) return {triangles:[], warning:true};
  const normal=[0,0,0];
  for(let i=0;i<points.length;i++) {
    const a=points[i],b=points[(i+1)%points.length];
    normal[0]+=(a[1]-b[1])*(a[2]+b[2]);
    normal[1]+=(a[2]-b[2])*(a[0]+b[0]);
    normal[2]+=(a[0]-b[0])*(a[1]+b[1]);
  }
  const axis=normal.map(Math.abs).indexOf(Math.max(...normal.map(Math.abs)));
  const axes=[0,1,2].filter(i=>i!==axis),p=points.map(v=>axes.map(i=>v[i]));
  const span=Math.max(...axes.map(i=>Math.max(...points.map(v=>v[i]))-Math.min(...points.map(v=>v[i]))),1e-15);
  const epsilon=span*span*1e-12;
  const cross=(a,b,c)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
  const area=p.reduce((a,v,i)=>{const n=p[(i+1)%p.length];return a+v[0]*n[1]-n[0]*v[1];},0);
  if(Math.abs(area)<=epsilon) return {triangles:[],warning:true};
  const sign=Math.sign(area);
  if(p.every((v,i)=>sign*cross(p[(i+p.length-1)%p.length],v,p[(i+1)%p.length])>=-epsilon)) {
    return {triangles:face.slice(2).map((_,i)=>[face[0],face[i+1],face[i+2]]),warning:false};
  }
  // Bound the exceptional concave case; show a warning instead of false fill.
  if(face.length>512) return {triangles:[],warning:true};
  const remaining=face.map((_,i)=>i),triangles=[];
  let budget=500000;
  while(remaining.length>3) {
    let clipped=false;
    for(let i=0;i<remaining.length;i++) {
      const a=remaining[(i+remaining.length-1)%remaining.length],b=remaining[i],c=remaining[(i+1)%remaining.length];
      const turn=sign*cross(p[a],p[b],p[c]);
      if(Math.abs(turn)<=epsilon) {remaining.splice(i,1);clipped=true;break;}
      if(turn<epsilon) continue;
      let contains=false;
      for(const j of remaining) {
        if(--budget<0) return {triangles:[],warning:true};
        if(j===a||j===b||j===c) continue;
        if(sign*cross(p[a],p[b],p[j])>=-epsilon&&sign*cross(p[b],p[c],p[j])>=-epsilon&&sign*cross(p[c],p[a],p[j])>=-epsilon) {contains=true;break;}
      }
      if(!contains) {triangles.push([face[a],face[b],face[c]]);remaining.splice(i,1);clipped=true;break;}
    }
    if(!clipped) return {triangles:[],warning:true};
  }
  if(remaining.length===3) triangles.push(remaining.map(i=>face[i]));
  return {triangles,warning:false};
}
export function projectMesh(vertices,faces,yaw,pitch,zoom,width,height,frame=meshFrame(vertices),nativeTriangles=null) {
  const scale=Math.min(width,height)*.36*zoom/frame.radius;
  const cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch);
  const points=vertices.map(v=>{
    const [x,y,z]=v.co.map((c,i)=>c-frame.center[i]);
    const rx=cy*x-sy*y,ry=sy*x+cy*y;
    return {id:v.id,x:width/2+rx*scale,y:height/2-(cp*z-sp*ry)*scale,depth:sp*z+cp*ry};
  });
  const byId=new Map(points.map(v=>[v.id,v]));
  const triangles=[],coordinates=new Map(vertices.map(v=>[v.id,v.co]));
  const nativeByFace=new Map();
  if(nativeTriangles)for(const t of nativeTriangles){if(!nativeByFace.has(t.face))nativeByFace.set(t.face,[]);nativeByFace.get(t.face).push(t.vertices);}
  let omittedFaces=0;
  for (let faceIndex=0;faceIndex<faces.length;faceIndex++) {
    const face=faces[faceIndex];
    const tessellation=nativeTriangles?{triangles:nativeByFace.get(faceIndex)||[],warning:false}:tessellate(face,coordinates);
    if(tessellation.warning) omittedFaces++;
    for(const ids of tessellation.triangles) {
      const p=ids.map(id=>byId.get(id));
      triangles.push({ids,face:faceIndex,points:p,depth:p.reduce((s,x)=>s+x.depth,0)/3});
    }
  }
  triangles.sort((a,b)=>b.depth-a.depth);
  return {points,triangles,omittedFaces};
}
