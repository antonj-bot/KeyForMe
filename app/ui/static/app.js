const $ = id => document.getElementById(id);
let token = "";
let clearedBefore = 0;
let lastSignature = "";
async function refresh(){
  try {
    const r=await fetch('/api/state',{cache:'no-store'});
    if(!r.ok) throw Error('Connection failed');
    const s=await r.json();token=s.token;
    $('status').textContent=s.status;
    $('dot').classList.toggle('busy',s.busy);
    $('extract').disabled=s.busy;
    $('extract').innerHTML=s.busy?'Working…':'Extract <span aria-hidden="true">→</span>';
    $('report').textContent=s.report_type||'—';
    $('units').textContent=s.units??'—';
    $('warnings').textContent=s.warnings??0;
    const rows=s.logs.slice(clearedBefore);
    const signature=JSON.stringify(rows);
    if(signature!==lastSignature){
      lastSignature=signature;
      const box=$('loglist');box.replaceChildren();
      if(!rows.length){const e=document.createElement('div');e.className='empty';e.textContent='No activity yet';box.append(e);}
      for(const row of rows){const el=document.createElement('div');el.className='line';const time=document.createElement('span');time.className='time';time.textContent=row.time;const text=document.createElement('span');text.className=row.level;text.textContent=row.message;el.append(time,text);box.append(el);}
      box.scrollTop=box.scrollHeight;
    }
  }catch(e){$('status').textContent='Disconnected';$('extract').disabled=true;}
}
$('extract').addEventListener('click',async()=>{
  $('extract').disabled=true;
  try {const r=await fetch('/api/extract',{method:'POST',headers:{'X-KeyForMe-Token':token}});if(!r.ok)throw Error((await r.json()).detail||'Could not start');}
  catch(e){alert(e.message);}
  refresh();
});
$('clear').addEventListener('click',()=>{fetch('/api/state').then(r=>r.json()).then(s=>{clearedBefore=s.logs.length;lastSignature='';$('loglist').replaceChildren();});});
setInterval(refresh,700);refresh();
