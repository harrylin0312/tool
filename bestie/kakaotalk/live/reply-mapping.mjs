// Pure matching functions. Never infer a legacy ID from a CSV row number.
export const normalize=s=>s.replace(/\r\n?/g,'\n');
const signature=(name,body,day,clock)=>JSON.stringify([name,normalize(body),day,clock]);
export function mapHistory(rows,nodes){
  const byKey=new Map(), proposals=new Map(), claims=new Map(), ids=new Set();
  for(const n of nodes){
    if(ids.has(n.id))throw Error('duplicate HTML ID');
    ids.add(n.id);
    const key=signature(n.name,n.body,n.day,n.clock);
    if(!byKey.has(key))byKey.set(key,[]);
    byKey.get(key).push(n);
  }
  for(let i=0;i<rows.length;i++){
    const r=rows[i], hits=(byKey.get(signature(r.User,r.Message,r.Date.slice(0,10),r.Date.slice(11,16)))||[])
      .filter(n=>!n.stamp||n.stamp===r.Date);
    if(hits.length!==1)continue;
    const n=hits[0];
    proposals.set(i+1,n.id);
    claims.set(n.id,(claims.get(n.id)||0)+1);
  }
  for(const [row,id] of proposals)if(claims.get(id)!==1)proposals.delete(row);
  // Reject non-monotonic matches rather than trusting a potentially shifted history.
  let last=-1;
  for(const id of proposals.values()){
    const num=Number(id.slice(1));
    if(!/^m\d+$/.test(id)||num<=last)throw Error('historical mapping order mismatch');
    last=num;
  }
  return proposals;
}
export function resolveSelector(rows,selector){
  if(!Array.isArray(selector)||selector.length<2||selector.length>4||
     typeof selector[0]!=='string'||typeof selector[1]!=='string'||
     (selector.length>=3&&typeof selector[2]!=='string')||
     (selector.length===4&&(!Number.isInteger(selector[3])||selector[3]<1)))throw Error('invalid reviewed selector');
  const [stamp,name,body,rowNo]=selector;
  const hits=rows.flatMap((r,i)=>r.Date===stamp&&r.User===name&&
    (body===undefined||normalize(r.Message)===normalize(body))&&
    (rowNo===undefined||rowNo===i+1)?[i+1]:[]);
  if(hits.length!==1)throw Error('reviewed selector not unique');
  return hits[0];
}
export function resolvePair(rows,mapping,pair){
  if(!Array.isArray(pair)||pair.length!==2)throw Error('invalid reviewed pair');
  const replyRow=resolveSelector(rows,pair[0]),targetRow=resolveSelector(rows,pair[1]);
  const reply=mapping.get(replyRow),target=mapping.get(targetRow);
  if(targetRow>=replyRow||!reply||!target||Number(target.slice(1))>=Number(reply.slice(1)))throw Error('unverified or reversed reply mapping');
  return [reply,target];
}
