import os
import pytest
from baselines.sql_guard import validate_sql,execute_sql
from baselines.sql_projection import project

@pytest.mark.parametrize('sql',[
    'SELECT pg_sleep(100)','SELECT * FROM pg_shadow','SELECT * FROM users',
    'SELECT id INTO stolen FROM hospitals','SELECT id FROM hospitals FOR UPDATE',
    'WITH x AS (DELETE FROM reports RETURNING *) SELECT * FROM x',
    'SELECT id FROM hospitals; DROP TABLE reports','COPY reports TO PROGRAM \'calc\'',
    'SELECT public.st_distance(location,location) FROM hospitals','SELECT id FROM other.hospitals',
    'SELECT pg_read_file(\'secret\')','SELECT 1::regproc','SELECT 1 OPERATOR(pg_catalog.+) 2'
])
def test_reject_unsafe_sql(sql):
    with pytest.raises(Exception):validate_sql(sql)

@pytest.mark.parametrize('sql',[
    'SELECT id AS hospital_id FROM hospitals ORDER BY id LIMIT 3',
    'SELECT hospital_id,AVG(cleanliness_score) FROM reports WHERE created_at>=\'2026-05-01\'::timestamptz GROUP BY hospital_id',
    'SELECT id FROM hospitals WHERE ST_DWithin(location::geography,ST_SetSRID(ST_MakePoint(-0.13,51.5),4326)::geography,2000)',
])
def test_allow_bounded_readonly_select(sql):assert validate_sql(sql)

@pytest.mark.skipif(not os.getenv('EVAL_DATABASE_URL'),reason='Isolated PostGIS evaluation database required')
def test_real_readonly_sql_and_projection():
    url=os.environ['EVAL_DATABASE_URL']
    assert execute_sql(url,'SELECT id AS hospital_id FROM hospitals ORDER BY id LIMIT 2')==[{'hospital_id':1},{'hospital_id':2}]
    entities,stats=project(url,[2,1],{'latitude':51.5,'longitude':-.13},'2026-05-31T12:00:00Z','2026-06-01T12:00:00Z',True)
    assert [h['hospital_id'] for h in entities]==[2,1]
    assert stats[0]['report_count']==2 and stats[0]['average_cleanliness']==4.5
    assert stats[0]['report_ids']==[2,3]
