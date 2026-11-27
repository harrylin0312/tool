import {readFileSync, writeFileSync, renameSync, mkdirSync} from 'node:fs';
import {createCipheriv, createDecipheriv, randomBytes, createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {parseHTML} from 'linkedom';

// Run from this folder after installing linkedom. Pass the private link on stdin.
// First run: node publish-original.mjs current.csv previous.csv
// Later runs: node publish-original.mjs current.csv
const [current, previous] = process.argv.slice(2);
const key = Buffer.from(readFileSync(0,'utf8').trim().split('#').pop(),'base64url');
const base = new URL('../index.html',import.meta.url);
const out = new URL('../original/index.html',import.meta.url);
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
if (old && (old.some((r,i)=>r.Date!==rows[i].Date) || old.at(-1).Message!==rows[count-1].Message)) throw Error('歷史紀錄未對齊');
if (!old && count===rows.length){console.log('沒有新增訊息');process.exit(0)}
const esc=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
if(old){
  for(const n of document.querySelectorAll('.translation,.quote-translation,.quote-language'))n.remove();
  for(const n of document.querySelectorAll('p.notice[id]')){
    const br=n.querySelector('br');
    if(br && Number(n.id.slice(1))>=446){while(br.nextSibling)br.nextSibling.remove();br.remove();n.append(' · '+n.dataset.clock)}
  }
}
const latest=document.querySelector('#latest');
let id=Math.max(...Array.from(document.querySelectorAll('[id^="m"]'),n=>Number(n.id.slice(1))).filter(Number.isFinite));
const firstNewId=id+1;
let day=rows[count-1].Date.slice(0,10);
const avatar=document.querySelector('.avatar.uji')?.outerHTML;
for(const {Date:stamp,User:name,Message:message} of rows.slice(count)){
  const date=stamp.slice(0,10), time=stamp.slice(11,16), body=esc(message).replace(/https?:\/\/[^\s<>]+/g,url=>'<a href="'+url+'" target="_blank" rel="noopener noreferrer">'+url+'</a>').replaceAll('\n','<br>');
  if(date!==day){latest.insertAdjacentHTML('beforebegin','<p class="notice">'+esc(date)+'</p>');day=date}
  const attrs='id="m'+(++id)+'" data-day="'+esc(date)+'" data-clock="'+esc(time)+'"';
  const notice=[name+' joined this chatroom.',name+' left this chatroom.','The message has been deleted.'].includes(message);
  const icon=name==='유디❤️' && avatar ? avatar : '<span class="avatar">'+esc(Array.from(name)[0]||'')+'</span>';
  latest.insertAdjacentHTML('beforebegin',notice ? '<p class="notice" '+attrs+'>'+body+' · '+esc(time)+'</p>' : '<article '+attrs+'>'+icon+'<div><div class="name">'+esc(name)+'</div><div class="line"><div class="bubble"><div class="original">'+body+'</div></div><time>'+esc(time)+'</time></div></div></article>');
}
// Optional reviewed pairs use exact export timestamps. Ambiguous timestamps are rejected.
if(process.env.REVIEWED_PAIRS){
  const find=([stamp,name])=>{
    const hits=rows.slice(count).flatMap((row,i)=>row.Date===stamp && row.User===name?[firstNewId+i]:[]);
    if(hits.length!==1)throw Error('審核時間未唯一對應');
    return document.getElementById('m'+hits[0]);
  };
  for(const [replyTime,originalTime] of JSON.parse(readFileSync(process.env.REVIEWED_PAIRS,'utf8'))){
    const reply=find(replyTime),original=find(originalTime);
    if(replyTime[0]<=originalTime[0])throw Error('引用順序錯誤');
    const a=document.createElement('a');a.className='quote';a.setAttribute('href','#'+original.id);
    const strong=document.createElement('strong');strong.textContent='↳ 回覆 '+original.querySelector('.name').textContent;
    a.append(strong,document.createElement('br'),original.querySelector('.original').textContent);
    reply.querySelector('.bubble').prepend(a);
    let list=original.querySelector('details.replies');
    if(!list){list=document.createElement('details');list.className='replies';list.innerHTML='<summary></summary><ul></ul>';original.append(list)}
    const back=document.createElement('a');back.setAttribute('href','#'+reply.id);
    back.textContent=reply.querySelector('.name').textContent+' '+reply.dataset.clock;
    const li=document.createElement('li');li.append(back);list.querySelector('ul').append(li);
    list.querySelector('summary').textContent=list.querySelectorAll('li').length+' 則已收錄回覆';
  }
}
main.dataset.exportCount=String(rows.length);
main.dataset.exportAnchor=anchor(rows);
document.querySelector('.top small').textContent='原文 · 截至 '+rows.at(-1).Date.slice(0,16)+'（台灣時間）';
const ids=Array.from(document.querySelectorAll('[id]'),n=>n.id);
if(new Set(ids).size!==ids.length || Array.from(main.querySelectorAll('a[href^="#"]')).some(a=>!ids.includes(a.getAttribute('href').slice(1))))throw Error('訊息編號或引用驗證失敗');
const iv=randomBytes(12),cipher=createCipheriv('aes-256-gcm',key,iv);
const encrypted=Buffer.concat([cipher.update(document.toString(),'utf8'),cipher.final(),cipher.getAuthTag()]);
const result=shell.replace(pattern,"const snapshot = { nonce: '"+iv.toString('base64')+"', ciphertext: '"+encrypted.toString('base64')+"' };").replace('<title>KakaoTalk 韓中對照</title>','<title>KakaoTalk 原文</title>');
mkdirSync(new URL('.',out),{recursive:true});const temp=fileURLToPath(out)+'.tmp';writeFileSync(temp,result);renameSync(temp,out);
console.log('新增',rows.length-count,'筆；最後編號',id,'；引用',main.querySelectorAll('a.quote').length);
