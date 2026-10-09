import json
import os
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def node_service(tmp_path_factory):
    seed_path=tmp_path_factory.mktemp("gis")/"seed.json"
    fixture={"users":[{"id":1,"name":"Test contributor"}],
             "queueLengths":[{"id":1,"description":"Unknown","colour":"#888888","sortOrder":0},
                             {"id":2,"description":"No queue","colour":"#008800","sortOrder":1},
                             {"id":3,"description":"15-30 minutes","colour":"#cc8800","sortOrder":3}],
             "hospitals":[{"id":i,"name":f"Hospital {chr(64+i)}","lastInspected":"2026-05-01","latitude":51.5+i*0.001,"longitude":-0.13,"userId":1} for i in range(1,5)],
             "reports":[{"id":i,"hospitalId":i,"userId":1,"queueLengthId":2 if i<3 else 3,
                         "cleanliness":"Synthetic explicitly rated fixture","cleanlinessScore":float(6-i) if i<4 else None,
                         "queueWaitMinutes":float(i*5),"createdAt":"2026-05-29T12:00:00Z"} for i in range(1,5)]}
    seed_path.write_text(json.dumps(fixture),encoding="utf8")
    script="const {createApp}=require('./src/app');const {createMemoryStore}=require('./src/store/memoryStore');const seed=require(process.argv[1]);const server=createApp({store:createMemoryStore(seed)}).listen(0,'127.0.0.1',()=>console.log('http://127.0.0.1:'+server.address().port));"
    env={**os.environ,"GIS_TOOLS_TOKEN":""}
    process=subprocess.Popen([shutil.which("node"),"-e",script,str(seed_path)],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        url=process.stdout.readline().strip()
        if not url.startswith("http://127.0.0.1:"):
            process.wait(timeout=5)
            raise AssertionError(process.stderr.read())
        yield url
    finally:
        process.terminate()
        process.communicate(timeout=10)
