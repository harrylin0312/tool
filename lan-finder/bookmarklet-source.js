(function(){
"use strict";
var old=document.getElementById("lan-finder-local-overlay");
if(old){old.remove();return;}
var host=location.hostname;
var m=host.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
if(location.protocol!=="http:"||!m){alert("請先在 Safari 開啟 HTTP 內網 IP 網頁，例如 http://192.168.5.80/booksB1/，再執行此書籤。");return;}
var parts=m.slice(1).map(Number);
if(parts.some(function(n){return n>255;})||!(parts[0]===10||(parts[0]===172&&parts[1]>=16&&parts[1]<=31)||(parts[0]===192&&parts[1]===168))){alert("此工具僅供私人 IPv4 內網使用。");return;}
var prefix=parts.slice(0,3).join(".");
var root=document.createElement("div");
root.id="lan-finder-local-overlay";
root.setAttribute("style","position:fixed!important;inset:0!important;z-index:2147483647!important;background:#091221!important;color:#f2f7ff!important;overflow:auto!important;padding:16px!important;font:14px/1.5 -apple-system,system-ui,sans-serif!important;box-sizing:border-box!important;");
root.innerHTML='<section style="max-width:690px;margin:auto;"><div style="display:flex;gap:10px;align-items:center;justify-content:space-between"><strong style="font-size:20px">LAN Finder · 內網模式 <small style="font-size:12px;color:#78f0cd">v2.2.0</small></strong><button id="lclose">關閉</button></div><p style="color:#a9bed6">目前執行於 '+host+' 的 HTTP 頁面。不向外部伺服器上傳掃描結果；僅掃描已獲授權的內網。</p><div style="border:1px solid #3b4f6a;border-radius:12px;padding:12px"><div><b>第一步：校正已知服務</b></div><div style="overflow-wrap:anywhere;font-size:12px">'+location.href.replace(/&/g,"&amp;").replace(/</g,"&lt;")+'</div><button id="lcheck">測試目前網址</button><div id="lcal" style="margin:6px 0;color:#aad9c8">尚未測試</div></div><div style="border:1px solid #3b4f6a;border-radius:12px;padding:12px;margin-top:12px"><b>第二步：掃描同網段</b><p style="font-size:12px;color:#afc0d3">請只掃描你擁有或獲得授權的裝置。Port 80 先測試；可再輸入其他服務埠。</p><label>網段 <input id="lpref" inputmode="decimal" style="width:160px" value="'+prefix+'"></label><div style="margin-top:8px"><label>從 <input id="lfrom" type="number" min="1" max="254" value="1" style="width:65px"></label> <label>到 <input id="lto" type="number" min="1" max="254" value="254" style="width:65px"></label></div><div style="margin-top:8px"><label>Ports <input id="lports" value="80" style="width:180px" inputmode="text"></label></div><div style="display:flex;gap:8px;margin-top:12px"><button id="lscan">開始掃描</button><button id="lstop" disabled>停止</button><button id="lcopy">複製結果</button></div><p id="lstatus" style="color:#a9bed6">尚未掃描。掃描失敗不代表 Port 關閉。</p><div id="lresults" style="font-size:13px;overflow-wrap:anywhere"></div></div><p style="font-size:12px;color:#9db0c9">注意：Safari、網站 CSP、HTTPS 憑證與伺服器設定仍可能造成漏報。此工具不是 TCP Port Scanner。結束後點右上方「關閉」，不會修改伺服器檔案。</p></section>';
(document.body||document.documentElement).appendChild(root);
root.querySelectorAll("button").forEach(function(b){b.setAttribute("style","border:1px solid #7894a8;color:#07221c;background:#78f0cd;border-radius:8px;padding:7px 10px;margin:4px 2px;font-weight:600")});
root.querySelectorAll("input").forEach(function(i){i.setAttribute("style",i.getAttribute("style")+";padding:7px;border:1px solid #7894a8;color:#fff;background:#14243b;border-radius:7px")});
var el=function(id){return root.querySelector("#"+id);};
var controllers=new Set();
var stopped=false,running=false,found=[];
function ping(url,timeout){
 var c=new AbortController();controllers.add(c);
 var timed=false;var timer=setTimeout(function(){timed=true;c.abort();},timeout);
 return fetch(url,{method:"GET",mode:"no-cors",credentials:"omit",cache:"no-store",redirect:"follow",signal:c.signal}).then(function(){return "ok";},function(){return timed?"timeout":"fail";}).finally(function(){clearTimeout(timer);controllers.delete(c);});
}
el("lclose").onclick=function(){stopped=true;controllers.forEach(function(c){c.abort();});root.remove();};
el("lcheck").onclick=async function(){
 el("lcal").textContent="測試中…";
 var result=await ping(location.href,4500);
 el("lcal").textContent=result==="ok"?"校正成功：此 HTTP 頁面可由 JavaScript 探測。":"校正失敗："+result+"。可能受網站 CSP、驗證或瀏覽器限制；無法據此判斷 Port 狀態。";
};
el("lcopy").onclick=async function(){
 var s=found.join("\n");if(!s){el("lstatus").textContent="目前沒有可複製的結果。";return;}
 try{await navigator.clipboard.writeText(s);el("lstatus").textContent="已複製 "+found.length+" 個網址。";}
 catch(e){prompt("長按複製掃描結果",s);}
};
el("lstop").onclick=function(){stopped=true;controllers.forEach(function(c){c.abort();});el("lstatus").textContent="正在停止…";};
el("lscan").onclick=async function(){
 if(running)return;
 var p=el("lpref").value.trim().split(".");
 var from=Number(el("lfrom").value),to=Number(el("lto").value);
 var ports=el("lports").value.split(",").map(function(s){return Number(s.trim());});
 if(p.length!==3||p.some(function(s){return !/^\d{1,3}$/.test(s)||Number(s)>255;})||p.join(".")!==prefix){el("lstatus").textContent="為安全起見，僅允許掃描目前頁面所在的 "+prefix+".0/24 網段。";return;}
 if(!Number.isInteger(from)||!Number.isInteger(to)||from<1||to>254||from>to||!ports.length||ports.length>8||ports.some(function(n){return !Number.isInteger(n)||n<1||n>65535;})){el("lstatus").textContent="IP 尾碼必須是 1–254；Port 必須是 1–65535，最多 8 個。";return;}
 running=true;stopped=false;found=[];el("lresults").textContent="";
 el("lscan").disabled=true;el("lstop").disabled=false;
 var jobs=[];
 ports=Array.from(new Set(ports));
 ports.forEach(function(port){for(var i=from;i<=to;i++){var secure=[443,5001,8443,9443].indexOf(port)!==-1;var protocol=secure?"https":"http";jobs.push(protocol+"://"+prefix+"."+i+((port===80&&!secure)||(port===443&&secure)?"":":"+port)+"/");}});
 var index=0,done=0,fail=0,timeouts=0;
 function draw(){el("lstatus").textContent="已測試 "+done+"/"+jobs.length+" · 成功 "+found.length+" · 失敗 "+fail+" · 逾時 "+timeouts+"。失敗不等於 Port 關閉。";}
 draw();
 var workers=Array.from({length:Math.min(8,jobs.length)},async function(){
  while(!stopped&&index<jobs.length){
   var url=jobs[index++];var result=await ping(url,1700);
   if(stopped)break;
   done++;
   if(result==="ok"){
    found.push(url);
    var a=document.createElement("a");a.href=url;a.target="_blank";a.rel="noopener noreferrer";a.textContent=url;
    a.style.cssText="display:block;color:#78f0cd;padding:4px 0;";
    el("lresults").appendChild(a);
   }else if(result==="timeout")timeouts++;else fail++;
   if(done%3===0||result==="ok"||done===jobs.length)draw();
  }
 });
 await Promise.all(workers);
 running=false;el("lscan").disabled=false;el("lstop").disabled=true;
 el("lstatus").textContent=(stopped?"已停止。":"掃描結束。")+"已測試 "+done+"/"+jobs.length+"；探測成功 "+found.length+"；失敗 "+fail+"；逾時 "+timeouts+"。"+(found.length?"":"結果為 0 不等於服務不存在。");
};
})();
