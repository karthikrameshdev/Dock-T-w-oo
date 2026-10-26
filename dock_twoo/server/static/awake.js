/* Wake preferences are per identity; they never control task leases or manual UI. */
(() => {
  const list=document.getElementById('assistantAwakeList');if(!list)return;
  const status=document.getElementById('assistantAwakeStatus'),search=document.getElementById('assistantAwakeSearch');
  const headers={'X-Brain-Request':'local','Content-Type':'application/json'};
  const rows=new Map();
  function render(characters){
    for(const entry of characters){
      let row=rows.get(entry.id);
      if(!row){
        row=document.createElement('label');row.className='assistant-awake-row';row.dataset.character=entry.id;
        const description=document.createElement('span'),name=document.createElement('strong'),hint=document.createElement('small'),input=document.createElement('input');
        name.textContent=entry.name;hint.textContent=entry.locked?'Default assistant · always on':'Wake by name';description.append(name,hint);
        input.type='checkbox';input.setAttribute('role','switch');input.setAttribute('aria-label',entry.name+' Awake');input.disabled=entry.locked;
        input.addEventListener('change',async()=>{
          const enabled=input.checked;input.disabled=true;status.textContent='Saving '+entry.name+'…';
          try{
            const response=await fetch('/api/brain/awake',{method:'POST',headers,body:JSON.stringify({character_id:entry.id,enabled})}),data=await response.json();
            if(!response.ok)throw new Error(data.error||'Awake preference could not be saved.');
            render(data.characters);status.textContent=`${entry.name} Awake ${enabled?'on':'off'}. Background work is unaffected.`;
          }catch(error){input.checked=!enabled;status.textContent=error.message;}finally{input.disabled=entry.locked;}
        });
        row.append(description,input);list.append(row);rows.set(entry.id,row);
      }
      row.querySelector('input').checked=entry.enabled;
    }
  }
  search.addEventListener('input',()=>{const query=search.value.trim().toLowerCase();for(const row of rows.values())row.hidden=!row.textContent.toLowerCase().includes(query);});
  async function load(){
    try{const response=await fetch('/api/brain/awake',{headers}),data=await response.json();if(!response.ok)throw new Error(data.error||'Awake settings could not load.');render(data.characters);status.textContent='Settings save immediately and are retained after restart.';}
    catch(error){status.textContent=error.message;}
  }
  load();document.querySelector('[data-tab="brain-tab-awake"]')?.addEventListener('click',load);
})();
