(function(){
'use strict';
try {
  var d=document, id='router-quickfill-ui', previous=d.getElementById(id);
  if(previous){ previous.remove(); return; }
  var host=location.hostname, origin=location.origin;
  var root=d.createElement('section');root.id=id;
  root.style.cssText='position:fixed!important;inset:0!important;z-index:2147483647!important;overflow:auto!important;background:rgb(9,18,32)!important;color:white!important;padding:16px!important;box-sizing:border-box!important;font:14px/1.5 -apple-system,system-ui,sans-serif!important';
  root.innerHTML='<div style="max-width:520px;margin:auto"><h2 style="margin:0 0 8px">Router QuickFill <small>v1.0</small></h2><p id="rqorigin"></p><p style="font-size:12px;color:#a8bbd4">僅於目前網頁填入，不自動提交。密碼不儲存，也不傳到其他伺服器。</p><label>共用帳號 <input id="rquser" autocomplete="off" placeholder="admin"></label><label>候選密碼（每行一組，可用 帳號[TAB]密碼）<textarea id="rqraw" rows="5" autocomplete="off" placeholder="一行一組密碼"></textarea></label><p><button id="rqload">載入到暫存清單</button> <button id="rqclear">清空</button></p><p id="rqstate">尚未載入</p><p><button id="rqprev">上一組</button> <button id="rqfill">填入目前組</button> <button id="rqnext">下一組</button></p><p><button id="rqhide">縮小以操作登入頁</button> <button id="rqattempt">記錄一次登入嘗試</button></p><p><button id="rqcopy">複製測試紀錄</button> <button id="rqclose">關閉並清空</button></p><p id="rqnote" style="font-size:12px;color:#ffda9c">請勿將其他網站的密碼輸入不可信設備頁面。若出現鎖定或 CAPTCHA，立即停止測試。</p></div>';
  var css=d.createElement('style');css.textContent='#router-quickfill-ui input,#router-quickfill-ui textarea{display:block;width:100%;padding:9px;margin:5px 0 12px;box-sizing:border-box;border-radius:7px;border:1px solid #71829a;background:#152238;color:white;font:inherit}#router-quickfill-ui button{margin:3px;padding:9px;border:1px solid #75e1c6;border-radius:8px;color:#051916;background:#75e1c6;font:inherit;cursor:pointer}#router-quickfill-ui label{display:block}#router-quickfill-ui p{margin:10px 0}';
  root.appendChild(css); (d.body||d.documentElement).appendChild(root);
  var $=function(x){return root.querySelector('#'+x)}, list=[], index=0, attempts=0, filled=0, log=[];
  $('rqorigin').textContent='目前網站：'+origin;
  function report(t){$('rqstate').textContent=t;}
  function forget(){list=[];index=0;attempts=0;filled=0;log=[];$('rqraw').value='';$('rquser').value='';report('已清空。');}
  function summary(t){report('候選 '+(list.length?index+1+'/'+list.length:'0')+' · 填入 '+filled+' · 手動嘗試 '+attempts+'｜'+t);}
  function fields(){
    var out=[],seen=new Set();
    function scan(doc,depth){if(depth>3||!doc||seen.has(doc))return;seen.add(doc);
      var nodes=doc.querySelectorAll('input,iframe,*');
      for(var n of nodes){if(root.contains(n))continue;
        if(n.tagName==='INPUT'&&!n.disabled&&n.type!=='hidden'&&n.getClientRects().length)out.push(n);
        if(n.shadowRoot)scan(n.shadowRoot,depth+1);
        if(n.tagName==='IFRAME'){try{scan(n.contentDocument,depth+1);}catch(e){}}
      }
    }scan(d,0);return out;
  }
  function fill(f,v){var w=f.ownerDocument.defaultView,desc=Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype,'value');if(desc&&desc.set)desc.set.call(f,v);else f.value=v;f.dispatchEvent(new w.Event('input',{bubbles:true}));f.dispatchEvent(new w.Event('change',{bubbles:true}));}
  function find(){var a=fields(), pass=a.filter(function(x){return x.type==='password'}),names=a.filter(function(x){return ['text','email','tel'].includes(x.type)});
    if(!pass.length)return null;
    var p=pass[0];names.sort(function(x,y){function rank(t){var s=[t.name,t.id,t.autocomplete,t.placeholder,t.getAttribute('aria-label')].join(' ');return (/user|account|login|email|帳號|用戶/i.test(s)?10:0)+(t.form===p.form?3:0)}return rank(y)-rank(x)});
    return {username:names[0],password:p};
  }
  $('rqload').onclick=function(){var common=$('rquser').value,raw=$('rqraw').value.split(/\r?\n/).filter(function(s){return s.length>0;});
    if(!raw.length){report('請先輸入候選密碼。');return;}
    if(raw.length>30){report('最多 30 組已知帳密，不支援大量字典嘗試。');return;}
    var candidate=raw.map(function(s){var k=s.indexOf('\t');return k<0?{user:common,pass:s}:{user:s.slice(0,k),pass:s.slice(k+1)}});
    if(candidate.some(function(x){return !x.user||!x.pass})){report('每組都必須有帳號與密碼。');return;}
    list=candidate;index=0;attempts=0;filled=0;log=[];$('rqraw').value='';summary('清單已載入，密碼輸入框已清除。');
  };
  $('rqfill').onclick=function(){if(!list.length){report('請先載入帳密清單。');return;}var f=find();if(!f){report('找不到可見的密碼欄位；可能在跨來源 iframe 或特殊元件內。');return;}
    try{if(f.username)fill(f.username,list[index].user);fill(f.password,list[index].pass);filled++;summary('填入成功；請自己確認並按原網站登入鍵。');}catch(e){report('填入失敗：'+String(e));}
  };
  $('rqprev').onclick=function(){if(list.length){index=Math.max(0,index-1);summary('已切換。')}};
  $('rqnext').onclick=function(){if(list.length){index=Math.min(list.length-1,index+1);summary('已切換。')}};
  $('rqattempt').onclick=function(){attempts++;log.push({time:new Date().toISOString(),candidate:index+1,event:'manual_attempt'});summary(attempts>=3?'已記錄至少 3 次。建議停止並觀察鎖定／冷卻機制。':'已記錄，請自行觀察登入回應。');};
  $('rqhide').onclick=function(){root.style.display='none';var bubble=d.createElement('button');bubble.id='rqbubble';bubble.textContent='帳密助手';bubble.style.cssText='position:fixed!important;bottom:18px!important;right:15px!important;z-index:2147483647!important;background:#75e1c6!important;color:#051916!important;border:0!important;border-radius:24px!important;padding:13px!important;font:14px system-ui!important';(d.body||d.documentElement).appendChild(bubble);bubble.onclick=function(){bubble.remove();root.style.display='block';};};
  $('rqcopy').onclick=function(){var text=JSON.stringify({site:origin,totalCandidates:list.length,filled:filled,attempts:attempts,log:log},null,2);var t=d.createElement('textarea');t.value=text;d.body.appendChild(t);t.select();try{d.execCommand('copy');summary('已複製不含密碼的測試紀錄。')}catch(e){summary('無法自動複製測試紀錄。')}t.remove();};
  $('rqclear').onclick=forget;
  $('rqclose').onclick=function(){forget();var bubble=d.getElementById('rqbubble');if(bubble)bubble.remove();root.remove();};
} catch(e){alert('Router QuickFill 啟動失敗：'+e)}
})();
