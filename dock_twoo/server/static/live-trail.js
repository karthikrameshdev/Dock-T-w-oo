/* One local task stream, suspended with the native drawer. Never replace open rows. */
(() => {
  if(new URLSearchParams(location.search).get('theme')==='light')document.body.classList.add('theme-light','usage-light');
  if(new URLSearchParams(location.search).get('embedded')==='1'){document.body.classList.add('workspace-embedded');document.getElementById('agentTaskPanel').open=false;}
  const activity=window.BrainActivity.mount(document.getElementById('liveActivity'));
  const target=document.getElementById('agentTaskTrail'),status=document.getElementById('trailConnection'),rows=new Map();
  const headers={'X-Brain-Request':'local'};
  let busy=false,catalog=[],profiles=[],empty=null;
  const element=(tag,text)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;};
  const get=async path=>{const r=await fetch(path,{headers}),data=await r.json();if(!r.ok)throw new Error(data.error||'Live Trail is unavailable');return data;};
  async function refresh(){
    if(busy||document.hidden||activity.isPaused())return;busy=true;
    try{
      if(!catalog.length){const models=await get('/api/brain/model');catalog=models.characters||[];profiles=models.profiles||[];}
      const data=await get('/api/brain/ecosystem'),jobs=data.jobs||[];
      const terminal=new Set(['complete','error','cancelled','stopped','failed']);
      const active=jobs.filter(job=>!terminal.has(job.state));
      const visible=[...active,...jobs.filter(job=>terminal.has(job.state)).slice(0,10)];
      const ids=new Set(visible.map(job=>job.id));
      for(const [id,row] of rows)if(!ids.has(id)){row.remove();rows.delete(id);}
      if(empty){empty.remove();empty=null;}
      if(!visible.length){empty=element('p','Your agents are ready. Tasks appear here when work begins.');empty.className='trail-empty';target.append(empty);}
      for(const job of visible){
        let row=rows.get(job.id);
        if(!row){row=element('details');row.dataset.task=job.id;const summary=element('summary'),heading=element('div'),badge=element('span');heading.className='trail-job-heading';badge.className='activity-badge';heading.append(element('strong'),badge);summary.append(heading,element('span'));const content=element('div');content.className='trail-job-content';row.append(summary,content);rows.set(job.id,row);target.append(row);}
        const name=catalog.find(c=>c.id===job.character_id)?.name||job.character_id;
        row.querySelector('strong').textContent=name;
        const badge=row.querySelector('.activity-badge');badge.textContent=job.state;badge.dataset.state=job.state;
        row.querySelector('summary>span').textContent=(job.prompt||'Agent task').slice(0,110);
        const signature=JSON.stringify(job);
        if(row._signature!==signature){
          const content=row.lastElementChild,selection=window.getSelection();
          if(selection?.toString()&&content.contains(selection.anchorNode))continue;
          row._signature=signature;content.replaceChildren();
          for(const [label,value] of [['Request',job.prompt],['Profile',profiles.find(p=>p.id===job.profile_id)?.name||job.profile_id||'Default'],['Parent task',job.parent_id],['Response',job.result],['Error',job.error]]){
            if(!value)continue;const p=element('p');p.append(element('b',label+'\n'),document.createTextNode(typeof value==='string'?value:JSON.stringify(value,null,2)));content.append(p);
          }
          if(!terminal.has(job.state))content.append(element('p','Work is in progress. Results will appear here.'));
          for(const path of job.artifacts||[]){
            const button=element('button','Download '+path.split(/[\\/]/).pop());button.type='button';
            button.onclick=async()=>{try{const r=await fetch('/api/brain/artifact?path='+encodeURIComponent(path),{headers});if(!r.ok)throw new Error('Document could not be downloaded');const url=URL.createObjectURL(await r.blob()),link=element('a');link.href=url;link.download=path.split(/[\\/]/).pop();link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(error){status.textContent=error.message;}};content.append(button);
          }
        }
      }
      status.textContent=active.length?`${active.length} ${active.length===1?'task':'tasks'} in progress`:'No active tasks';
    }catch(error){status.textContent=error.message;}finally{busy=false;}
  }
  refresh();const timer=setInterval(refresh,2500);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden){refresh();activity.refresh();}});
  window.addEventListener('pagehide',()=>{clearInterval(timer);activity.dispose();},{once:true});
})();
