// Compute only from an independently verified historical CSV, never from an untrusted candidate.
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
const [path,count]=process.argv.slice(2);
if(!path)throw Error('usage: node history-digest.mjs trusted.csv [prefix-count]');
const py="import csv,json,sys;print(json.dumps(list(csv.DictReader(open(sys.argv[1],encoding='utf-8-sig',newline='')))))";
const rows=JSON.parse(execFileSync('python3',['-c',py,path],{maxBuffer:128*1024*1024}));
const n=count===undefined?rows.length:Number(count);
if(!Number.isSafeInteger(n)||n<1||n>rows.length||rows.slice(0,n).some(r=>['Date','User','Message'].some(k=>typeof r[k]!=='string')))throw Error('invalid trusted CSV or prefix count');
console.log(createHash('sha256').update(JSON.stringify(rows.slice(0,n).map(r=>[r.Date,r.User,r.Message]))).digest('hex'));
