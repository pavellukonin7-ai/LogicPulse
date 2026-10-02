// Anonymous, consent-gated, sampled coordinates only. No keystrokes, values or account IDs.
import {api} from './session.js';
let record=null, pending=null, sequence=0, active=0, points=[],clicks={},sending=false,enabled=false,starting=false;
let lastActivity=performance.now(),lastTick=performance.now(),lastMove=0;
const notice=document.querySelector('#analytics-notice');
function choice(){try{return localStorage.getItem('lp_analytics')}catch{return 'no'}}
function save(value){try{localStorage.setItem('lp_analytics',value)}catch{}}
async function start(){if(starting||record||!enabled)return;starting=true;try{const device=innerWidth<768?'mobile':innerWidth<1024?'tablet':'desktop';const result=await api('/api/metrics/sessions',{method:'POST',body:JSON.stringify({consent:true,device,page:'/'})});if(!enabled){await api('/api/metrics/sessions/'+result.id,{method:'DELETE',headers:{'X-Metrics-Token':result.token}});return;}record=result;active=0;sequence=0;points=[];clicks={};lastTick=performance.now();}catch{}finally{starting=false;}}
function target(el){if(el.closest('#auth-nav'))return 'auth';if(el.closest('#submit-request'))return 'submit';if(el.closest('#request-form'))return 'form';if(el.closest('#service-catalog'))return 'service';if(el.closest('#navigation'))return 'navigation';if(el.closest('a[href="#brief"]'))return 'brief';return 'other'}
function point(e,kind){if(!enabled||!record||e.target.closest('#analytics-notice'))return;const height=document.documentElement.scrollHeight;points.push({x:Math.max(0,Math.min(1,e.clientX/innerWidth)),y:Math.max(0,Math.min(1,(e.clientY+scrollY)/height)),kind});if(points.length>120)points.shift();}
addEventListener('pointermove',e=>{lastActivity=performance.now();if(lastActivity-lastMove>1000){point(e,'move');lastMove=lastActivity;}},{passive:true});
addEventListener('click',e=>{lastActivity=performance.now();if(enabled&&record&&!e.target.closest('#analytics-notice')){point(e,'click');const k=target(e.target);clicks[k]=Math.min(50,(clicks[k]||0)+1)}},{passive:true});
for(const ev of ['keydown','scroll','touchstart'])addEventListener(ev,()=>{lastActivity=performance.now()},{passive:true});
setInterval(()=>{const t=performance.now();if(enabled&&record&&!document.hidden&&document.hasFocus()&&t-lastActivity<30000)active+=Math.min(t-lastTick,1500);lastTick=t;},1000);
async function flush(keepalive=false){if(!enabled||!record||sending)return;if(!pending){pending={sequence:++sequence,active_ms:Math.min(3600000,Math.floor(active)),points:points.splice(0,60),clicks};clicks={};}sending=true;try{const r=await fetch('/api/metrics/sessions/'+record.id,{method:'POST',headers:{'Content-Type':'application/json','X-Metrics-Token':record.token},body:JSON.stringify(pending),keepalive});if(r.ok)pending=null;else if(r.status===410){record=null;pending=null;await start();}}catch{}finally{sending=false;}}
setInterval(()=>{if(enabled&&!record)start();flush();},10000);
addEventListener('pagehide',()=>flush(true));
document.addEventListener('visibilitychange',()=>{if(document.hidden)flush(true)});
document.querySelector('#analytics-accept').addEventListener('click',()=>{save('yes');enabled=true;notice.hidden=true;start()});
document.querySelector('#analytics-decline').addEventListener('click',async()=>{save('no');enabled=false;notice.hidden=true;const old=record;record=null;pending=null;points=[];clicks={};if(old)try{await api('/api/metrics/sessions/'+old.id,{method:'DELETE',headers:{'X-Metrics-Token':old.token}})}catch{}});
document.querySelector('#analytics-settings').addEventListener('click',()=>{notice.hidden=false});
if(choice()==='yes'){enabled=true;start()}else if(choice()!=='no')notice.hidden=false;
