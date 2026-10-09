"""An AST allowlist plus an isolated read-only database role. Never a production API."""
from urllib.parse import urlparse
import psycopg
from pglast import ast,parse_sql
from pglast.visitors import Visitor
from psycopg.rows import dict_row

TABLES={'hospitals','reports','queue_lengths','hospital_latest_status','hospital_report_details'}
FUNCTIONS={'st_distance','st_dwithin','st_setsrid','st_makepoint','st_x','st_y','avg','count','min','max','sum','round','abs','least','greatest','array_agg','coalesce','nullif','date_trunc'}
TYPES={'geometry','geography','int4','int8','integer','bigint','float8','float4','numeric','text','timestamptz','timestamp','interval','bool'}
NODE_TYPES={'RawStmt','SelectStmt','ResTarget','RangeVar','RangeSubselect','JoinExpr','Alias','ColumnRef','A_Star','A_Expr','A_Const','Integer','Float','String','Boolean','BoolExpr','NullTest','BooleanTest','FuncCall','TypeCast','TypeName','SortBy','CaseExpr','CaseWhen','CoalesceExpr','MinMaxExpr','RowExpr','A_ArrayExpr','SubLink','SQLValueFunction','WindowDef'}

class Allowlist(Visitor):
    def visit(self,ancestors,node):
        kind=type(node).__name__
        if kind not in NODE_TYPES:raise ValueError('SQL node is not allowed: '+kind)
        if isinstance(node,ast.SelectStmt) and (node.intoClause or node.lockingClause or node.withClause):raise ValueError('SELECT INTO, locks and CTEs are disabled')
        if isinstance(node,ast.RangeVar) and (node.relname not in TABLES or node.schemaname not in (None,'public') or node.catalogname):raise ValueError('Table is outside the benchmark allowlist')
        if isinstance(node,ast.FuncCall):
            name=[p.sval.lower() for p in node.funcname]
            if len(name)>2 or name[-1] not in FUNCTIONS or (len(name)==2 and name[0] not in ('extensions','pg_catalog')):raise ValueError('Function is not allowed')
        if isinstance(node,ast.TypeName):
            name=[p.sval.lower() for p in node.names]
            if name[-1] not in TYPES or len(name)>2 or (len(name)==2 and name[0] not in ('pg_catalog','extensions')):raise ValueError('Type is not allowed')
        if isinstance(node,ast.A_Expr) and any(p.sval not in ('=','<>','!=','<','>','<=','>=','+','-','*','/','~~','~~*','!~~','!~~*') for p in node.name):raise ValueError('Operator is not allowed')

def validate_sql(sql):
    if not isinstance(sql,str) or not sql.strip() or len(sql)>10000:raise ValueError('SQL length is invalid')
    parsed=parse_sql(sql)
    if len(parsed)!=1 or not isinstance(parsed[0].stmt,ast.SelectStmt):raise ValueError('Exactly one SELECT is required')
    Allowlist()(parsed)
    return sql.rstrip().rstrip(';')

def connect_readonly(url):
    if urlparse(url).path!='/queuelens_eval':raise ValueError('Text-to-SQL requires isolated queuelens_eval')
    db=psycopg.connect(url,row_factory=dict_row,options='-c search_path=public,extensions -c default_transaction_read_only=on -c statement_timeout=3000 -c lock_timeout=1000',connect_timeout=5)
    role=db.execute('SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()
    if any(role.values()):db.close();raise ValueError('Text-to-SQL rejects privileged roles')
    writes=db.execute("SELECT has_table_privilege(current_user,'hospitals','INSERT,UPDATE,DELETE,TRUNCATE') AS hospitals,has_table_privilege(current_user,'reports','INSERT,UPDATE,DELETE,TRUNCATE') AS reports").fetchone()
    if any(writes.values()):db.close();raise ValueError('Text-to-SQL requires a role without write privileges')
    return db

def execute_sql(url,sql):
    safe=validate_sql(sql)
    with connect_readonly(url) as db:
        # Validated SELECT is wrapped, row-capped and time-capped; never arbitrary SQL.
        rows=db.execute('SELECT * FROM ('+safe+') AS baseline_result LIMIT 201').fetchall()
        if len(rows)>200:raise ValueError('SQL returned more than 200 rows')
        return rows
