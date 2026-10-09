"""CI/local setup. Only the named queuelens_test → queuelens_eval databases."""
import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse
import psycopg
from psycopg import sql
from load_fixture import load
from oracle import isolated_url

def bootstrap():
    test=os.environ['TEST_DATABASE_URL'];admin=isolated_url(os.environ['EVAL_ADMIN_DATABASE_URL'])
    if urlparse(test).path!='/queuelens_test':raise ValueError('Bootstrap requires isolated queuelens_test')
    if urlparse(test).hostname!=urlparse(admin).hostname:raise ValueError('Test and evaluation databases must share the isolated host')
    password=os.environ['EVAL_READER_PASSWORD']
    with psycopg.connect(test,autocommit=True) as db:
        if not db.execute('SELECT 1 FROM pg_database WHERE datname=%s',('queuelens_eval',)).fetchone():db.execute('CREATE DATABASE queuelens_eval')
    root=Path(__file__).resolve().parents[1]
    subprocess.run(['node','scripts/migrate.js'],cwd=root,env={**os.environ,'DATABASE_URL':admin,'DATABASE_SSL':'false'},check=True)
    load(admin)
    with psycopg.connect(admin,autocommit=True) as db:
        if not db.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',('queuelens_eval_reader',)).fetchone():
            db.execute(sql.SQL('CREATE ROLE queuelens_eval_reader LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS').format(sql.Literal(password)))
        db.execute('GRANT CONNECT ON DATABASE queuelens_eval TO queuelens_eval_reader')
        db.execute('GRANT USAGE ON SCHEMA public,extensions TO queuelens_eval_reader')
        db.execute('GRANT SELECT ON hospitals,reports,queue_lengths,hospital_latest_status,hospital_report_details TO queuelens_eval_reader')
        db.execute('ALTER ROLE queuelens_eval_reader IN DATABASE queuelens_eval SET default_transaction_read_only=on')
    print('Isolated evaluation database and read-only role ready')

if __name__=='__main__':bootstrap()
