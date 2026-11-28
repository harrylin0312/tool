// Integration fixture: only synthetic data and an ephemeral test key.
// Run with Node 22+, python3 and the project's real linkedom installed.
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,copyFileSync,writeFileSync,readFileSync,rmSync} from 'node:fs';
import {createCipheriv,createDecipheriv,randomBytes,createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {parseHTML} from 'linkedom';
const root=mkdtempSync(fileURLToPath(new URL('./.publish-test-',import.meta.url)));
const rows=[
 ['2026-11-27 23:57:00','Alex','old'],
 ['2026-11-27 23:58:00','Alex','old second'],
 ['2026-11-28 00:00:01','Alex','안녕, & <hello>\nhttps://example.org/test'],
 ['2026-11-28 00:00:02','New','reply'],
 ['','','The message has been deleted.'],
 ['2026-11-28 00:00:04','New','second message'],
 ['2026-11-28 00:01:00','New','next batch']
];
const key=randomBytes(32),iv=randomBytes(12);
const file=join(root,'original','index.html');
const csv=(name,rs)=>writeFileSync(join(root,name),'\uFEFF'+[['Date','User','Message'],...rs].map(r=>r.map(v=>'"'+v.replaceAll('"','""')+'"').join(',')).join('\r\n')+'\r\n');
const msg=(id,clock,style,body)=>'<article id="m'+id+'" data-day="2026-11-27" data-clock="'+clock+'"><span class="avatar"'+style+'>A</span><div><div class="name">Alex</div><div class="line"><div class="bubble"><div class="original">'+body+'</div><div class="translation">譯文</div></div><time>'+clock+'</time></div></div></article>';
const plain='<!DOCTYPE html><html><head><style>article{display:grid;grid-template-columns:32px minmax(0,1fr)}</style></head><body><main><header class="top"><div><small>old</small></div></header><div class="stream"><p class="notice" id="m1">extra</p>'+msg(2,'23:57',' style="background:#a9c8fa"','old')+msg(4,'23:58','','old second')+'<div id="latest"></div></div></main></body></html>';
const cipher=createCipheriv('aes-256-gcm',key,iv);
const payload=Buffer.concat([cipher.update(plain,'utf8'),cipher.final(),cipher.getAuthTag()]);
const digest=rs=>createHash('sha256').update(JSON.stringify(rs)).digest('hex');
function run(args,pairs,expected=true,trusted){
  const env={...process.env};delete env.REVIEWED_PAIRS;delete env.TRUSTED_HISTORY_SHA256;
  if(trusted!==undefined)env.TRUSTED_HISTORY_SHA256=trusted;
  if(pairs){env.REVIEWED_PAIRS=join(root,'pairs.json');writeFileSync(env.REVIEWED_PAIRS,JSON.stringify(pairs));}
  const r=spawnSync(process.execPath,[join(root,'live','publish-original.mjs'),...args],{cwd:root,input:key.toString('base64url'),encoding:'utf8',env});
  assert.equal(r.status===0,expected,r.stderr||r.stdout);
}
function read(){
  const [,nonce,ct]=readFileSync(file,'utf8').match(/nonce: '([^']+)', ciphertext: '([^']+)'/);
  const b=Buffer.from(ct,'base64'),dec=createDecipheriv('aes-256-gcm',key,Buffer.from(nonce,'base64'));
  dec.setAuthTag(b.subarray(-16));
  const {document}=parseHTML(Buffer.concat([dec.update(b.subarray(0,-16)),dec.final()]).toString());
  return {document,nonce};
}
const sel=i=>rows[i-1].slice(0,2);
const attr=(doc,selector,name)=>doc.querySelector(selector)?.getAttribute(name);
try{
  mkdirSync(join(root,'live'));
  for(const f of ['publish-original.mjs','reply-mapping.mjs'])copyFileSync(new URL('./'+f,import.meta.url),join(root,'live',f));
  csv('prev.csv',rows.slice(0,2));csv('cur.csv',rows.slice(0,6));csv('next.csv',rows);
  writeFileSync(join(root,'index.html'),"<!DOCTYPE html><title>KakaoTalk 韓中對照</title><script>const snapshot = { nonce: '"+iv.toString('base64')+"', ciphertext: '"+payload.toString('base64')+"' };</script>");
  const pairs=[[sel(4),sel(1)],[sel(6),sel(3)]];
  run(['cur.csv','prev.csv'],pairs,false);
  run(['cur.csv','prev.csv'],pairs,true,digest(rows.slice(0,2)));
  const a=read(),d=a.document;
  assert.equal(d.querySelectorAll('.translation').length,0);
  assert.equal(attr(d,'main','data-export-count'),'6');
  assert.equal(attr(d,'#m6 .quote','href'),'#m2');
  assert.equal(attr(d,'#m2 > div > details.replies a','href'),'#m6');
  assert.equal(attr(d,'#m8 .quote','href'),'#m5');
  assert.equal(attr(d,'#m5 > div > details.replies a','href'),'#m8');
  assert.equal(attr(d,'#m4','data-source-row'),'2');
  assert.equal(d.querySelector('#m7').textContent,'The message has been deleted.');
  assert.equal(attr(d,'#m5 time','datetime'),'2026-11-28T00:00:01+08:00');
  assert.equal(attr(d,'#m5 .original','translate'),'no');
  assert.equal(attr(d,'#m4 .avatar','style'),'background:#a9c8fa');
  assert.equal(d.querySelectorAll('article > details').length,0);
  const text=n=>Array.from(n.childNodes).map(c=>c.nodeType===3?c.textContent:c.tagName==='BR'?'\n':text(c)).join('');
  assert.equal(text(d.querySelector('#m5 .original')),rows[2][2]);
  assert.equal(text(d.querySelector('#m8 .quote')), '↳ 回覆 Alex\n'+rows[2][2]);
  assert.equal(d.querySelectorAll('#m8 .quote br').length,2);
  const before=readFileSync(file);
  run(['cur.csv'],pairs);assert.deepEqual(readFileSync(file),before);
  run(['next.csv'],[[sel(7),sel(2)]]);
  const b=read();assert.notEqual(a.nonce,b.nonce);
  assert.equal(attr(b.document,'#m9 .quote','href'),'#m4');
  assert.equal(attr(b.document,'#m4 > div > details.replies a','href'),'#m9');
  assert.equal(attr(b.document,'#m6 .quote','href'),'#m2');
  assert.equal(attr(b.document,'main','data-snapshot-through'),'2026-11-28T00:01:00+08:00');
  const stable=readFileSync(file);
  // QA-01: even a trusted earlier CSV cannot reinitialize an existing original.
  run(['cur.csv','prev.csv'],null,false,digest(rows.slice(0,2)));
  assert.deepEqual(readFileSync(file),stable);
  run(['next.csv'],[[sel(7),sel(1)]],false);assert.deepEqual(readFileSync(file),stable);
  const changed=rows.map(r=>[...r]);changed[0][2]='modified';csv('tampered.csv',changed);
  run(['tampered.csv'],null,false);assert.deepEqual(readFileSync(file),stable);
  // QA-02: reconstruct a legacy snapshot (no history digest), preserving its old anchor.
  b.document.querySelector('main').removeAttribute('data-export-digest');
  const legacyIV=randomBytes(12),legacyCipher=createCipheriv('aes-256-gcm',key,legacyIV);
  const legacyBytes=Buffer.concat([legacyCipher.update(b.document.toString(),'utf8'),legacyCipher.final(),legacyCipher.getAuthTag()]);
  const legacy=stable.toString().replace(/nonce: '[^']+', ciphertext: '[^']+'/,
    "nonce: '"+legacyIV.toString('base64')+"', ciphertext: '"+legacyBytes.toString('base64')+"'");
  writeFileSync(file,legacy);
  const legacyBefore=readFileSync(file),trusted=digest(rows);
  run(['tampered.csv'],null,false);assert.deepEqual(readFileSync(file),legacyBefore);
  run(['tampered.csv'],null,false,trusted);assert.deepEqual(readFileSync(file),legacyBefore);
  run(['next.csv'],null,false);assert.deepEqual(readFileSync(file),legacyBefore);
  run(['next.csv'],null,true,trusted);
  assert.equal(attr(read().document,'main','data-export-digest'),trusted);
  const migrated=readFileSync(file);run(['next.csv'],null);assert.deepEqual(readFileSync(file),migrated);
  console.log('PASS: first import, shifted IDs, cross-batch reply, replay, conflict, history tamper, QA-01/02/03');
}finally{rmSync(root,{recursive:true,force:true})}
