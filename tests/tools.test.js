"use strict";
const request=require("supertest");
const {createApp}=require("../src/app");
const {createMemoryStore}=require("../src/store/memoryStore");
const {createPostgresStore}=require("../src/store/postgresStore");
const {executeTool,catalog}=require("../src/tools/service");
const demo=require("../src/data/demoData");
const window={start_time:"2026-05-29T00:00:00Z",end_time:"2026-05-30T00:00:00Z"};
function fixture(){
  return {...demo,reports:[
    {id:1,hospitalId:1,userId:1,queueLengthId:2,cleanliness:"explicit score",cleanlinessScore:4,queueWaitMinutes:0,createdAt:window.start_time},
    {id:2,hospitalId:1,userId:1,queueLengthId:4,cleanliness:"explicit score",cleanlinessScore:5,queueWaitMinutes:20,createdAt:"2026-05-29T12:00:00Z"},
    {id:3,hospitalId:1,userId:1,queueLengthId:6,cleanliness:"outside window",cleanlinessScore:1,queueWaitMinutes:90,createdAt:window.end_time},
    {id:4,hospitalId:2,userId:1,queueLengthId:1,cleanliness:"unknown queue and no score",createdAt:"2026-05-29T12:00:00Z"},
    {id:5,hospitalId:3,userId:1,queueLengthId:3,cleanliness:"explicit score",cleanlinessScore:3,createdAt:"2026-05-29T12:00:00Z"}
  ]};
}
describe("typed GIS tools",()=>{
  test("catalog has exactly eight strict schemas",()=>{
    expect(catalog().tools).toHaveLength(8);
    for(const tool of catalog().tools)expect(tool.input_schema.additionalProperties).toBe(false);
  });
  test.each([
    ["search_nearby_hospitals",{latitude:"51",longitude:0}],
    ["search_nearby_hospitals",{latitude:91,longitude:0}],
    ["search_nearby_hospitals",{latitude:0,longitude:0,radius_m:-1}],
    ["search_nearby_hospitals",{latitude:0,longitude:0,sql:"SELECT 1"}],
    ["get_hospital_details",{hospital_id:true}],
    ["get_hospital_details",{hospital_id:"1abc"}],
    ["get_queue_statistics",{hospital_id:1,...window,start_time:"2026-05-29T00:00:00"}],
    ["get_queue_statistics",{hospital_id:1,...window,start_time:"2026-02-30T00:00:00Z"}],
    ["get_queue_statistics",{hospital_id:1,...window,end_time:window.start_time}],
    ["compare_hospitals",{hospital_ids:[1,1],...window}]
  ])("rejects invalid %s arguments",async(name,args)=>{await expect(executeTool(createMemoryStore(),name,args)).rejects.toHaveProperty("status",400);});
  test("radius uses raw metres and nearest order is stable",async()=>{
    const store=createMemoryStore();
    const all=await executeTool(store,"search_nearby_hospitals",{latitude:51.5246,longitude:-0.1347});
    expect(all.data.hospitals[0].hospital_id).toBe(1);
    const boundary=all.data.hospitals[1].distance_m;
    const inside=await executeTool(store,"search_nearby_hospitals",{latitude:51.5246,longitude:-0.1347,radius_m:boundary});
    const outside=await executeTool(store,"search_nearby_hospitals",{latitude:51.5246,longitude:-0.1347,radius_m:boundary-0.001});
    expect(inside.data.hospitals).toHaveLength(2);expect(outside.data.hospitals).toHaveLength(1);
    expect(all.evidence.data_source).toBe("memory");
  });
  test("truncated candidates are explicit",async()=>{
    const result=await executeTool(createMemoryStore(),"search_nearby_hospitals",{latitude:51.5,longitude:0,limit:1});
    expect(result.data.complete).toBe(false);
  });
  test("resolution handles exact name, ambiguity and injection as literal data",async()=>{
    const store=createMemoryStore();
    expect((await executeTool(store,"resolve_hospitals",{query:"Bloomsbury Community Hospital"})).data.hospitals).toHaveLength(1);
    expect((await executeTool(store,"resolve_hospitals",{query:"Hospital"})).data.hospitals.length).toBeGreaterThan(1);
    expect((await executeTool(store,"resolve_hospitals",{query:"' OR 1=1 --"})).data.hospitals).toEqual([]);
  });
  test("nonexistent entity is not confused with no reports",async()=>{
    await expect(executeTool(createMemoryStore(),"get_hospital_details",{hospital_id:999})).rejects.toHaveProperty("status",404);
    const result=await executeTool(createMemoryStore(),"get_hospital_reports",{hospital_id:8,...window});
    expect(result.data.reports).toEqual([]);
  });
  test("half-open statistics retain evidence and separate severity from observed minutes",async()=>{
    const store=createMemoryStore(fixture());
    const queue=await executeTool(store,"get_queue_statistics",{hospital_id:1,...window});
    expect(queue.data).toMatchObject({report_count:2,average_queue_severity:2,average_wait_minutes:10,report_ids:[1,2],average_cleanliness:4.5});
    const clean=await executeTool(store,"get_cleanliness_statistics",{hospital_id:2,...window});
    expect(clean.data).toMatchObject({known_queue_count:0,average_queue_severity:null,average_cleanliness:null});
    expect((await executeTool(store,"get_hospital_reports",{hospital_id:1,...window})).data.reports.map(r=>r.report_id)).toEqual([2,1]);
  });
  test("comparison batches the exact requested IDs",async()=>{
    const result=await executeTool(createMemoryStore(fixture()),"compare_hospitals",{hospital_ids:[1,2],...window});
    expect(result.data.statistics.map(s=>s.hospital_id)).toEqual([1,2]);
  });
  test("ranking excludes missing metrics, enforces filters and validates weights",async()=>{
    const args={candidate_ids:[1,2,3],latitude:51.5246,longitude:-0.1347,...window,distance_weight:0,queue_weight:1,cleanliness_weight:0,min_cleanliness:4,limit:3};
    const result=await executeTool(createMemoryStore(fixture()),"rank_hospitals",args);
    expect(result.data.ranking.map(r=>r.hospital_id)).toEqual([1]);
    expect(result.data.excluded_ids).toEqual([2,3]);
    await expect(executeTool(createMemoryStore(),"rank_hospitals",{...args,queue_weight:0.5})).rejects.toHaveProperty("code","invalid_weights");
  });
  test("SQL binds name and coordinate values; no query injection",async()=>{
    const pool={query:jest.fn().mockResolvedValue({rows:[]})};
    const store=createPostgresStore({pool});
    await store.toolResolveHospitals("x' OR 1=1 --");
    const [sql,values]=pool.query.mock.calls[0];expect(sql).not.toContain("x'");expect(values[0]).toBe("x' OR 1=1 --");
    await store.toolSearchHospitals({latitude:51.5,longitude:-0.1,radius_m:2000,limit:201});
    expect(pool.query.mock.calls[1][1]).toEqual([2000,-0.1,51.5,201]);expect(pool.query.mock.calls[1][0]).toContain("ST_DWithin");
  });
  test("API routing, unknown tool and legacy strict fixes",async()=>{
    const app=createApp({store:createMemoryStore()});
    await request(app).get("/api/tools/catalog").expect(200);
    await request(app).post("/api/tools/get_hospital_details").send({hospital_id:1}).expect(200);
    await request(app).post("/api/tools/execute_sql").send({}).expect(404);
    await request(app).get("/api/hospitals/nearest?lat=&lon=").expect(400);
    await request(app).get("/api/hospitals/1abc/reports").expect(400);
    await request(app).get("/api/user?userId=999").expect(404);
    expect((await request(app).get("/api/users/3/activity")).body.rank).toBe(2);
  });
  test("token-protected tool catalog",async()=>{
    const previous=process.env.GIS_TOOLS_TOKEN;process.env.GIS_TOOLS_TOKEN="test-token";
    try { const app=createApp({store:createMemoryStore()});await request(app).get("/api/tools/catalog").expect(401);await request(app).get("/api/tools/catalog").set("Authorization","Bearer test-token").expect(200); }
    finally { if(previous===undefined)delete process.env.GIS_TOOLS_TOKEN;else process.env.GIS_TOOLS_TOKEN=previous; }
  });
});
