(function(){
try{
var d=document,old=d.getElementById("lf-identify");if(old){old.remove();return;}
var host=location.hostname,a=host.split(".").map(Number);
if(a.length!==4||a.some(function(n){return !Number.isInteger(n)||n<0||n>255;})||!(a[0]===10||(a[0]===172&&a[1]>=16&&a[1]<=31)||(a[0]===192&&a[1]===168))){alert("LAN Identifier: please open a private-IP device page first.");return;}
var title=(d.title||"").trim().slice(0,140),meta=function(name){var e=d.querySelector('meta[name="'+name+'"]');return e?(e.content||"").slice(0,140):"";};
var fields=[["標題",title,3],["程式資訊",meta("generator"),3],["應用程式",meta("application-name"),3],["主標題",Array.from(d.querySelectorAll("h1,h2")).slice(0,5).map(function(e){return e.textContent.trim().slice(0,80);}).join(" "),2],["Logo",Array.from(d.querySelectorAll("img[alt]")).slice(0,8).map(function(e){return e.alt.slice(0,50);}).join(" "),1]];
var brands=[
["TP-Link","網路設備",/tp[- ]?link|omada|mercusys/i],
["ASUS","網路設備",/\basus\b|asuswrt/i],
["D-Link","網路設備",/d[- ]?link/i],
["NETGEAR","網路設備",/netgear/i],
["MikroTik","網路設備",/mikrotik|routeros/i],
["Ubiquiti","網路設備",/ubiquiti|unifi/i],
["OpenWrt","路由器系統",/openwrt|luci/i],
["pfSense","防火牆",/pfsense/i],
["OPNsense","防火牆",/opnsense/i],
["Synology","NAS／儲存",/synology|diskstation/i],
["QNAP","NAS／儲存",/\bqnap\b|qts/i],
["TrueNAS","NAS／儲存",/truenas/i],
["Proxmox","虛擬化",/proxmox/i],
["Home Assistant","智慧家庭",/home assistant/i],
["Hikvision","監控設備",/hikvision/i],
["Dahua","監控設備",/dahua/i],
["Brother","可能為印表機",/\bbrother\b/i],
["Epson","可能為印表機",/\bepson\b/i],
["HP","可能為印表機",/hp laserjet|hewlett[- ]?packard/i]
];
var match=null;
for(var f of fields){if(!f[1])continue;for(var b of brands){if(b[2].test(f[1])){match={brand:b[0],type:b[1],source:f[0],level:f[2]>=3?"較高":f[2]===2?"中":"低"};break;}}if(match)break;}
var login=/login|sign in|登入|管理|administrator|password/i.test(fields.map(function(f){return f[1];}).join(" "));
var brand=match?match.brand:"未辨識",type=match?match.type:(login?"管理／登入網頁":"未知 HTTP 網頁"),level=match?match.level:"未知";
var panel=d.createElement("section");panel.id="lf-identify";panel.style.cssText="position:fixed!important;inset:0!important;z-index:2147483647!important;overflow:auto!important;box-sizing:border-box!important;background:rgb(9,18,33)!important;color:white!important;padding:20px!important;font:15px/1.6 system-ui!important";
panel.innerHTML='<h2 style="margin:0">LAN Identifier v0.1</h2><p id="lfip"></p><p id="lfbrand"></p><p id="lftype"></p><p id="lftrust"></p><p id="lftitle" style="overflow-wrap:anywhere"></p><label>人工修正分類：<select id="lfcat"><option>未知 HTTP 網頁</option><option>管理／登入網頁</option><option>網路設備</option><option>路由器系統</option><option>NAS／儲存</option><option>防火牆</option><option>監控設備</option><option>可能為印表機</option><option>智慧家庭</option><option>虛擬化</option><option>一般網站</option></select></label><p><button id="lfcopy">複製設備紀錄</button> <button id="lfexit">關閉</button></p><textarea id="lftext" readonly rows="4" style="box-sizing:border-box;width:100%;font-size:12px"></textarea><p id="lfmsg" style="font-size:12px;color:lightblue">僅分析目前頁面可見的標題與標記；不讀取密碼、不上傳資料。</p>';
(d.body||d.documentElement).appendChild(panel);
var q=function(x){return panel.querySelector("#"+x);},put=function(x,v){q(x).textContent=v;};
put("lfip","IP："+host);put("lfbrand","品牌："+brand);put("lftype","類型："+type);put("lftrust","可信度："+level+"；依據："+(match?match.source:"沒有明確品牌線索"));put("lftitle","頁面標題："+(title||"無"));
var sel=q("lfcat");if(Array.from(sel.options).some(function(o){return o.value===type;}))sel.value=type;
function exportText(){q("lftext").value=JSON.stringify({format:"lanfinder-device-v1",ip:host,brand:brand,type:sel.value,confidence:level,source:match?match.source:"unknown"});}
sel.onchange=exportText;exportText();
q("lfexit").onclick=function(){panel.remove();};
q("lfcopy").onclick=function(){
var t=q("lftext");t.focus();t.select();
try{if(d.execCommand("copy")){put("lfmsg","已複製設備紀錄；可以貼回 ChatGPT 或保存到筆記。");return;}}catch(e){}
put("lfmsg","無法自動複製，請長按下方紀錄並選擇複製。");
};
}catch(e){alert("LAN Identifier error: "+String(e));}
})();
