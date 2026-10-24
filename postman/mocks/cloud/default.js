// Contract-derived fixture, not a language model. It chooses deterministic
// tools so the production client, agent and local tools run over real HTTP.
const http=require('http');
http.createServer((req,res)=>{
 let body='';req.on('data',chunk=>body+=chunk);req.on('end',()=>{
  const url=new URL(req.url,'http://localhost');
  if(!['/chat/completions','/messages'].includes(url.pathname)){res.writeHead(501);return res.end('Unmodeled endpoint');}
  const anthropic=url.pathname==='/messages';
  if((anthropic?req.headers['x-api-key']:req.headers.authorization)!==(anthropic?'fixture-key':'Bearer fixture-key')){res.writeHead(401);return res.end('{}');}
  let data;try{data=JSON.parse(body);}catch{res.writeHead(400);return res.end('{}');}
  const user=data.messages.find(m=>m.role==='user');
  const text=typeof user.content==='string'?user.content:JSON.stringify(user.content);
  const responses=[];
  for(const message of data.messages){
    if(message.role==='tool')responses.push(JSON.parse(message.content));
    if(message.role==='user' && Array.isArray(message.content))for(const block of message.content)if(block.type==='tool_result')responses.push(JSON.parse(block.content));
  }
  let calls=[];
  const make=(name,args)=>({id:'call_'+responses.length+'_'+calls.length,name,arguments:args});
  if(text.includes('invalid-arguments') && !responses.length)calls.push(make('read_file',{wrong:'bad'}));
  else if(text.includes('invalid-arguments'))calls.push(make('finish',{text:'The invalid tool was rejected and reported correctly.',emotion:'concerned'}));
  else if(text.includes('record-work') && !responses.length)calls.push(make('add_task',{title:'Implemented cloud agent',date:'2026-01-05',status:'done'}));
  else if(text.includes('recall-work') && !responses.length)calls.push(make('list_tasks',{date:'2026-01-05'}));
  else if(text.includes('record-work')||text.includes('recall-work'))calls.push(make('finish',{text:JSON.stringify(responses[0].result),emotion:'happy',gesture:'nod'}));
  else if(!responses.length){
    const folder=text.match(/folder=(.+)/)?.[1];
    calls.push(make('list_files',{path:folder}));
  }else if(responses.length===1 && responses[0].ok){
    for(const item of responses[0].result.items)calls.push(make('read_file',{path:item.path}));
  }else {
    const contents=responses.slice(1).filter(r=>r.ok).map(r=>r.result.text).join(' ');
    calls.push(make('finish',{text:'Verified folder summary: '+contents,emotion:'happy',gesture:'nod'}));
  }
  let output;
  if(anthropic)output={id:'msg_fixture',type:'message',role:'assistant',model:data.model,stop_reason:'tool_use',content:calls.map(c=>({type:'tool_use',id:c.id,name:c.name,input:c.arguments})),usage:{input_tokens:1,output_tokens:1}};
  else output={id:'chat_fixture',object:'chat.completion',choices:[{finish_reason:'tool_calls',message:{role:'assistant',content:null,tool_calls:calls.map(c=>({type:'function',id:c.id,function:{name:c.name,arguments:JSON.stringify(c.arguments)}}))}}]};
  res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify(output));
 });
}).listen(process.env.PORT||4501);
