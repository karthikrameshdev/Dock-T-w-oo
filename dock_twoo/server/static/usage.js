/* Shared by the console and native Dashboard drawer. No remote chart service. */
window.BrainUsage = (() => {
  const number = value => Number(value || 0).toLocaleString();
  const node = (tag, text, cls) => { const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el; };
  const colors=['#7b96ff','#66d5c1','#ba9cff','#f8bd72'];
  function svg(label) {const el=document.createElementNS('http://www.w3.org/2000/svg','svg');el.setAttribute('viewBox','0 0 400 180');el.setAttribute('role','img');el.setAttribute('aria-label',label);return el;}
  function shape(root,tag,attrs,text) {const el=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [key,value] of Object.entries(attrs))el.setAttribute(key,value);if(text!==undefined)el.textContent=text;root.append(el);return el;}
  function card(title,caption){const box=node('section',undefined,'usage-chart');box.append(node('h3',title),node('p',caption,'usage-muted'));return box;}
  function donut(input,output,unclassified=0) {
    const chart=svg('Cloud input and output token proportions'),sum=input+output+unclassified;
    shape(chart,'circle',{cx:105,cy:85,r:58,fill:'none',stroke:'var(--usage-border)','stroke-width':21});
    let offset=0;
    [input,output,unclassified].forEach((value,index)=>{const percent=sum?value/sum*100:0;shape(chart,'circle',{cx:105,cy:85,r:58,fill:'none',stroke:colors[index],'stroke-width':21,pathLength:100,'stroke-dasharray':`${percent} ${100-percent}`,'stroke-dashoffset':-offset,transform:'rotate(-90 105 85)'});offset+=percent;});
    shape(chart,'text',{x:105,y:84,'text-anchor':'middle',class:'usage-svg-value'},number(sum));
    shape(chart,'text',{x:105,y:105,'text-anchor':'middle',class:'usage-svg-label'},'tokens');
    [['Input',input],['Output',output],...(unclassified?[['Unclassified',unclassified]]:[])].forEach(([label,value],i)=>{shape(chart,'circle',{cx:208,cy:42+i*48,r:5,fill:colors[i]});shape(chart,'text',{x:222,y:47+i*48,class:'usage-svg-label'},label);shape(chart,'text',{x:222,y:67+i*48,class:'usage-svg-value'},number(value));});
    return chart;
  }
  function line(days) {
    const chart=svg('Cloud tokens consumed per day'),max=Math.max(1,...days.map(d=>d.total_tokens));
    for(let i=0;i<4;i++){const y=18+i*43;shape(chart,'line',{x1:38,y1:y,x2:386,y2:y,stroke:'var(--usage-border)'});shape(chart,'text',{x:32,y:y+4,'text-anchor':'end',class:'usage-svg-label'},number(Math.round(max*(1-i/3))));}
    const points=days.map((day,i)=>`${38+i/Math.max(1,days.length-1)*348},${147-day.total_tokens/max*129}`);
    if(points.length===1)shape(chart,'circle',{cx:38,cy:147-days[0].total_tokens/max*129,r:4,fill:colors[0]});
    else shape(chart,'polyline',{points:points.join(' '),fill:'none',stroke:colors[0],'stroke-width':3,'stroke-linejoin':'round','stroke-linecap':'round'});
    for(const i of [...new Set([0,Math.floor((days.length-1)/2),days.length-1])])if(days[i])shape(chart,'text',{x:38+i/Math.max(1,days.length-1)*348,y:171,'text-anchor':i===0?'start':i===days.length-1?'end':'middle',class:'usage-svg-label'},days[i].day.slice(5));
    return chart;
  }
  function bars(models) {
    const chart=svg('Input and output tokens by cloud model'),rows=models.slice().sort((a,b)=>b.total_tokens-a.total_tokens).slice(0,4),max=Math.max(1,...rows.map(row=>row.total_tokens));
    if(!rows.length)shape(chart,'text',{x:200,y:92,'text-anchor':'middle',class:'usage-svg-label'},'No cloud usage in this range');
    rows.forEach((row,i)=>{const y=16+i*40;shape(chart,'text',{x:4,y:y+10,class:'usage-svg-label'},row.model.length>43?row.model.slice(0,40)+'…':row.model);const input=row.input_tokens/max*340,output=row.output_tokens/max*340;shape(chart,'rect',{x:4,y:y+18,width:Math.max(0,input),height:10,rx:3,fill:colors[0]});shape(chart,'rect',{x:4+input,y:y+18,width:Math.max(0,output),height:10,rx:3,fill:colors[1]});if(row.unattributed_tokens)shape(chart,'rect',{x:4+input+output,y:y+18,width:row.unattributed_tokens/max*340,height:10,rx:3,fill:colors[2]});shape(chart,'text',{x:390,y:y+28,'text-anchor':'end',class:'usage-svg-label'},number(row.total_tokens));});
    return chart;
  }
  function outcomes(summary) {
    const chart=svg('Cloud API call outcomes'),values=[['Successful',summary.successful_calls,colors[1]],['Failed',summary.failed_calls,'#f18d9b'],['Cancelled',summary.cancelled_calls,colors[3]]],max=Math.max(1,...values.map(v=>v[1]));
    values.forEach(([label,value,color],i)=>{const y=22+i*48;shape(chart,'text',{x:4,y:y+10,class:'usage-svg-label'},label);shape(chart,'rect',{x:95,y,width:Math.max(1,value/max*245),height:17,rx:5,fill:color});shape(chart,'text',{x:385,y:y+13,'text-anchor':'end',class:'usage-svg-label'},number(value));});return chart;
  }
  function mount(root) {
    root.classList.add('usage-shell');
    const filters=node('form',undefined,'usage-filters'),period=node('select');period.setAttribute('aria-label','Usage period');
    for(const [value,label] of [['month','1 month · this month'],['7d','7 days'],['custom','From / To dates']]){const option=node('option',label);option.value=value;period.append(option);}
    const from=node('input'),to=node('input');from.type=to.type='date';from.setAttribute('aria-label','From date');to.setAttribute('aria-label','To date');
    const apply=node('button','Apply range');apply.type='submit';
    for(const [label,control] of [['Period',period],['From',from],['To',to]]){const field=node('label',undefined,'usage-field');field.append(node('span',label),control);filters.append(field);}filters.append(apply);
    const status=node('p','Loading cloud usage…','usage-muted');status.setAttribute('role','status');
    const kpis=node('div',undefined,'usage-kpis'),charts=node('div',undefined,'usage-charts'),foot=node('p',undefined,'usage-muted');
    root.append(filters,status,kpis,charts,foot);
    let busy=false;
    function render(data){
      const s=data.summary;kpis.replaceChildren();
      for(const [label,value] of [['Total tokens',s.total_tokens],['Input tokens',s.input_tokens],['Output tokens',s.output_tokens],['Cloud calls',s.calls],['Model IDs',s.unique_models],['Recovery calls',s.retries]]){const box=node('div',undefined,'usage-kpi');box.append(node('span',label),node('strong',number(value)));kpis.append(box);}
      charts.replaceChildren();
      for(const [title,caption,graphic] of [['Token distribution','Provider-reported input and output',donut(s.input_tokens,s.output_tokens,s.unattributed_tokens)],['Daily consumption','Provider-reported total tokens',line(data.daily)],['Usage by model','Blue: input · Mint: output · Lilac: unclassified',bars(data.models)],['Call outcomes','Completed cloud API attempts',outcomes(s)]]){const box=card(title,caption);box.append(graphic);charts.append(box);}
      status.textContent=`${data.from} — ${data.to} · Cloud API usage only${data.fixture?' · SYNTHETIC TEST DATA':''}`;
      const coverage=s.unknown_usage_calls?`${number(s.unknown_usage_calls)} calls have unavailable token usage; totals cover reported usage only.`:'Token counts come from provider responses, including context and tool payloads.';
      const cost=s.cost_known_calls?`Provider-reported cost: $${s.cost_usd.toFixed(4)} across ${number(s.cost_known_calls)} calls.`:'The provider has not reported a currency cost; no credit or price estimate is invented.';
      foot.textContent=`Tracking began ${data.tracking_started?.slice(0,10)||'with this update'}; earlier usage is unknown. ${coverage} ${s.unattributed_tokens?`${number(s.unattributed_tokens)} tokens are included in the provider total without an input/output breakdown (unclassified). `:''}${cost} Cached input: ${number(s.cached_tokens)}; reasoning output: ${number(s.reasoning_tokens)} (already included, never added twice). Detailed activity expires after 7 days. Daily usage totals remain available. No local STT/TTS/vision tokens are counted.`;
    }
    async function refresh(){
      if(busy)return;busy=true;
      try{const query=new URLSearchParams({period:period.value});if(period.value==='custom'){if(!from.value||!to.value)throw new Error('Choose both From and To dates.');query.set('from',from.value);query.set('to',to.value);}
        const response=await fetch('/api/usage?'+query,{headers:{'X-Brain-Request':'local'}}),data=await response.json();if(!response.ok)throw new Error(data.error||'Usage could not be loaded.');
        if(period.value!=='custom'){from.value=data.from;to.value=data.to;}render(data);
      }catch(error){status.textContent=error.message;}finally{busy=false;}
    }
    period.addEventListener('change',()=>{from.disabled=to.disabled=period.value!=='custom';if(period.value!=='custom')refresh();});
    filters.addEventListener('submit',event=>{event.preventDefault();refresh();});from.disabled=to.disabled=true;
    refresh();const timer=setInterval(()=>{if(!document.hidden && root.offsetParent!==null)refresh();},5000);
    return {refresh,dispose:()=>clearInterval(timer)};
  }
  return {mount};
})();
