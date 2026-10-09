"use strict";
const express=require("express");
const {Readable}=require("stream");
function createAgentRouter(){
  const router=express.Router();
  router.get("/config",(req,res)=>res.json({enabled:Boolean(process.env.AGENT_SERVICE_URL)}));
  const proxy=async(req,res)=>{
    if(!process.env.AGENT_SERVICE_URL)return res.status(503).json({error:"QueueLens Agent is not configured"});
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),35000);
    res.on("close",()=>{controller.abort();clearTimeout(timer);});
    try{
      const base=new URL(process.env.AGENT_SERVICE_URL);
      if(!["http:","https:"].includes(base.protocol))throw new Error("Unsupported Agent URL");
      const url=process.env.AGENT_SERVICE_URL.replace(/\/$/,"")+(req.path.endsWith("/stream")?"/query/stream":"/query");
      const token=process.env.AGENT_API_TOKEN;
      const upstream=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json",...(token?{Authorization:`Bearer ${token}`}:{})},body:JSON.stringify(req.body),signal:controller.signal,redirect:"error"});
      res.status(upstream.status).set("Content-Type",upstream.headers.get("content-type")||"application/json").set("Cache-Control","no-cache");
      if(req.path.endsWith("/stream"))res.set("X-Accel-Buffering","no");
      if(upstream.body){const stream=Readable.fromWeb(upstream.body);stream.on("error",()=>{if(!res.destroyed)res.destroy();});res.on("finish",()=>clearTimeout(timer));stream.pipe(res);}
      else{clearTimeout(timer);res.end();}
    }catch(error){clearTimeout(timer);if(!res.headersSent)res.status(502).json({error:"QueueLens Agent is unavailable"});}
  };
  router.post("/query",proxy);router.post("/query/stream",proxy);
  return router;
}
module.exports={createAgentRouter};
