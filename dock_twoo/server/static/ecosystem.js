/* Character model/voice assignments and Brain's authenticated local task trail. */
(() => {
  const byId=id=>document.getElementById(id), root=byId('agentCharacterSettings');
  if(!root)return;
  const headers={'X-Brain-Request':'local','Content-Type':'application/json'};
  let catalog=[],profiles=[],bindings={},voices={},busy=false,dirty=false;
  const select=byId('agentCharacter'),profile=byId('agentCharacterProfile'),voice=byId('agentCharacterVoice');
  for(const [value,label] of [['af_heart','Heart · American female'],['af_bella','Bella · American female'],['am_adam','Adam · American male'],['am_michael','Michael · American male'],['bf_emma','Emma · British female'],['bm_george','George · British male']])voice.add(new Option(label,value));
  function fill(){
    const id=select.value,entry=catalog.find(c=>c.id===id);if(!entry)return;
    profile.replaceChildren(new Option('Use default agent model',''));
    for(const p of profiles)profile.add(new Option(`${p.name} · ${p.model||'Not configured'}`,p.id));
    profile.value=bindings[id]||'';
    const tuning=voices[id]||{voice:'af_heart',speed:1,pitch:1};
    voice.value=tuning.voice;byId('agentCharacterSpeed').value=Number(tuning.speed.toFixed(3));byId('agentCharacterPitch').value=Number(tuning.pitch.toFixed(3));
    byId('agentCharacterRole').textContent=`${entry.name} · ${entry.species.replaceAll('_',' ')} · Peer agent · can delegate to available agents`;
    window.ConsoleControls?.enhance(root);dirty=false;
  }
  async function refresh(){
    if(busy)return;busy=true;
    try{
      const response=await fetch('/api/brain/model',{headers}),data=await response.json();if(!response.ok)throw new Error(data.error||'Agent settings could not load.');
      profiles=data.profiles||[];bindings=data.bindings||{};voices=data.voices||{};
      if(!catalog.length){catalog=data.characters||[];for(const entry of catalog)select.add(new Option(`${entry.name} · ${entry.species.replaceAll('_',' ')}`,entry.id));}
      if(!dirty)fill();
    }catch(error){byId('agentCharacterStatus').textContent=error.message;}finally{busy=false;}
  }
  select.addEventListener('change',fill);
  for(const field of [profile,voice,byId('agentCharacterSpeed'),byId('agentCharacterPitch')])field.addEventListener('input',()=>{dirty=true;});
  byId('agentCharacterSave').addEventListener('click',async()=>{
    const button=byId('agentCharacterSave');button.disabled=true;
    try{
      const response=await fetch('/api/brain/character-profile',{method:'POST',headers,body:JSON.stringify({character_id:select.value,profile_id:profile.value,tuning:{voice:voice.value,speed:Number(byId('agentCharacterSpeed').value),pitch:Number(byId('agentCharacterPitch').value)}})}),data=await response.json();
      if(!response.ok)throw new Error(data.error||'Character could not be saved.');
      dirty=false;await refresh();byId('agentCharacterStatus').textContent='Character settings saved. Accepted tasks retain their original model.';
    }catch(error){byId('agentCharacterStatus').textContent=error.message;}finally{button.disabled=false;}
  });
  byId('agentCharacterForget').addEventListener('click',async()=>{
    const name=catalog.find(c=>c.id===select.value)?.name||'this character';
    if(!confirm(`Clear ${name}'s conversation summaries, preferences and learned workflow policy? Saved tasks, notes and documents are retained.`))return;
    try{const response=await fetch('/api/brain/memory/forget',{method:'POST',headers,body:JSON.stringify({character_id:select.value})}),data=await response.json();if(!response.ok)throw new Error(data.error);byId('agentCharacterStatus').textContent='Character memory cleared.';}catch(error){byId('agentCharacterStatus').textContent=error.message;}
  });
  const trailRows=new Map();let trailBusy=false;
  async function trail(){
    const target=byId('agentTaskTrail');if(!target||target.offsetParent===null||document.hidden||trailBusy)return;trailBusy=true;
    try{
      const response=await fetch('/api/brain/ecosystem',{headers}),data=await response.json();if(!response.ok)throw new Error(data.error||'Agent trail unavailable.');
      const ids=new Set((data.jobs||[]).slice(0,20).map(j=>j.id));
      for(const [id,row] of trailRows)if(!ids.has(id)){row.remove();trailRows.delete(id);}
      for(const p of target.querySelectorAll(':scope > p'))p.remove();
      const outputs=byId('agentDocumentOutputs');outputs.replaceChildren();
      for(const job of (data.jobs||[]).filter(j=>!j.parent_id&&j.state==='complete').slice(0,5))for(const path of job.artifacts||[]){
        const button=document.createElement('button');button.type='button';button.className='btn btn-secondary';button.textContent='Download '+path.split(/[\\/]/).pop();
        button.addEventListener('click',async()=>{try{const response=await fetch('/api/brain/artifact?path='+encodeURIComponent(path),{headers});if(!response.ok)throw new Error('Document could not be downloaded.');const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=path.split(/[\\/]/).pop();link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(error){byId('agentCharacterStatus').textContent=error.message;}});outputs.append(button);
      }
      if(!data.jobs?.length){const p=document.createElement('p');p.className='field-desc';p.textContent='No agent tasks yet. Ask a character a question to begin.';target.append(p);return;}
      for(const job of data.jobs.slice(0,20)){
        const entry=catalog.find(c=>c.id===job.character_id);
        let details=trailRows.get(job.id);if(!details){details=document.createElement('details');details.dataset.task=job.id;details.append(document.createElement('summary'),document.createElement('pre'));trailRows.set(job.id,details);target.append(details);}
        const title=details.querySelector('summary'),body=details.querySelector('pre');
        title.textContent=`${entry?.name||job.character_id} · ${job.state} · ${job.prompt.slice(0,100)}`;
        const content=JSON.stringify({task:job.id,parent:job.parent_id,profile:profiles.find(p=>p.id===job.profile_id)?.name||job.profile_id,result:job.result,error:job.error,artifacts:job.artifacts},null,2);
        if(body.textContent!==content){const scroll=body.scrollTop;body.textContent=content;body.scrollTop=scroll;}
        body.style.cssText='white-space:pre-wrap;overflow-wrap:anywhere;padding:12px;max-height:240px;overflow:auto';
      }
    }catch(error){byId('agentCharacterStatus').textContent=error.message;}finally{trailBusy=false;}
  }
  refresh();setInterval(()=>{if(root.offsetParent!==null&&!document.hidden)refresh();trail();},3000);
})();
