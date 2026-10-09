"use strict";
const {Pool}=require("pg");
const {createPostgresStore}=require("../src/store/postgresStore");
const {executeTool}=require("../src/tools/service");
const connectionString=process.env.TEST_DATABASE_URL;
const databaseSuite=connectionString?describe:describe.skip;
databaseSuite("real PostGIS GIS tools (isolated queuelens_test only)",()=>{
  let pool,store;
  beforeAll(async()=>{
    if(new URL(connectionString).pathname!=="/queuelens_test")throw new Error("Tests require isolated database named queuelens_test");
    pool=new Pool({connectionString,options:"-c search_path=public,extensions -c statement_timeout=5000"});
    store=createPostgresStore({pool});await store.healthCheck();
  });
  afterAll(async()=>{if(pool)await pool.end();});
  test("PostGIS computes nearest and radius in metres",async()=>{
    const result=await executeTool(store,"search_nearby_hospitals",{latitude:51.5246,longitude:-0.1347,radius_m:1000});
    expect(result.evidence.data_source).toBe("postgres");expect(result.data.hospitals[0].hospital_id).toBe(1);expect(result.data.hospitals[0].distance_m).toBe(0);
    expect(result.data.hospitals.every(h=>h.distance_m<=1000)).toBe(true);
  });
  test("real SQL time window aggregates raw report evidence",async()=>{
    const args={hospital_id:1,start_time:"2026-05-29T00:00:00Z",end_time:"2026-05-30T00:00:00Z"};
    const result=await executeTool(store,"get_queue_statistics",args);
    expect(result.data).toMatchObject({report_count:1,average_queue_severity:1,report_ids:[13],average_cleanliness:null});
    expect((await executeTool(store,"get_hospital_reports",args)).data.reports).toHaveLength(1);
  });
  test("literal injection cannot expand results; no-score ranking cannot fabricate candidates",async()=>{
    expect((await executeTool(store,"resolve_hospitals",{query:"' OR 1=1 --"})).data.hospitals).toHaveLength(0);
    const result=await executeTool(store,"rank_hospitals",{candidate_ids:[1,2,3],latitude:51.52,longitude:-0.13,start_time:"2026-05-18T00:00:00Z",end_time:"2026-05-30T00:00:00Z",distance_weight:0,queue_weight:0,cleanliness_weight:1});
    expect(result.data.ranking).toHaveLength(0);
  });
});
