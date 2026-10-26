/* Character model and voice settings. Live tasks are in the Dock2 Live Trail drawer. */
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
  refresh();setInterval(()=>{if(root.offsetParent!==null&&!document.hidden)refresh();},3000);
})();
