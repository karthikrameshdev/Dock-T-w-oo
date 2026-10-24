/* Seven-day local request tracing. Values are rendered as text, never executable HTML. */
window.BrainActivity = (() => {
 const number=n=>Number(n||0).toLocaleString();
 const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
 function mount(root){
  root.classList.add('usage-shell');
  const note=el('p','Detailed activity is kept for up to 7 days (128 MB detail limit). Fixed system instructions are represented by a size and fingerprint; sent conversation, tools and returned payloads are shown below. API credentials are redacted.','usage-muted');
  const policy=el('form',undefined,'activity-policies');
  function field(label,value,min,max){const wrap=el('label',label),input=el('input');input.type='number';input.min=min;input.max=max;input.value=value;input.required=true;input.setAttribute('aria-label',label);wrap.append(input);policy.append(wrap);return input;}
  const calls=field('Maximum cloud calls',8,1,12),tokens=field('Request token budget',24000,2000,64000),stalls=field('Stop after stalled turns',3,2,3),output=field('Maximum output tokens',1024,128,2048),save=el('button','Save credit limits');save.type='submit';policy.append(save);
  const policyStatus=el('p','Loading credit limits…','usage-muted');policyStatus.setAttribute('role','status');
  const status=el('p','Loading activity…','usage-muted');status.setAttribute('role','status');
  const layout=el('div',undefined,'activity-layout'),list=el('div',undefined,'activity-list'),detail=el('section',undefined,'activity-detail');detail.setAttribute('aria-label','Activity details');
  const pagination=el('div',undefined,'usage-filters'),previous=el('button','Previous'),next=el('button','Next');pagination.append(previous,next);layout.append(list,detail);root.append(note,policy,policyStatus,status,layout,pagination);
  let selected='',offset=0,nextOffset=null,signature='',detailSignature='',busy=false;
  async function get(path){const response=await fetch(path,{headers:{'X-Brain-Request':'local'}}),data=await response.json();if(!response.ok)throw new Error(data.error||'Activity could not be loaded.');return data;}
  function details(data){
   const opened=new Set([...detail.querySelectorAll('details[open]')].map(item=>item.dataset.id));detail.replaceChildren();
   detail.append(el('h3',data.run.request));
   const input=data.calls.reduce((sum,call)=>sum+(call.input_tokens||0),0),out=data.calls.reduce((sum,call)=>sum+(call.output_tokens||0),0),models=new Set(data.calls.map(call=>call.provider+'/'+call.model));
   detail.append(el('p',`${data.run.source} · ${data.run.state} · ${data.calls.length} cloud calls · ${models.size} model IDs · ${number(input)} input / ${number(out)} output tokens`,'usage-muted'));
   if(data.run.stop_reason)detail.append(el('p',data.run.stop_reason,'usage-muted'));
   if(data.run.reply){const reply=el('p',data.run.reply);reply.style.margin='12px 0';detail.append(reply);}
   if(!data.events.length)detail.append(el('p','Handled locally. No cloud call was made.','usage-muted'));
   for(const event of data.events){const box=el('details');box.dataset.id=String(event.id);box.open=opened.has(String(event.id));
    const retry=event.payload.retry?' · recovery call':'';
    box.append(el('summary',`${event.step?`Turn ${event.step} · `:''}${event.kind.replaceAll('_',' ')}${retry} · ${new Date(event.at).toLocaleTimeString()}`));
    box.append(el('pre',JSON.stringify(event.payload,null,2)));detail.append(box);
   }
  }
  async function loadDetail(force=false,key=''){
   if(!selected){detail.replaceChildren(el('p','Select a request to inspect its cloud calls and local actions.','usage-muted'));return;}
   if(!force && key===detailSignature)return;
   const target=selected,data=await get('/api/activity/'+target);if(target!==selected)return;details(data);detailSignature=key;
  }
  async function refresh(){if(busy)return;busy=true;try{
   const data=await get('/api/activity?offset='+offset);nextOffset=data.next_offset;previous.disabled=offset===0;next.disabled=nextOffset===null;
   const digest=JSON.stringify(data.runs);
   if(digest!==signature){signature=digest;list.replaceChildren();
    for(const run of data.runs){const button=el('button',undefined,'activity-item'+(run.id===selected?' active':''));button.append(el('strong',run.request),el('small',`${new Date(run.started).toLocaleString()} · ${run.state}\n${run.cloud_calls} calls · ${number(run.total_tokens)} tokens · ${run.retries} recovery calls`));
     button.addEventListener('click',async()=>{selected=run.id;for(const item of list.querySelectorAll('.activity-item'))item.classList.remove('active');button.classList.add('active');try{await loadDetail(true);}catch(error){status.textContent=error.message;}});list.append(button);
    }
   }
   status.textContent=data.runs.length?`${data.runs.length} requests on this page · last 7 days`:'No tracked requests yet. New voice and console requests will appear here. Earlier usage cannot be reconstructed.';
   const run=data.runs.find(run=>run.id===selected);
   if(run)await loadDetail(false,JSON.stringify(run));
  }catch(error){status.textContent=error.message;}finally{busy=false;}}
  previous.addEventListener('click',()=>{offset=Math.max(0,offset-30);signature='';refresh();});next.addEventListener('click',()=>{if(nextOffset!==null){offset=nextOffset;signature='';refresh();}});
  policy.addEventListener('submit',async event=>{event.preventDefault();try{
   const response=await fetch('/api/brain/settings',{method:'POST',headers:{'Content-Type':'application/json','X-Brain-Request':'local'},body:JSON.stringify({agent_max_steps:Number(calls.value),agent_token_budget:Number(tokens.value),agent_no_progress_turns:Number(stalls.value),agent_max_output_tokens:Number(output.value)})});const data=await response.json();if(!response.ok||!data.success)throw new Error(data.error);
   policyStatus.textContent='Credit limits saved. They apply to the next request. Stops never make an extra cloud call.';
  }catch(error){policyStatus.textContent=error.message;}});
  get('/api/brain/status').then(data=>{const settings=data.settings||{};calls.value=Math.min(12,settings.agent_max_steps||8);tokens.value=settings.agent_token_budget||24000;stalls.value=settings.agent_no_progress_turns||3;output.value=settings.agent_max_output_tokens||1024;policyStatus.textContent='Three stalled turns by default, bounded total calls and tokens, no automatic HTTP retries. Token preflight uses an estimate; dashboard counts use provider usage only.';}).catch(error=>policyStatus.textContent=error.message);
  refresh();setInterval(()=>{if(!document.hidden&&root.offsetParent!==null)refresh();},2500);
  return {refresh};
 }
 return {mount};
})();
