/* Activity is local. Preserve expanded rows, selection and scroll during polling. */
window.BrainActivity = (() => {
 const number=n=>n===null||n===undefined?'Not reported':Number(n).toLocaleString();
 const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
 const get=async path=>{const response=await fetch(path,{headers:{'X-Brain-Request':'local'}}),data=await response.json();if(!response.ok)throw new Error(data.error||'Activity could not be loaded.');return data;};
 function mount(root){
  root.classList.add('usage-shell','activity-tracker');
  const toolbar=el('div',undefined,'activity-toolbar'),search=el('input'),state=el('select'),live=el('button','Pause updates'),refreshButton=el('button','Refresh');
  search.type='search';search.placeholder='Search requests on this page';search.setAttribute('aria-label','Search activity');
  for(const value of ['all','running','complete','thinking','acting','error','stopped','cancelled','interrupted'])state.add(new Option(value==='all'?'All statuses':value,value));state.setAttribute('aria-label','Filter activity status');
  toolbar.append(search,state,live,refreshButton);
  const note=el('p','Detailed activity is kept for 7 days. Model input is redacted before transmission; fixed system instructions are omitted. Local tool details stay on this computer.','usage-muted activity-notice');
  const sectionTitle=el('div',undefined,'activity-section-title');sectionTitle.append(el('h2','Request history'),el('span','Page totals · Last 7 days'));
  const overview=el('div',undefined,'usage-kpis activity-overview'),metrics={};
  for(const [key,label] of [['requests','Requests'],['calls','Model calls'],['tokens','Reported tokens'],['retries','Retries']]){const box=el('div',undefined,'usage-kpi'),value=el('strong','—');box.append(el('span',label),value);overview.append(box);metrics[key]=value;}
  const limits=el('details',undefined,'activity-limits'),form=el('form',undefined,'activity-policies'),limitStatus=el('p','','usage-muted');limits.append(el('summary','Request budgets & recovery limits'),form,limitStatus);
  const fields={};for(const [key,label,max] of [['agent_task_call_limit','Total model calls (0 = no fixed limit)',10000],['agent_task_token_limit','Token budget (0 = no fixed limit)',10000000],['agent_no_progress_turns','Review after stalled turns',10],['agent_max_output_tokens','Maximum output tokens',16384]]){const wrap=el('label',label),input=el('input');input.type='number';input.min=key.includes('no_progress')?2:key.includes('output')?128:0;input.max=max;input.required=true;input.setAttribute('aria-label',label);wrap.append(input);form.append(wrap);fields[key]=input;}
  const save=el('button','Save limits','usage-primary');save.type='submit';form.append(save);
  get('/api/brain/status').then(data=>{for(const [key,input] of Object.entries(fields))input.value=data.settings?.[key]??(key.includes('no_progress')?3:key.includes('output')?4096:0);}).catch(error=>limitStatus.textContent=error.message);
  form.onsubmit=async event=>{event.preventDefault();try{const response=await fetch('/api/brain/settings',{method:'POST',headers:{'Content-Type':'application/json','X-Brain-Request':'local'},body:JSON.stringify(Object.fromEntries(Object.entries(fields).map(([key,input])=>[key,Number(input.value)])))}),data=await response.json();if(!response.ok||!data.success)throw new Error(data.error||'Limits could not be saved');limitStatus.textContent='Saved for new requests. Repeated failures still trigger recovery review.';}catch(error){limitStatus.textContent=error.message;}};
  const status=el('p','Loading activity…','usage-muted');status.setAttribute('role','status');
  const list=el('div',undefined,'activity-list');list.setAttribute('aria-label','Requests');
  const pagination=el('div',undefined,'usage-filters'),previous=el('button','Previous'),next=el('button','Next');pagination.append(previous,next);
  const footer=el('div',undefined,'activity-footer');footer.append(status,pagination);root.append(sectionTitle,overview,toolbar,list,footer,limits,note);
  let offset=0,nextOffset=null,busy=false,pending=false,paused=false,runs=[];
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
     const detail=el('section',undefined,'activity-detail');detail.setAttribute('aria-label','Request details');detail._digest='';detail._expanded=new Set();detail._pages=new Map();row._before=null;row._cursors=[];
     row.append(summary,detail);rows.set(run.id,row);
     row.addEventListener('toggle',()=>{if(row.open)loadDetail(run.id,row).catch(error=>status.textContent=error.message);});
    }
    const summary=row.firstElementChild;
    summary.querySelector('.activity-badge').textContent=run.state;summary.querySelector('.activity-badge').dataset.state=run.state;
    summary.querySelector('time').textContent=new Date(run.started).toLocaleTimeString();
    summary.querySelector('strong').textContent=run.request||'Untitled request';
    summary.querySelector('small').textContent=`${new Date(run.started).toLocaleDateString()} · ${run.source} · ${run.cloud_calls} model calls · ${number(run.total_tokens)} tokens · ${run.retries} retries`;
    row.hidden=!((state.value==='all'||run.state===state.value)&&[run.request,run.source,run.state].join(' ').toLowerCase().includes(query));
    if(!row.hidden)count++;
    // Reorder only when needed, so an open row and its selected text keep their DOM.
    const index=runs.indexOf(run);if(list.children[index]!==row)list.insertBefore(row,list.children[index]||null);
   }
   if(!count)list.append(el('p',runs.length?'No requests match these filters. Try another search or status.':'Your next request will appear here. Expand it to inspect model calls and results.','activity-empty'));
  }
  function pagedText(parent,detail,key,url,label){
   const holder=el('div',undefined,'activity-text-pages');holder.dataset.textPage=key;parent.append(holder);
   const show=page=>{
    holder.replaceChildren();
    if(!page){const open=el('button',label);open.onclick=()=>load(0);holder.append(open);return;}
    holder.append(el('p',`Characters ${number(page.offset+1)}–${number(Math.min(page.offset+page.text.length,page.total))} of ${number(page.total)}`,'usage-muted'),el('pre',page.text));
    if(page.limited)holder.append(el('p','This legacy event exceeds the safe display limit. Its preview is limited to 2 MB.','activity-warning'));
    const controls=el('div',undefined,'usage-filters'),back=el('button','Previous text'),forward=el('button','Next text'),close=el('button','Close full text');
    back.disabled=page.previous_offset===null;forward.disabled=page.next_offset===null;
    back.onclick=()=>load(page.previous_offset);forward.onclick=()=>load(page.next_offset);close.onclick=()=>{detail._pages.delete(key);show(null);};controls.append(back,forward,close);holder.append(controls);
   };
   const load=async offset=>{for(const b of holder.querySelectorAll('button'))b.disabled=true;try{
    const page=await get(url+(url.includes('?')?'&':'?')+'offset='+offset);detail._pages.delete(key);detail._pages.set(key,page);
    while(detail._pages.size>64)detail._pages.delete(detail._pages.keys().next().value);
    if(holder.isConnected)show(page);
   }catch(error){status.textContent=error.message;show(detail._pages.get(key));}};
   show(detail._pages.get(key));
  }
  function renderDetail(data,detail){
   const expanded=detail._expanded;
   const signature=JSON.stringify(data);if(signature===detail._digest)return;detail._digest=signature;
   const top=detail.scrollTop;
   for(const box of detail.querySelectorAll('details[data-event]')){if(box.open)expanded.add(box.dataset.event);else expanded.delete(box.dataset.event);}
   const activeSelection=window.getSelection();if(activeSelection?.toString()&&detail.contains(activeSelection.anchorNode)){detail._digest='';return;}
   detail.replaceChildren();
   const heading=el('div',undefined,'activity-request-header'),badge=el('span',data.run.state,'activity-badge');badge.dataset.state=data.run.state;heading.append(badge,el('span',new Date(data.run.started).toLocaleString(),'usage-muted'),el('h3',data.run.request));detail.append(el('h4','Request'),heading);
   if(data.run.request_truncated)pagedText(detail,detail,'request','/api/activity/'+data.run.id+'/text?field=request','Read full request');
   const kpis=el('div',undefined,'usage-kpis');
   const sum=key=>data.calls.reduce((n,c)=>n+(c[key]||0),0),known=data.calls.filter(c=>c.total_tokens!==null).length;
   const usage=data.usage||{calls:data.calls.length,input_tokens:sum('input_tokens'),output_tokens:sum('output_tokens'),retries:sum('retry'),latency_ms:sum('latency_ms'),known_usage_calls:known};
   for(const [label,value] of [['Model calls',usage.calls],['Input tokens',usage.input_tokens],['Output tokens',usage.output_tokens],['Retries',usage.retries],['Model time',`${(usage.latency_ms/1000).toFixed(1)} s`]]){const box=el('div',undefined,'usage-kpi');box.append(el('span',label),el('strong',typeof value==='number'?number(value):value));kpis.append(box);}detail.append(kpis);
   if(usage.known_usage_calls<usage.calls)detail.append(el('p',`${usage.calls-usage.known_usage_calls} calls did not report usage; their token counts are unknown.`,'usage-muted'));
   if(data.run.stop_reason){const warning=el('div',data.run.stop_reason,'activity-warning');detail.append(warning);}
   if(data.run.reply){const reply=el('div',undefined,'activity-answer');reply.append(el('h4','Assistant response'),el('p',data.run.reply));detail.append(reply);}
   if(data.run.reply_truncated)pagedText(detail,detail,'reply','/api/activity/'+data.run.id+'/text?field=reply','Read full response');
   const page=data.pagination;
   if(page&&(page.next_before!==null||page.before!==null)){
    const row=detail.parentElement,controls=el('div',undefined,'usage-filters'),older=el('button','Older events'),newer=el('button','Newer events'),latest=el('button','Latest events');
    older.disabled=page.next_before===null;newer.disabled=!row._cursors.length;latest.disabled=row._before===null;
    older.onclick=()=>{row._cursors.push(row._before);row._before=page.next_before;loadDetail(data.run.id,row).catch(error=>status.textContent=error.message);};
    newer.onclick=()=>{row._before=row._cursors.pop()??null;loadDetail(data.run.id,row).catch(error=>status.textContent=error.message);};
    latest.onclick=()=>{row._before=null;row._cursors=[];loadDetail(data.run.id,row).catch(error=>status.textContent=error.message);};
    controls.append(older,newer,latest);detail.append(el('p',`${data.events.length} of ${number(page.event_count)} events · ${page.before===null?'Latest activity':'Earlier activity'}`,'usage-muted'),controls);
   }
   if(data.calls.length){
    detail.append(el('h4','Model requests'));
    const requests=new Map(),responses=new Map();
    for(const event of data.events){if(event.kind==='cloud_request')requests.set(event.payload.call_id,event);if(event.kind==='cloud_response')responses.set(event.payload.call_id,event);}
    for(const call of data.calls){
     const key='call-'+call.id,box=el('details',undefined,'activity-event activity-call');box.dataset.event=key;box.dataset.state=call.status;box.open=expanded.has(key);
     const summary=el('summary');summary.append(el('strong',`${call.model} · ${call.status==='in_flight'?'In progress':call.status}`),el('span',`Turn ${call.step}${call.retry?' · retry':''} · ${call.character_name||'Assistant'} · ${call.profile_name||'Default'}`));box.append(summary);
     box.append(el('p',`${call.provider} · Input ${number(call.input_tokens)} → Output ${number(call.output_tokens)} tokens · ${((call.latency_ms||0)/1000).toFixed(1)} s`,'usage-muted'));
     const request=requests.get(call.id),response=responses.get(call.id);
     const exchange=el('div',undefined,'activity-exchange'),requestPanel=el('section'),responsePanel=el('section');exchange.append(requestPanel,responsePanel);box.append(exchange);
     requestPanel.append(el('h4','Request'),el('pre',request?JSON.stringify(request.payload.payload??request.payload,null,2):'Request detail is on another event page.'));
     if(request?.payload_truncated)pagedText(requestPanel,detail,'event-'+request.id,'/api/activity/'+data.run.id+'/events/'+request.id,'Read full request data');
     responsePanel.append(el('h4','Response'),el('pre',response?JSON.stringify(response.payload.response??response.payload,null,2):(call.status==='in_flight'?'Waiting for the model response…':'Response detail is on another event page.')));
     if(response?.payload_truncated)pagedText(responsePanel,detail,'event-'+response.id,'/api/activity/'+data.run.id+'/events/'+response.id,'Read full response data');
     if(response?.payload.error)box.append(el('p',response.payload.error,'activity-warning'));
     box.addEventListener('toggle',()=>{if(box.open)expanded.add(key);else expanded.delete(key);});detail.append(box);
    }
   }
   detail.append(el('h4','Request timeline'));
   if(!data.events.length)detail.append(el('p','Handled locally. No model exchange was recorded.','usage-muted'));
   for(const event of data.events){
    const box=el('details',undefined,'activity-event');box.dataset.event=String(event.id);box.open=expanded.has(String(event.id));
    const summary=el('summary'),name=el('strong',event.kind.replaceAll('_',' ')),meta=el('span',`${event.step?'Turn '+event.step+' · ':''}${new Date(event.at).toLocaleTimeString()}`,'usage-muted');summary.append(name,meta);box.append(summary);
    const payload=el('pre',JSON.stringify(event.payload,null,2));box.append(payload);box.addEventListener('toggle',()=>{if(box.open)expanded.add(String(event.id));else expanded.delete(String(event.id));});detail.append(box);
    if(event.payload_truncated)pagedText(box,detail,'event-'+event.id,'/api/activity/'+data.run.id+'/events/'+event.id,'Read full event data');
   }
   detail.scrollTop=top;
  }
  async function loadDetail(id,row){
   if(row._busy||!row.open||row.hidden)return;row._busy=true;const cursor=row._before;
   try{const data=await get('/api/activity/'+id+(cursor===null?'':'?before='+cursor));if(rows.get(id)===row&&cursor===row._before)renderDetail(data,row.lastElementChild);}finally{row._busy=false;if(cursor!==row._before&&rows.get(id)===row)loadDetail(id,row).catch(error=>status.textContent=error.message);}
  }
  async function refresh(){if(busy){pending=true;return;}busy=true;const requestedOffset=offset;try{
   const data=await get('/api/activity?offset='+requestedOffset);if(requestedOffset!==offset){pending=true;return;}runs=data.runs;nextOffset=data.next_offset;previous.disabled=offset===0;next.disabled=nextOffset===null;
   renderList();metrics.requests.textContent=number(runs.length);metrics.calls.textContent=number(runs.reduce((n,r)=>n+(r.cloud_calls||0),0));metrics.tokens.textContent=number(runs.reduce((n,r)=>n+(r.total_tokens||0),0));metrics.retries.textContent=number(runs.reduce((n,r)=>n+(r.retries||0),0));
   status.textContent=`Page ${Math.floor(offset/30)+1} · ${paused?'Updates paused':'Updated '+new Date().toLocaleTimeString()}`;overview.setAttribute('aria-label','Totals for requests on this page');
   // Collapsed requests never fetch potentially large request/response payloads.
   for(const [id,row] of rows)if(row.open&&!row.hidden)await loadDetail(id,row);
  }catch(error){status.textContent=error.message;}finally{busy=false;if(pending){pending=false;refresh();}}}
  search.oninput=renderList;state.onchange=renderList;
  live.onclick=()=>{paused=!paused;live.textContent=paused?'Resume updates':'Pause updates';live.setAttribute('aria-pressed',String(paused));status.textContent=paused?'Live updates paused':'Resuming live updates…';if(!paused)refresh();};refreshButton.onclick=refresh;
  previous.onclick=()=>{offset=Math.max(0,offset-30);for(const row of rows.values())row.remove();rows.clear();refresh();};next.onclick=()=>{if(nextOffset!==null){offset=nextOffset;for(const row of rows.values())row.remove();rows.clear();refresh();}};
  refresh();const timer=setInterval(()=>{if(!paused&&!document.hidden&&root.offsetParent!==null)refresh();},2500);window.ConsoleControls?.enhance(toolbar);
  return {refresh,isPaused:()=>paused,dispose:()=>clearInterval(timer)};
 }
 return {mount};
})();
