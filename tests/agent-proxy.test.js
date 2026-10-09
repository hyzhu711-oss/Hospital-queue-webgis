"use strict";
const http=require("node:http");
const request=require("supertest");
const {createApp}=require("../src/app");
const {createMemoryStore}=require("../src/store/memoryStore");
describe("optional same-origin Agent proxy",()=>{
  let upstream,base,seen;
  const saved={url:process.env.AGENT_SERVICE_URL,token:process.env.AGENT_API_TOKEN};
  beforeAll(done=>{
    upstream=http.createServer((req,res)=>{
      seen={path:req.url,token:req.headers.authorization};
      if(req.url==="/query/stream"){
        res.writeHead(200,{"Content-Type":"text/event-stream"});res.end('event: done\ndata: {"status":"ok","answer":"grounded"}\n\n');
      }else{res.writeHead(422,{"Content-Type":"application/json"});res.end(JSON.stringify({error:"invalid input"}));}
    }).listen(0,"127.0.0.1",()=>{base=`http://127.0.0.1:${upstream.address().port}`;done();});
  });
  afterAll(done=>{
    if(saved.url===undefined)delete process.env.AGENT_SERVICE_URL;else process.env.AGENT_SERVICE_URL=saved.url;
    if(saved.token===undefined)delete process.env.AGENT_API_TOKEN;else process.env.AGENT_API_TOKEN=saved.token;
    upstream.close(done);
  });
  const app=()=>createApp({store:createMemoryStore()});
  test("disabled Agent preserves ordinary WebGIS",async()=>{
    delete process.env.AGENT_SERVICE_URL;
    expect((await request(app()).get("/api/agent/config")).body).toEqual({enabled:false});
    expect((await request(app()).post("/api/agent/query").send({query:"nearest"})).status).toBe(503);
    expect((await request(app()).get("/api/health")).status).toBe(200);
  });
  test("server token stays in upstream header; validation status is retained",async()=>{
    process.env.AGENT_SERVICE_URL=base;process.env.AGENT_API_TOKEN="test-server-only-token";
    const response=await request(app()).post("/api/agent/query").send({query:""});
    expect(response.status).toBe(422);expect(seen.token).toBe("Bearer test-server-only-token");
    expect(JSON.stringify(response.body)).not.toContain("test-server-only-token");
    expect((await request(app()).get("/api/agent/config")).body).toEqual({enabled:true});
  });
  test("SSE events pass through with buffering disabled",async()=>{
    process.env.AGENT_SERVICE_URL=base;
    const response=await request(app()).post("/api/agent/query/stream").send({query:"nearest"});
    expect(response.status).toBe(200);expect(response.headers["x-accel-buffering"]).toBe("no");
    expect(response.text).toContain("event: done");expect(seen.path).toBe("/query/stream");
  });
});
