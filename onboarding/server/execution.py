from __future__ import annotations
import hashlib, json, uuid
from datetime import datetime, timezone
from .profile_store import connect
from .workspace import write_json

def now(): return datetime.now(timezone.utc).isoformat()

def ensure_schema():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS execution_approvals(
          id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id TEXT NOT NULL, actor TEXT NOT NULL, note TEXT NOT NULL,
          scope_json TEXT NOT NULL, previous_hash TEXT NOT NULL, entry_hash TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS execution_steps(
          step_id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, step_type TEXT NOT NULL, status TEXT NOT NULL,
          scope_json TEXT NOT NULL, requires_human INTEGER NOT NULL DEFAULT 0, result_json TEXT, error TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(profile_id,step_type)
        );
        """)

def approve(profile_id:str, actor:str, note:str, scope:list[str]):
    ensure_schema(); t=now()
    with connect() as db:
        row=db.execute('SELECT entry_hash FROM execution_approvals WHERE profile_id=? ORDER BY id DESC LIMIT 1',(profile_id,)).fetchone()
        prev=row[0] if row else ''
        canonical=json.dumps({'profile_id':profile_id,'actor':actor,'note':note,'scope':scope,'previous_hash':prev,'created_at':t},sort_keys=True,separators=(',',':'))
        h=hashlib.sha256(canonical.encode()).hexdigest()
        db.execute('INSERT INTO execution_approvals(profile_id,actor,note,scope_json,previous_hash,entry_hash,created_at) VALUES(?,?,?,?,?,?,?)',(profile_id,actor,note,json.dumps(scope),prev,h,t))
    return {'actor':actor,'note':note,'scope':scope,'previous_hash':prev,'entry_hash':h,'created_at':t}

def seed_steps(profile_id:str):
    ensure_schema(); t=now()
    steps=[('workspace_prepare',False),('infrastructure_provision',True),('branding_apply',False),('integration_connect',True),('platform_configure',False),('deployment_smoke_test',False),('rollback_verify',False),('client_acceptance',True)]
    with connect() as db:
        for typ,human in steps:
            sid='exec_'+uuid.uuid4().hex[:16]
            try: db.execute('INSERT INTO execution_steps(step_id,profile_id,step_type,status,scope_json,requires_human,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(sid,profile_id,typ,'pending','{}',1 if human else 0,t,t))
            except Exception: pass
    return list_steps(profile_id)

def list_steps(profile_id:str):
    ensure_schema()
    with connect() as db: return [dict(r) for r in db.execute('SELECT step_id,step_type,status,requires_human,result_json,error,created_at,updated_at FROM execution_steps WHERE profile_id=? ORDER BY rowid',(profile_id,))]

def set_step(profile_id:str, step_type:str, status:str, result:dict|None=None, error:str|None=None):
    ensure_schema(); t=now()
    with connect() as db:
        db.execute('UPDATE execution_steps SET status=?,result_json=?,error=?,updated_at=? WHERE profile_id=? AND step_type=?',(status,json.dumps(result) if result is not None else None,error,t,profile_id,step_type))
        db.execute('INSERT INTO events(profile_id,event_type,body_json,created_at) VALUES(?,?,?,?)',(profile_id,'execution_step_'+status,json.dumps({'step_type':step_type,'result':result,'error':error}),t))
    if result is not None: write_json(profile_id,f'execution/{step_type}.json',result)

def approvals(profile_id:str):
    ensure_schema()
    with connect() as db: return [dict(r) for r in db.execute('SELECT actor,note,scope_json,previous_hash,entry_hash,created_at FROM execution_approvals WHERE profile_id=? ORDER BY id',(profile_id,))]
