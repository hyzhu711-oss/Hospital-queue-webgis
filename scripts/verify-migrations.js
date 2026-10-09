"use strict";
// Exercises fresh, repeated and legacy migrations only against disposable test databases.
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const {randomBytes}=require("node:crypto");
const {spawnSync}=require("node:child_process");
const {Client}=require("pg");
async function main(){
  const source=process.env.TEST_DATABASE_URL;
  if(!source || new URL(source).pathname!=="/queuelens_test")throw new Error("TEST_DATABASE_URL must name isolated queuelens_test");
  const settings={connectionString:source,options:"-c search_path=public,extensions"};
  const admin=new Client(settings);await admin.connect();
  const root=path.resolve(__dirname,"..");
  try{
    for(const legacy of [false,true]){
      const name="queuelens_migration_"+randomBytes(8).toString("hex");
      assert.match(name,/^queuelens_migration_[a-f0-9]{16}$/);
      const url=new URL(source);url.pathname="/"+name;
      await admin.query(`CREATE DATABASE ${name}`);
      const db=new Client({...settings,connectionString:String(url)});
      try{
        await db.connect();
        if(legacy){
          for(const file of ["001_init.sql","002_seed.sql"])await db.query(fs.readFileSync(path.join(root,"database","migrations",file),"utf8"));
          await db.query("UPDATE hospitals SET name=$1 WHERE id=1",["Preserved legacy hospital"]);
          await db.query("UPDATE reports SET cleanliness=$1 WHERE id=13",["Preserved legacy observation"]);
        }
        const migrate=()=>{
          const run=spawnSync(process.execPath,[path.join(root,"scripts","migrate.js")],{cwd:root,env:{...process.env,DATABASE_URL:String(url),DATABASE_SSL:"false"},encoding:"utf8"});
          assert.equal(run.status,0,run.stderr);process.stdout.write(run.stdout);
        };
        migrate();
        const before=(await db.query("SELECT (SELECT COUNT(*) FROM hospitals)::int AS hospitals,(SELECT COUNT(*) FROM reports)::int AS reports")).rows[0];
        migrate();
        assert.deepEqual((await db.query("SELECT (SELECT COUNT(*) FROM hospitals)::int AS hospitals,(SELECT COUNT(*) FROM reports)::int AS reports")).rows[0],before);
        assert.equal((await db.query("SELECT COUNT(*)::int AS count FROM schema_migrations")).rows[0].count,3);
        assert.equal((await db.query("SELECT COUNT(*)::int AS count FROM information_schema.columns WHERE table_schema='public' AND table_name='reports' AND column_name IN ('cleanliness_score','queue_wait_minutes')")).rows[0].count,2);
        assert.ok((await db.query("SELECT indexname FROM pg_indexes WHERE tablename='hospitals' AND indexdef ILIKE '%geography%'")).rowCount);
        if(legacy){
          assert.equal((await db.query("SELECT name FROM hospitals WHERE id=1")).rows[0].name,"Preserved legacy hospital");
          assert.equal((await db.query("SELECT cleanliness FROM reports WHERE id=13")).rows[0].cleanliness,"Preserved legacy observation");
        }
        console.log(`${legacy?"Legacy adoption":"Fresh installation"}: migration assertions passed`);
      }finally{
        await db.end();
        // Identifier was generated and restricted above; no caller-supplied database is dropped.
        await admin.query(`DROP DATABASE ${name}`);
      }
    }
  }finally{await admin.end();}
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
