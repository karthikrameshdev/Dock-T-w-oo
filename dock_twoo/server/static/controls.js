/* One searchable, keyboard-accessible select for console and native web drawers. */
window.ConsoleControls = (() => {
  let sequence=0, active=null;
  function labelFor(select) {
    return select.getAttribute('aria-label') || (select.labels?.[0]?.querySelector('span')?.textContent || select.labels?.[0]?.textContent || select.closest('.form-group')?.querySelector('label')?.textContent || 'Select an option').trim();
  }
  function enhance(root=document) {
    const selects=[...(root.matches?.('select')?[root]:[]),...root.querySelectorAll('select:not([multiple])')];
    for(const select of selects) {
      if(select.multiple)continue;
      if(select._refreshCustomDropdown){select._refreshCustomDropdown();continue;}
      const id='console-options-'+(++sequence), name=labelFor(select);
      select.classList.add('console-native-select');select.tabIndex=-1;select.setAttribute('aria-hidden','true');
      const wrapper=document.createElement('div');wrapper.className='custom-dropdown-container';
      const trigger=document.createElement('button');trigger.type='button';trigger.className='custom-dropdown-trigger';
      trigger.id='console-trigger-'+sequence;
      for(const label of [...(select.labels||[])])label.htmlFor=trigger.id;
      trigger.setAttribute('role','combobox');trigger.setAttribute('aria-label',name);trigger.setAttribute('aria-expanded','false');trigger.setAttribute('aria-controls',id);trigger.setAttribute('aria-haspopup','listbox');
      const value=document.createElement('span');value.className='custom-dropdown-value';
      const arrow=document.createElement('span');arrow.className='custom-dropdown-arrow';arrow.textContent='⌄';arrow.setAttribute('aria-hidden','true');trigger.append(value,arrow);wrapper.append(trigger);select.after(wrapper);
      const menu=document.createElement('div');menu.className='custom-dropdown-menu';menu.hidden=true;
      const searchWrap=document.createElement('div');searchWrap.className='custom-dropdown-search-wrapper';
      const search=document.createElement('input');search.type='search';search.className='custom-dropdown-search';search.placeholder='Search…';search.autocomplete='off';search.setAttribute('aria-label','Search '+name+' options');search.setAttribute('aria-controls',id);
      searchWrap.append(search);
      const list=document.createElement('div');list.id=id;list.className='custom-dropdown-list';list.setAttribute('role','listbox');list.setAttribute('aria-label',name+' options');menu.append(searchWrap,list);document.body.append(menu);
      let focused=-1, items=[], lastSync='';
      function focusItem(index){
        focused=index;
        items.forEach((item,i)=>item.classList.toggle('keyboard-focus',i===index));
        if(items[index]){search.setAttribute('aria-activedescendant',items[index].id);items[index].scrollIntoView({block:'nearest'});}
        else search.removeAttribute('aria-activedescendant');
      }
      function options(){
        list.replaceChildren();items=[];focused=-1;search.removeAttribute('aria-activedescendant');
        const query=search.value.trim().toLocaleLowerCase();
        for(const [index,option] of [...select.options].entries()) {
          if(option.hidden || !option.textContent.toLocaleLowerCase().includes(query))continue;
          const item=document.createElement('button');item.type='button';item.className='custom-dropdown-item';item.tabIndex=-1;item.id=id+'-'+index;item.setAttribute('role','option');item.setAttribute('aria-selected',String(option.selected));
          item.disabled=option.disabled || option.parentElement?.disabled===true;
          const text=document.createElement('span');text.textContent=option.textContent;item.append(text);
          if(option.selected){item.classList.add('selected');const check=document.createElement('span');check.textContent='✓';check.setAttribute('aria-hidden','true');item.append(check);}
          item.addEventListener('click',()=>{select.value=option.value;select.dispatchEvent(new Event('change',{bubbles:true}));sync();close(true);});
          list.append(item);if(!item.disabled)items.push(item);
        }
        if(!list.children.length){const empty=document.createElement('p');empty.className='custom-dropdown-empty';empty.textContent='No matching options';list.append(empty);}
      }
      function position(){
        if(menu.hidden)return;
        if(!wrapper.isConnected || !select.isConnected || !wrapper.getClientRects().length){close();return;}
        const rect=trigger.getBoundingClientRect(), below=innerHeight-rect.bottom-8, above=rect.top-8;
        const up=below<240 && above>below, height=Math.max(80,Math.min(280,up?above:below));
        menu.style.width=Math.min(rect.width,innerWidth-16)+'px';menu.style.left=Math.max(8,Math.min(rect.left,innerWidth-rect.width-8))+'px';menu.style.maxHeight=height+'px';
        menu.style.top=(up?Math.max(8,rect.top-Math.min(height,menu.scrollHeight)-4):rect.bottom+4)+'px';
      }
      function close(returnFocus=false){menu.hidden=true;wrapper.classList.remove('open');trigger.setAttribute('aria-expanded','false');if(active?.menu===menu)active=null;if(returnFocus)trigger.focus();}
      function sync(){
        const signature=JSON.stringify([select.value,select.disabled,[...select.options].map(option=>[option.value,option.textContent,option.disabled,option.hidden])]);
        if(signature===lastSync)return;lastSync=signature;
        value.textContent=select.selectedOptions[0]?.textContent || 'Select…';trigger.disabled=select.disabled;trigger.title=value.textContent;
        if(select.disabled)close();if(!menu.hidden){options();position();}
      }
      function open(){
        if(trigger.disabled)return;
        if(active)active.close();
        search.value='';options();menu.hidden=false;wrapper.classList.add('open');trigger.setAttribute('aria-expanded','true');active={menu,wrapper,close,position};position();search.focus();
      }
      trigger.addEventListener('click',()=>menu.hidden?open():close());
      trigger.addEventListener('keydown',event=>{if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();open();focusItem(event.key==='ArrowUp'?items.length-1:0);}else if(event.key==='Escape')close();});
      search.addEventListener('input',()=>{options();position();});
      search.addEventListener('keydown',event=>{
        if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();if(items.length)focusItem(event.key==='ArrowDown'?(focused+1)%items.length:focused<=0?items.length-1:focused-1);}
        else if(event.key==='Enter'){event.preventDefault();(items[focused]||items[0])?.click();}
        else if(event.key==='Escape'){event.preventDefault();close(true);}
        else if(event.key==='Tab')close(true);
      });
      select.addEventListener('change',sync);select.addEventListener('invalid',event=>{event.preventDefault();trigger.focus();});
      select._refreshCustomDropdown=sync;select._hasCustomDropdown=true;sync();
    }
  }
  document.addEventListener('pointerdown',event=>{if(active&&!active.menu.contains(event.target)&&!active.wrapper.contains(event.target))active.close();});
  window.addEventListener('resize',()=>active?.position());
  document.addEventListener('scroll',event=>{if(active&&!active.menu.contains(event.target))active.position();},true);
  const observer=new MutationObserver(changes=>{
    for(const change of changes){
      if(change.target instanceof HTMLSelectElement || change.target instanceof HTMLOptionElement || change.target instanceof HTMLOptGroupElement){const select=change.target.closest('select');if(select)enhance(select);}
      for(const node of change.addedNodes)if(node.nodeType===1 && (node.matches('select')||node.querySelector('select')))enhance(node);
    }
    if(active&&!active.wrapper.isConnected){active.menu.remove();active.close();}
  });
  function start(){enhance();observer.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled','label','selected']});}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
  return {enhance};
})();
window.initSearchableDropdowns=()=>window.ConsoleControls.enhance();
