"""Replace synthetic records ONLY in the explicitly named isolated evaluation database."""
import json
import os
from pathlib import Path
import psycopg
from oracle import isolated_url

def load(url):
    fixture=json.loads((Path(__file__).parent/'benchmark'/'fixture.json').read_text(encoding='utf-8'))
    with psycopg.connect(isolated_url(url),options='-c search_path=public,extensions') as db:
        db.execute('TRUNCATE reports,hospitals,queue_lengths,users RESTART IDENTITY CASCADE')
        for u in fixture['users']:db.execute('INSERT INTO users(id,display_name) VALUES(%s,%s)',(u['id'],u['name']))
        for q in fixture['queueLengths']:db.execute('INSERT INTO queue_lengths(id,description,colour,sort_order) VALUES(%s,%s,%s,%s)',(q['id'],q['description'],q['colour'],q['sortOrder']))
        for h in fixture['hospitals']:db.execute('INSERT INTO hospitals(id,name,last_inspected,location,user_id) VALUES(%s,%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),4326),%s)',(h['id'],h['name'],h['lastInspected'],h['longitude'],h['latitude'],h['userId']))
        for r in fixture['reports']:db.execute('INSERT INTO reports(id,hospital_id,user_id,queue_length_id,cleanliness,cleanliness_score,queue_wait_minutes,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',(r['id'],r['hospitalId'],r['userId'],r['queueLengthId'],r['cleanliness'],r.get('cleanlinessScore'),r.get('queueWaitMinutes'),r['createdAt']))
        for table in ['users','queue_lengths','hospitals','reports']:
            db.execute(f"SELECT setval(pg_get_serial_sequence('{table}','id'),(SELECT MAX(id) FROM {table}))")
    print('Loaded isolated synthetic fixture: 12 hospitals, '+str(len(fixture['reports']))+' observations')

if __name__=='__main__':load(os.environ['EVAL_ADMIN_DATABASE_URL'])
