"use strict";
(function(root){
  async function initialise({host,adapter,getLocation}){
    if(!host)return;
    try{const config=await fetch("/api/agent/config").then(r=>r.json());if(!config.enabled)return;}catch(_){return;}
    host.hidden=false;
    const form=document.createElement("form"),label=document.createElement("label"),input=document.createElement("textarea"),button=document.createElement("button");
    label.textContent="Ask QueueLens Agent";input.required=true;input.maxLength=4000;input.rows=3;input.placeholder='例如：2km 内清洁度最高的医院？或查询完整医院名称';input.setAttribute("aria-label","Spatial question");
    const locate=document.createElement("button");locate.type="button";locate.className="command-button";locate.textContent="Use my location";let location=null,locationAt=0;
    locate.addEventListener("click",()=>{if(!navigator.geolocation){status.textContent="Geolocation is unavailable";return;}navigator.geolocation.getCurrentPosition(position=>{location={latitude:position.coords.latitude,longitude:position.coords.longitude};locationAt=Date.now();status.textContent="Location ready for nearby queries.";},()=>{status.textContent="Location permission is required for nearby queries.";},{timeout:10000,maximumAge:30000});});
    button.type="submit";button.className="primary-button full-width";button.textContent="Ask Agent";label.append(input);form.append(label,button,locate);
    const status=document.createElement("p"),answer=document.createElement("p"),details=document.createElement("details"),summary=document.createElement("summary"),trace=document.createElement("pre");
    status.setAttribute("role","status");answer.className="agent-answer";summary.textContent="Execution evidence";details.append(summary,trace);host.append(form,status,answer,details);
    let sessionId=sessionStorage.getItem("queuelens.session");
    async function display(result){
      answer.textContent=result.answer;status.textContent=[result.status,...(result.warnings||[])].join(" · ");
      trace.textContent=JSON.stringify({plan:result.plan,verification:result.verification,trace:result.trace},null,2);
      if(result.session_id){sessionId=result.session_id;sessionStorage.setItem("queuelens.session",sessionId);}
      if(result.status==="stale_session"){sessionId=null;sessionStorage.removeItem("queuelens.session");}
      if(result.status==="ok"){
        await root.QueueLensMapActions.applyActions(result.map_actions,result.entities,adapter);
      }
    }
    // Re-query facts after navigation; retain only the opaque server session for referents.
    sessionStorage.removeItem("queuelens.mapResult");
    form.addEventListener("submit",async event=>{
      event.preventDefault();button.disabled=true;status.textContent="Planning…";
      try{
        const response=await fetch("/api/agent/query/stream",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query:input.value,location:(Date.now()-locationAt<300000?location:null)||getLocation()||null,...(sessionId?{session_id:sessionId}:{})})});
        if(!response.ok)throw new Error(`Agent request failed (${response.status})`);
        const reader=response.body.getReader(),decoder=new TextDecoder();let buffer="",done=false;
        while(!done){
          const chunk=await reader.read();done=chunk.done;buffer+=decoder.decode(chunk.value||new Uint8Array(),{stream:!done});buffer=buffer.replace(/\r\n/g,"\n");
          if(buffer.length>10000000)throw new Error("Agent response exceeds display limit");
          let separator;
          while((separator=buffer.indexOf("\n\n"))>=0){
            const block=buffer.slice(0,separator);buffer=buffer.slice(separator+2);
            const eventLine=block.split("\n").find(line=>line.startsWith("event: ")),dataLine=block.split("\n").find(line=>line.startsWith("data: "));
            if(!eventLine||!dataLine)continue;
            const name=eventLine.slice(7),data=JSON.parse(dataLine.slice(6));
            if(name==="done")await display(data);else status.textContent=({planning:"Planning…",executing:"Querying hospital data…",verifying:"Checking results…",responding:"Preparing answer…",tool_start:"Querying hospital data…",tool_result:"Hospital data received…"})[name]||name;
          }
        }
      }catch(error){status.textContent=error.message;}finally{button.disabled=false;}
    });
  }
  root.QueueLensAgentUI={initialise};
})(window);
