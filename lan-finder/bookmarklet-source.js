(function(){
try{
alert("LAN Finder v2.3.0 started");
var a=location.hostname.split("."),d=document;
if(location.protocol!=="http:"||a.length!==4||a.some(function(v){return !/^\\d+$/.test(v)||+v>255;})){alert("Open a local http://IP page first.");return;}
var id="lf-local-panel";
if(d.getElementById(id)){alert("LAN Finder is already running.");return;}
var p=a.slice(0,3).join(".")+".",el=d.createElement("div");
el.id=id;
el.style.cssText="position:fixed!important;inset:0!important;z-index:2147483647!important;background:rgb(9,18,33)!important;color:white!important;padding:18px!important;overflow:auto!important;font:14px system-ui!important";
el.innerHTML='<h2>LAN Finder v2.3.0</h2><p>Network: '+p+'0/24</p><button id="lfclose">Close</button> <button id="lfknown">Check known URL</button> <button id="lfscan">Scan port 80</button> <button id="lfstop">Stop</button><p id="lfstatus">Ready. Scanning only authorized devices.</p><div id="lfresults"></div>';
d.body.appendChild(el);
var q=function(id){return el.querySelector("#"+id);},stop=false,active=false,ctls=[];
function report(s){q("lfstatus").textContent=s;}
async function probe(url){
var c=new AbortController(),t=setTimeout(function(){c.abort();},1700);ctls.push(c);
try{await fetch(url,{mode:"no-cors",credentials:"omit",cache:"no-store",signal:c.signal});return true;}
catch(e){return false;}
finally{clearTimeout(t);ctls.splice(ctls.indexOf(c),1);}
}
q("lfclose").onclick=function(){stop=true;ctls.forEach(function(c){c.abort();});el.remove();};
q("lfstop").onclick=function(){stop=true;ctls.forEach(function(c){c.abort();});report("Stopping...");};
q("lfknown").onclick=async function(){report("Checking known URL...");report(await probe(location.href)?"Known page: reachable":"Known page: blocked or failed. No TCP conclusion.");};
q("lfscan").onclick=async function(){
if(active)return;active=true;stop=false;var i=1,done=0,found=0;
q("lfresults").textContent="";
report("Scanning "+p+"1-254 on port 80...");
await Promise.all(Array.from({length:8},async function(){
while(!stop&&i<=254){
var n=i++,url="http://"+p+n+"/",ok=await probe(url);if(stop)break;done++;
if(ok){found++;var link=d.createElement("a");link.href=url;link.textContent=url;link.target="_blank";link.style.cssText="display:block;color:aqua;padding:3px";q("lfresults").appendChild(link);}
if(done%8===0||ok)report("Tested "+done+"/254, web replies "+found+". Failures are unknown, not closed ports.");
}
}));
active=false;report("Finished: "+done+"/254, web replies "+found+". Other ports not tested.");
};
}catch(e){alert("LAN Finder start error: "+String(e));}
})();
