"""Fixed read-only formatting queries after model SQL has selected and ordered IDs.

No semantic selection, filtering, ranking or verification happens here.
"""
from .sql_guard import connect_readonly

def project(url,ids,location,start,end,include_statistics):
    if len(ids)>200 or len(ids)!=len(set(ids)) or any(type(i) is not int or not 0<i<=2147483647 for i in ids):raise ValueError('Invalid hospital ID projection')
    with connect_readonly(url) as db:
        rows=db.execute('''SELECT h.id AS hospital_id,h.name,ST_Y(h.location) AS latitude,ST_X(h.location) AS longitude,
            CASE WHEN %s::double precision IS NULL THEN NULL ELSE ST_Distance(h.location::geography,ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography) END AS distance_m,
            COALESCE(q.description,'Unknown') AS queue_description,COALESCE(r.cleanliness,'No report yet') AS cleanliness_note,
            r.id AS latest_report_id,r.created_at AS latest_report_at,r.cleanliness_score,r.queue_wait_minutes
            FROM hospitals h LEFT JOIN LATERAL(SELECT * FROM reports WHERE hospital_id=h.id ORDER BY created_at DESC,id DESC LIMIT 1) r ON TRUE
            LEFT JOIN queue_lengths q ON q.id=r.queue_length_id WHERE h.id=ANY(%s)''',
            (location['latitude'] if location else None,location['longitude'] if location else None,location['latitude'] if location else None,ids)).fetchall()
        byid={r['hospital_id']:r for r in rows}
        if len(byid)!=len(ids):raise ValueError('SQL returned inconsistent hospital IDs')
        entities=[byid[i] for i in ids]
        for h in entities:
            if h['latest_report_at']:h['latest_report_at']=h['latest_report_at'].isoformat(timespec='milliseconds').replace('+00:00','Z')
        stats=[]
        if include_statistics:
            stats=db.execute('''SELECT h.id AS hospital_id,COUNT(r.id)::int AS report_count,
                COUNT(r.id) FILTER(WHERE q.sort_order>0)::int AS known_queue_count,AVG(q.sort_order) FILTER(WHERE q.sort_order>0) AS average_queue_severity,
                COUNT(r.queue_wait_minutes)::int AS observed_wait_count,AVG(r.queue_wait_minutes) AS average_wait_minutes,
                COUNT(r.cleanliness_score)::int AS cleanliness_count,AVG(r.cleanliness_score) AS average_cleanliness,MIN(r.cleanliness_score) AS min_cleanliness,MAX(r.cleanliness_score) AS max_cleanliness,
                MIN(r.created_at) AS first_report_at,MAX(r.created_at) AS last_report_at,
                (array_agg(NULLIF(q.sort_order,0) ORDER BY r.created_at,r.id))[1] AS first_queue_severity,(array_agg(NULLIF(q.sort_order,0) ORDER BY r.created_at DESC,r.id DESC))[1] AS last_queue_severity,
                (array_agg(r.id ORDER BY r.created_at,r.id) FILTER(WHERE r.id IS NOT NULL))[1:200] AS report_ids,COUNT(r.id)<=200 AS report_ids_complete
                FROM hospitals h LEFT JOIN reports r ON r.hospital_id=h.id AND r.created_at>=%s::timestamptz AND r.created_at<%s::timestamptz
                LEFT JOIN queue_lengths q ON q.id=r.queue_length_id WHERE h.id=ANY(%s) GROUP BY h.id ORDER BY h.id''',(start,end,ids)).fetchall()
            for s in stats:
                for field in ('average_queue_severity','average_wait_minutes','average_cleanliness','min_cleanliness','max_cleanliness'):
                    if s[field] is not None:s[field]=float(s[field])
                for field in ('first_report_at','last_report_at'):
                    if s[field]:s[field]=s[field].isoformat(timespec='milliseconds').replace('+00:00','Z')
                s['report_ids']=s['report_ids'] or []
        return entities,stats
