/* Activity is local. Preserve expanded rows, selection and scroll during polling. */
window.BrainActivity = (() => {
 const number=n=>n===null||n===undefined?'Not reported':Number(n).toLocaleString();
 const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
 const get=async path=>{const response=await fetch(path,{headers:{'X-Brain-Request':'local'}}),data=await response.json();if(!response.ok)throw new Error(data.error||'Activity could not be loaded.');return data;};
 function mount(root){
  root.classList.add('usage-shell','activity-tracker');
  const toolbar=el('div',undefined,'activity-toolbar'),search=el('input'),state=el('select'),live=el('button','Pause live updates'),refreshButton=el('button','Refresh');
  search.type='search';search.placeholder='Search requests on this page';search.setAttribute('aria-label','Search activity');
  for(const value of ['all','running','complete','thinking','acting','error','stopped','cancelled','interrupted'])state.add(new Option(value==='all'?'All statuses':value,value));state.setAttribute('aria-label','Filter activity status');
  toolbar.append(search,state,live,refreshButton);
  const note=el('p','Last 7 days · Model input is redacted locally before transmission. Fixed system instructions are omitted from traces. Local tool details remain on this computer.','usage-muted');
  const limits=el('details',undefined,'activity-limits'),form=el('form',undefined,'activity-policies'),limitStatus=el('p','','usage-muted');limits.append(el('summary','Request budgets & recovery limits'),form,limitStatus);
  const fields={};for(const [key,label,max] of [['agent_task_call_limit','Total model calls (0 = no fixed limit)',10000],['agent_task_token_limit','Token budget (0 = no fixed limit)',10000000],['agent_no_progress_turns','Review after stalled turns',10],['agent_max_output_tokens','Maximum output tokens',16384]]){const wrap=el('label',label),input=el('input');input.type='number';input.min=key.includes('no_progress')?2:key.includes('output')?128:0;input.max=max;input.required=true;input.setAttribute('aria-label',label);wrap.append(input);form.append(wrap);fields[key]=input;}
  const save=el('button','Save limits');save.type='submit';form.append(save);
  get('/api/brain/status').then(data=>{for(const [key,input] of Object.entries(fields))input.value=data.settings?.[key]??(key.includes('no_progress')?3:key.includes('output')?4096:0);}).catch(error=>limitStatus.textContent=error.message);
  form.onsubmit=async event=>{event.preventDefault();try{const response=await fetch('/api/brain/settings',{method:'POST',headers:{'Content-Type':'application/json','X-Brain-Request':'local'},body:JSON.stringify(Object.fromEntries(Object.entries(fields).map(([key,input])=>[key,Number(input.value)])))}),data=await response.json();if(!response.ok||!data.success)throw new Error(data.error||'Limits could not be saved');limitStatus.textContent='Saved for new requests. Repeated failures still trigger recovery review.';}catch(error){limitStatus.textContent=error.message;}};
  const status=el('p','Loading activity…','usage-muted');status.setAttribute('role','status');
  const list=el('div',undefined,'activity-list');list.setAttribute('aria-label','Requests');
  const pagination=el('div',undefined,'usage-filters'),previous=el('button','Previous'),next=el('button','Next');pagination.append(previous,next);root.append(toolbar,note,limits,status,list,pagination);
  let offset=0,nextOffset=null,busy=false,paused=false,runs=[];
  const rows=new Map();
  function renderList(){
   const query=search.value.trim().toLowerCase(),ids=new Set(runs.map(run=>run.id));
   for(const [id,row] of rows)if(!ids.has(id)){row.remove();rows.delete(id);}
   for(const message of list.querySelectorAll(':scope > p'))message.remove();
   let count=0;
   for(const run of runs){
    let row=rows.get(run.id);
    if(!row){
     row=el('details',undefined,'activity-item activity-run');row.dataset.run=run.id;
     const summary=el('summary'),heading=el('div',undefined,'activity-row-heading');heading.append(el('span','','activity-badge'),el('time'));
     summary.append(heading,el('strong'),el('small'));
     const detail=el('section',undefined,'activity-detail');detail.setAttribute('aria-label','Request details');detail._digest='';detail._expanded=new Set();
     row.append(summary,detail);rows.set(run.id,row);
     row.addEventListener('toggle',()=>{if(row.open)loadDetail(run.id,row).catch(error=>status.textContent=error.message);});
    }
    const summary=row.firstElementChild;
    summary.querySelector('.activity-badge').textContent=run.state;
    summary.querySelector('time').textContent=new Date(run.started).toLocaleTimeString();
    summary.querySelector('strong').textContent=run.request||'Untitled request';
    summary.querySelector('small').textContent=`${new Date(run.started).toLocaleDateString()} · ${run.source} · ${run.cloud_calls} model calls · ${number(run.total_tokens)} tokens · ${run.retries} retries`;
    row.hidden=!((state.value==='all'||run.state===state.value)&&[run.request,run.source,run.state].join(' ').toLowerCase().includes(query));
    if(!row.hidden)count++;
    // Reorder only when needed, so an open row and its selected text keep their DOM.
    const index=runs.indexOf(run);if(list.children[index]!==row)list.insertBefore(row,list.children[index]||null);
   }
   if(!count)list.append(el('p','No requests match these filters.','usage-muted'));
  }
  function renderDetail(data,detail){
   const expanded=detail._expanded;
   const signature=JSON.stringify(data);if(signature===detail._digest)return;detail._digest=signature;
   const top=detail.scrollTop;
   for(const box of detail.querySelectorAll('details[data-event]')){if(box.open)expanded.add(box.dataset.event);else expanded.delete(box.dataset.event);}
   const activeSelection=window.getSelection();if(activeSelection?.toString()&&detail.contains(activeSelection.anchorNode)){detail._digest='';return;}
   detail.replaceChildren();
   const heading=el('div',undefined,'activity-request-header');heading.append(el('span',data.run.state,'activity-badge'),el('span',new Date(data.run.started).toLocaleString(),'usage-muted'),el('h3',data.run.request));detail.append(heading);
   const kpis=el('div',undefined,'usage-kpis');
   const sum=key=>data.calls.reduce((n,c)=>n+(c[key]||0),0),known=data.calls.filter(c=>c.total_tokens!==null).length;
   for(const [label,value] of [['Model calls',data.calls.length],['Input tokens',sum('input_tokens')],['Output tokens',sum('output_tokens')],['Retries',sum('retry')],['Model time',`${(sum('latency_ms')/1000).toFixed(1)} s`]]){const box=el('div',undefined,'usage-kpi');box.append(el('span',label),el('strong',typeof value==='number'?number(value):value));kpis.append(box);}detail.append(kpis);
   if(known<data.calls.length)detail.append(el('p',`${data.calls.length-known} calls did not report usage; their token counts are unknown.`,'usage-muted'));
   if(data.run.stop_reason){const warning=el('div',data.run.stop_reason,'activity-warning');detail.append(warning);}
   if(data.run.reply){const reply=el('div',undefined,'activity-answer');reply.append(el('h4','Assistant response'),el('p',data.run.reply));detail.append(reply);}
   if(data.calls.length){
    detail.append(el('h4','Model requests'));
    const requests=new Map(),responses=new Map();
    for(const event of data.events){if(event.kind==='cloud_request')requests.set(event.payload.call_id,event.payload);if(event.kind==='cloud_response')responses.set(event.payload.call_id,event.payload);}
    for(const call of data.calls){
     const key='call-'+call.id,box=el('details',undefined,'activity-event activity-call');box.dataset.event=key;box.dataset.state=call.status;box.open=expanded.has(key);
     const summary=el('summary');summary.append(el('strong',`${call.model} · ${call.status==='in_flight'?'In progress':call.status}`),el('span',`Turn ${call.step}${call.retry?' · retry':''} · ${call.character_name||'Assistant'} · ${call.profile_name||'Default'}`));box.append(summary);
     box.append(el('p',`${call.provider} · Input ${number(call.input_tokens)} → Output ${number(call.output_tokens)} tokens · ${((call.latency_ms||0)/1000).toFixed(1)} s`,'usage-muted'));
     box.append(el('h4','Request'),el('pre',requests.has(call.id)?JSON.stringify(requests.get(call.id).payload,null,2):'Request detail is unavailable.'));
     const response=responses.get(call.id);box.append(el('h4','Response'),el('pre',response?JSON.stringify(response.response,null,2):(call.status==='in_flight'?'Waiting for the model response…':'Response detail is unavailable.')));
     if(response?.error)box.append(el('p',response.error,'activity-warning'));
     box.addEventListener('toggle',()=>{if(box.open)expanded.add(key);else expanded.delete(key);});detail.append(box);
    }
   }
   detail.append(el('h4','Request timeline'));
   if(!data.events.length)detail.append(el('p','Handled locally. No model exchange was recorded.','usage-muted'));
   for(const event of data.events){
    const box=el('details',undefined,'activity-event');box.dataset.event=String(event.id);box.open=expanded.has(String(event.id));
    const summary=el('summary'),name=el('strong',event.kind.replaceAll('_',' ')),meta=el('span',`${event.step?'Turn '+event.step+' · ':''}${new Date(event.at).toLocaleTimeString()}`,'usage-muted');summary.append(name,meta);box.append(summary);
    const payload=el('pre',JSON.stringify(event.payload,null,2));box.append(payload);box.addEventListener('toggle',()=>{if(box.open)expanded.add(String(event.id));else expanded.delete(String(event.id));});detail.append(box);
   }
   detail.scrollTop=top;
  }
  async function loadDetail(id,row){
   if(row._busy||!row.open||row.hidden)return;row._busy=true;
   try{const data=await get('/api/activity/'+id);if(rows.get(id)===row)renderDetail(data,row.lastElementChild);}finally{row._busy=false;}
  }
  async function refresh(){if(busy)return;busy=true;try{
   const data=await get('/api/activity?offset='+offset);runs=data.runs;nextOffset=data.next_offset;previous.disabled=offset===0;next.disabled=nextOffset===null;
   renderList();status.textContent=`${runs.length} ${runs.length===1?'request':'requests'} on this page · ${paused?'Live updates paused':'Updated '+new Date().toLocaleTimeString()}`;
   // Collapsed requests never fetch potentially large request/response payloads.
   for(const [id,row] of rows)if(row.open&&!row.hidden)await loadDetail(id,row);
  }catch(error){status.textContent=error.message;}finally{busy=false;}}
  search.oninput=renderList;state.onchange=renderList;
  live.onclick=()=>{paused=!paused;live.textContent=paused?'Resume live updates':'Pause live updates';live.setAttribute('aria-pressed',String(paused));if(!paused)refresh();};refreshButton.onclick=refresh;
  previous.onclick=()=>{offset=Math.max(0,offset-30);for(const row of rows.values())row.remove();rows.clear();refresh();};next.onclick=()=>{if(nextOffset!==null){offset=nextOffset;for(const row of rows.values())row.remove();rows.clear();refresh();}};
  refresh();setInterval(()=>{if(!paused&&!document.hidden&&root.offsetParent!==null)refresh();},2500);window.ConsoleControls?.enhance(toolbar);
  return {refresh,isPaused:()=>paused};
 }
 return {mount};
})();
