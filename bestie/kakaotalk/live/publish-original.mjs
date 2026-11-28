import {readFileSync, writeFileSync, renameSync, mkdirSync, existsSync, linkSync, unlinkSync} from 'node:fs';
import {createCipheriv, createDecipheriv, randomBytes, createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {parseHTML} from 'linkedom';
import {normalize,mapHistory,resolvePair,validRow,isNotice,lastTimestamp} from './reply-mapping.mjs';

// Run from this folder after installing linkedom. Pass the private link on stdin.
// First creation (only if original/index.html is absent): node publish-original.mjs current.csv previous.csv
// Legacy migration / first creation require TRUSTED_HISTORY_SHA256 from a separately verified historical CSV.
// Later runs: node publish-original.mjs current.csv
const [current, previous] = process.argv.slice(2);
const key = Buffer.from(readFileSync(0,'utf8').trim().split('#').pop(),'base64url');
const base = new URL('../index.html',import.meta.url);
const out = new URL('../original/index.html',import.meta.url);
if(previous && existsSync(out))throw Error('原文快照已存在，禁止重新初始化');
const shell = readFileSync(previous ? base : out,'utf8');
const pattern = /const snapshot = \{ nonce: '([^']+)', ciphertext: '([^']+)' \};/;
const [,nonce,ciphertext] = shell.match(pattern);
const bytes = Buffer.from(ciphertext,'base64');
const decipher = createDecipheriv('aes-256-gcm',key,Buffer.from(nonce,'base64'));
decipher.setAuthTag(bytes.subarray(-16));
const plain = Buffer.concat([decipher.update(bytes.subarray(0,-16)),decipher.final()]).toString();
const {document} = parseHTML(plain);
const main=document.querySelector('main');
function csv(path){
  const code = "import csv,json,sys;print(json.dumps(list(csv.DictReader(open(sys.argv[1],encoding='utf-8-sig',newline='')))))";
  return JSON.parse(execFileSync('python3',['-c',code,path],{maxBuffer:128*1024*1024}));
}
function anchor(rows){
  return createHash('sha256').update(JSON.stringify(rows.slice(-12).map(r=>r.Date))).digest('hex');
}
const rows=csv(current);
const old=previous ? csv(previous) : null;
const count=old?.length ?? Number(main.dataset.exportCount);
if (!count || rows.length<count || anchor(rows.slice(0,count))!==(old ? anchor(old) : main.dataset.exportAnchor)) throw Error('匯出檔未銜接上次進度');
if(rows.some(r=>!validRow(r)))throw Error('CSV 欄位或時間格式錯誤');
const through=lastTimestamp(rows);
if(!through)throw Error('CSV 沒有可用時間');
const throughISO=through.replace(' ','T')+'+08:00';
const digest=rs=>createHash('sha256').update(JSON.stringify(rs.map(r=>[r.Date,r.User,r.Message]))).digest('hex');
if(old && digest(old)!==digest(rows.slice(0,count)))throw Error('歷史紀錄未對齊');
const prefixDigest=digest(rows.slice(0,count));
const lockedDigest=old?null:main.dataset.exportDigest;
if(lockedDigest){
  if(lockedDigest!==prefixDigest)throw Error('歷史 CSV 內容已變更');
}else{
  // A timestamp anchor alone cannot authenticate legacy CSV contents.
  // Do not calculate this expected digest from the unverified current input.
  const trusted=process.env.TRUSTED_HISTORY_SHA256;
  if(!/^[a-f0-9]{64}$/.test(trusted||''))throw Error('首次遷移需獨立核對的 TRUSTED_HISTORY_SHA256');
  if(trusted!==prefixDigest)throw Error('歷史 CSV 與可信基準不符');
}

const esc=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
if(old){
  for(const n of document.querySelectorAll('.translation,.quote-translation,.quote-language'))n.remove();
  for(const n of document.querySelectorAll('p.notice[id]')){
    const br=n.querySelector('br');
    if(br && Number(n.id.slice(1))>=446){while(br.nextSibling)br.nextSibling.remove();br.remove();n.append(' · '+n.dataset.clock)}
  }
}
// Reuse the existing palette and the first known color for each display name.
const avatarColors=new Map(), paletteSet=new Set();
const colorPattern=/background:\s*(#[0-9a-fA-F]{6})\b/;
for(const article of document.querySelectorAll('article')){
  const node=article.querySelector('.avatar:not(.uji)');
  const name=article.querySelector('.name')?.textContent;
  const color=node?.getAttribute('style')?.match(colorPattern)?.[1];
  if(color && name!==undefined){
    paletteSet.add(color);
    if(!avatarColors.has(name))avatarColors.set(name,color);
  }
}
const palette=[...paletteSet].sort();
if(!palette.length)palette.push('#a9c9f8','#f0d8a3','#cec5eb');
function avatarColor(name){
  if(!avatarColors.has(name)){
    let hash=2166136261;
    for(const ch of name)hash=Math.imul(hash^ch.codePointAt(0),16777619);
    avatarColors.set(name,palette[(hash>>>0)%palette.length]);
  }
  return avatarColors.get(name);
}
// Repair legacy markup without changing message IDs, content or reply links.
let repairedAvatars=0,repairedReplies=0;
for(const article of document.querySelectorAll('article')){
  const node=article.querySelector('.avatar:not(.uji)');
  const name=article.querySelector('.name')?.textContent;
  const content=Array.from(article.children).find(n=>n.tagName==='DIV' && n.querySelector('.line'));
  if(!content)throw Error('訊息內容容器遺失: '+article.id);
  if(node && name!==undefined && !colorPattern.test(node.getAttribute('style')||'')){
    const existing=node.getAttribute('style')||'';
    node.setAttribute('style',existing+(existing && !existing.endsWith(';')?';':'')+'background:'+avatarColor(name));
    repairedAvatars++;
  }
  for(const child of Array.from(article.children)){
    if(child.matches('details.replies')){content.append(child);repairedReplies++}
  }
}
// A legacy snapshot has no row metadata. Match exact text, name and time.
function originalText(node){
  return Array.from(node.childNodes).map(n=>n.nodeType===3?n.textContent:n.tagName==='BR'?'\n':originalText(n)).join('');
}
function descriptor(a){
  return {id:a.id,name:a.querySelector('.name').textContent,
    body:originalText(a.querySelector('.original')),day:a.dataset.day,clock:a.dataset.clock,
    stamp:(a.querySelector('time')?.getAttribute('datetime')||'').slice(0,19).replace('T',' ')};
}
const history=Array.from(main.querySelectorAll('article[id]'));
const mapping=mapHistory(rows.slice(0,count),history.map(descriptor));
const mappedIds=new Set(mapping.values());
let metadataChanges=0;
function setAttr(node,key,value){
  if(node.getAttribute(key)!==value){node.setAttribute(key,value);metadataChanges++}
}
function remember(node,rowNo){
  const row=rows[rowNo-1];
  setAttr(node,'data-source-row',String(rowNo));
  setAttr(node,'data-source-time',row.Date);
  setAttr(node,'data-source-hash',digest([row]));
}
for(const a of history){
  const rowNo=Number(a.getAttribute('data-source-row'));
  if(rowNo){
    if(!Number.isInteger(rowNo)||rowNo>count||rowNo<1||a.getAttribute('data-source-hash')!==digest([rows[rowNo-1]]))throw Error('來源映射驗證失敗');
    const d=descriptor(a),r=rows[rowNo-1];
    if(d.name!==r.User||normalize(d.body)!==normalize(r.Message)||d.day!==r.Date.slice(0,10)||d.clock!==r.Date.slice(11,16)||(d.stamp&&d.stamp!==r.Date))throw Error('來源映射內容不符');
    if((mapping.has(rowNo)&&mapping.get(rowNo)!==a.id)||(mappedIds.has(a.id)&&mapping.get(rowNo)!==a.id))throw Error('來源映射衝突');
    mapping.set(rowNo,a.id);mappedIds.add(a.id);
  }
}
let lastMappedId=0;
for(const [rowNo,id] of [...mapping].sort((a,b)=>a[0]-b[0])){
  const num=Number(id.slice(1));
  if(!/^m\d+$/.test(id)||num<=lastMappedId)throw Error('來源映射順序錯誤');
  lastMappedId=num;
  remember(document.getElementById(id),rowNo);
}
for(const a of history){
  for(const n of a.querySelectorAll('.name,.original,.avatar:not(.uji)'))setAttr(n,'translate','no');
  const avatar=a.querySelector('.avatar');if(avatar)setAttr(avatar,'aria-hidden','true');
  const source=a.getAttribute('data-source-time');
  if(source)setAttr(a.querySelector('time'),'datetime',source.replace(' ','T')+'+08:00');
}
const latest=document.querySelector('#latest');
let id=Math.max(...Array.from(document.querySelectorAll('[id^="m"]'),n=>Number(n.id.slice(1))).filter(Number.isFinite));
let rowNo=count;
let day=lastTimestamp(rows.slice(0,count))?.slice(0,10)||'';
const avatar=document.querySelector('.avatar.uji')?.outerHTML;
for(const {Date:stamp,User:name,Message:message} of rows.slice(count)){
  const date=stamp.slice(0,10), time=stamp.slice(11,16), body=esc(message).replace(/https?:\/\/[^\s<>]+/g,url=>'<a href="'+url+'" target="_blank" rel="noopener noreferrer">'+url+'</a>').replaceAll('\n','<br>');
  if(date&&date!==day){latest.insertAdjacentHTML('beforebegin','<p class="notice">'+esc(date)+'</p>');day=date}
  const attrs='id="m'+(++id)+'" data-day="'+esc(date)+'" data-clock="'+esc(time)+'"';
  rowNo++;
  const notice=isNotice({Date:stamp,User:name,Message:message});
  const icon=name==='유디❤️' && avatar ? avatar : '<span class="avatar" style="background:'+avatarColor(name)+'" aria-hidden="true" translate="no">'+esc(Array.from(name)[0]||'')+'</span>';
  latest.insertAdjacentHTML('beforebegin',notice ? '<p class="notice" translate="no" '+attrs+'>'+body+(time?' · '+esc(time):'')+'</p>' : '<article '+attrs+'>'+icon+'<div><div class="name" translate="no">'+esc(name)+'</div><div class="line"><div class="bubble"><div class="original" translate="no">'+body+'</div></div><time datetime="'+esc(stamp.replace(' ','T')+'+08:00')+'">'+esc(time)+'</time></div></div></article>');
  const inserted=document.getElementById('m'+id);remember(inserted,rowNo);
  if(!notice)mapping.set(rowNo,inserted.id);
}
// Reviewed selectors: [timestamp,name] or [timestamp,name,body,rowNumber].
// Ambiguous or conflicting reviewed pairs abort before writing the snapshot.
let addedPairs=0;
if(process.env.REVIEWED_PAIRS){
  const pairs=JSON.parse(readFileSync(process.env.REVIEWED_PAIRS,'utf8'));
  if(!Array.isArray(pairs))throw Error('回覆審核檔格式錯誤');
  for(const pair of pairs){
    const [replyId,targetId]=resolvePair(rows,mapping,pair);
    const reply=document.getElementById(replyId),original=document.getElementById(targetId);
    const bubble=reply.querySelector('.bubble'),oldQuote=bubble.querySelector('.quote');
    const href='#'+targetId;
    if(oldQuote&&oldQuote.getAttribute('href')!==href)throw Error('既有引用衝突: '+replyId);
    if(!oldQuote){
      const a=document.createElement('a');a.className='quote';a.setAttribute('href',href);
      a.setAttribute('data-reply-kind','quote');a.setAttribute('translate','no');
      const strong=document.createElement('strong');strong.textContent='↳ 回覆 '+original.querySelector('.name').textContent;
      a.append(strong,document.createElement('br'));
      const lines=normalize(originalText(original.querySelector('.original'))).split('\n');
      for(let i=0;i<lines.length;i++){
        if(i)a.append(document.createElement('br'));
        a.append(lines[i]);
      }
      bubble.prepend(a);addedPairs++;
    }
    let list=original.querySelector('details.replies');
    if(!list){list=document.createElement('details');list.className='replies';list.innerHTML='<summary></summary><ul></ul>';original.querySelector('.line').parentElement.append(list)}
    const ul=list.querySelector('ul');
    if(!ul)throw Error('既有回覆清單格式不符: '+targetId);
    const links=Array.from(ul.querySelectorAll('a')).filter(a=>a.getAttribute('href')==='#'+replyId);
    if(links.length>1)throw Error('既有反向連結重複: '+replyId);
    if(!links.length){
      const back=document.createElement('a');back.setAttribute('href','#'+replyId);
      back.textContent=reply.querySelector('.name').textContent+' '+reply.dataset.clock;
      const li=document.createElement('li');li.append(back);ul.append(li);addedPairs++;
      list.querySelector('summary').textContent=list.querySelectorAll('li').length+' 則已收錄回覆';
    }
    if(reply.querySelector('.quote').getAttribute('href')!==href||!Array.from(ul.querySelectorAll('a')).some(a=>a.getAttribute('href')==='#'+replyId))throw Error('雙向回覆驗證失敗');
  }
}
if(!old&&count===rows.length&&!repairedAvatars&&!repairedReplies&&!metadataChanges&&!addedPairs&&main.dataset.exportDigest===digest(rows)&&main.dataset.snapshotThrough===throughISO){
  console.log('沒有新增訊息或結構修復');process.exit(0);
}
main.dataset.exportCount=String(rows.length);
main.dataset.exportAnchor=anchor(rows);
main.dataset.exportDigest=digest(rows);
main.dataset.snapshotThrough=throughISO;
document.querySelector('.top small').textContent='原文 · 截至 '+through.slice(0,16)+'（台灣時間）';
for(const article of document.querySelectorAll('article')){
  const node=article.querySelector('.avatar:not(.uji)');
  if(node && !colorPattern.test(node.getAttribute('style')||''))throw Error('頭像背景缺失: '+article.id);
  if(Array.from(article.children).some(n=>n.matches('details.replies')))throw Error('回覆清單容器錯誤: '+article.id);
}
const ids=Array.from(document.querySelectorAll('[id]'),n=>n.id);
if(new Set(ids).size!==ids.length || Array.from(main.querySelectorAll('a[href^="#"]')).some(a=>!ids.includes(a.getAttribute('href').slice(1))))throw Error('訊息編號或引用驗證失敗');
const iv=randomBytes(12),cipher=createCipheriv('aes-256-gcm',key,iv);
const encrypted=Buffer.concat([cipher.update(document.toString(),'utf8'),cipher.final(),cipher.getAuthTag()]);
const result=shell.replace(pattern,"const snapshot = { nonce: '"+iv.toString('base64')+"', ciphertext: '"+encrypted.toString('base64')+"' };").replace('<title>KakaoTalk 韓中對照</title>','<title>KakaoTalk 原文</title>');
mkdirSync(new URL('.',out),{recursive:true});
const temp=fileURLToPath(out)+'.'+randomBytes(12).toString('hex')+'.tmp';
writeFileSync(temp,result,{flag:'wx'});
try{
  // Exclusive creation protects against a destination appearing after the initial check.
  if(previous)linkSync(temp,out);else renameSync(temp,out);
}finally{if(existsSync(temp))unlinkSync(temp)}
console.log('新增',rows.length-count,'筆；最後編號',id,'；引用',main.querySelectorAll('a.quote').length,'；修復頭像',repairedAvatars,'；修復回覆',repairedReplies);
