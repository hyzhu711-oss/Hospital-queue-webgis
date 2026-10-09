"use strict";
const {createApp}=require("../src/app");
const {createMemoryStore}=require("../src/store/memoryStore");
const {createPostgresStore}=require("../src/store/postgresStore");
const fixture=require("./benchmark/fixture.json");
let store;
if(process.env.EVAL_STORE==="postgres"){
  if(!process.env.EVAL_DATABASE_URL || new URL(process.env.EVAL_DATABASE_URL).pathname!=="/queuelens_eval")throw new Error("Evaluation requires isolated queuelens_eval");
  process.env.DATABASE_URL=process.env.EVAL_DATABASE_URL;process.env.DATABASE_SSL="false";
  store=createPostgresStore();
}else store=createMemoryStore(fixture);
process.env.GIS_TOOLS_TOKEN="";delete process.env.AGENT_SERVICE_URL;
const server=createApp({store}).listen(0,"127.0.0.1",()=>console.log("http://127.0.0.1:"+server.address().port));
process.on("SIGTERM",()=>server.close(async()=>{if(store.close)await store.close();process.exit(0)}));
