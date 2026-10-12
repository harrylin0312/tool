(function(){try{
var d=document,h=location.hostname,m=h.match(/^(10|192|172)\.(\d+)\.(\d+)\.(\d+)$/);
if(!m||(+m[1]===192&&+m[2]!==168)||(+m[1]===172&&(+m[2]<16||+m[2]>31))){alert("Open a private-IP device webpage first");return;}
var old=d.getElementById("lfid");if(old){old.remove();return;}
var t=(d.title||"").slice(0,100),g=d.querySelector('meta[name="generator"]'),a=d.querySelector('meta[name="application-name"]'),f=[["title",t],["generator",g?g.content:""],["application",a?a.content:""],["heading",Array.from(d.querySelectorAll("h1,h2")).slice(0,4).map(x=>x.textContent.slice(0,70)).join(" ")],["logo",Array.from(d.querySelectorAll("img[alt]")).slice(0,5).map(x=>x.alt).join(" ")]];
var b=[["TP-Link","Network",/tp[- ]?link|omada|mercusys/i],["ASUS","Network",/asuswrt|\basus\b/i],["D-Link","Network",/d[- ]?link/i],["NETGEAR","Network",/netgear/i],["MikroTik","Network",/mikrotik|routeros/i],["Ubiquiti","Network",/ubiquiti|unifi/i],["OpenWrt","Router OS",/openwrt|luci/i],["Synology","NAS",/synology|diskstation/i],["QNAP","NAS",/qnap|qts/i],["Proxmox","Virtualization",/proxmox/i],["Home Assistant","Smart home",/home assistant/i],["Hikvision","Camera",/hikvision/i],["Dahua","Camera",/dahua/i]];
var brand="Unknown",kind="Unknown",source="None";
outer:for(var v of f){for(var e of b)if(e[2].test(v[1])){brand=e[0];kind=e[1];source=v[0];break outer;}}
if(kind==="Unknown"&&/login|sign in/i.test(t))kind="Login page";
var z=d.createElement("section");z.id="lfid";z.style.cssText="position:fixed!important;inset:0!important;z-index:2147483647!important;background:#091221!important;color:#fff!important;padding:18px!important;overflow:auto!important;font:15px system-ui!important";
z.innerHTML='<h2>LAN Identifier v0.1</h2><p id="liout"></p><label>Correct type: <select id="litype"><option>Unknown</option><option>Network</option><option>Router OS</option><option>NAS</option><option>Camera</option><option>Smart home</option><option>Virtualization</option><option>Login page</option><option>Web service</option></select></label><p><button id="licopy">Copy record</button> <button id="liclose">Close</button></p><textarea id="litext" readonly rows="4" style="width:95%"></textarea><p id="limsg">Page title and visible metadata only. No data sent.</p>';
(d.body||d.documentElement).appendChild(z);
var q=id=>z.querySelector("#"+id),sel=q("litype");sel.value=kind;
q("liout").textContent="IP: "+h+" | Brand: "+brand+" | Type: "+kind+" | Evidence: "+source+" | Page: "+(t||"none");
function record(){q("litext").value=JSON.stringify({ip:h,brand:brand,type:sel.value,evidence:source});}record();sel.onchange=record;
q("liclose").onclick=()=>z.remove();
q("licopy").onclick=()=>{var x=q("litext");x.focus();x.select();try{if(d.execCommand("copy")){q("limsg").textContent="Copied";return;}}catch(e){}q("limsg").textContent="Select and copy text manually";};
}catch(e){alert("LAN Identifier error: "+e);}
})();
