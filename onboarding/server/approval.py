from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from .profile_store import connect

def now(): return datetime.now(timezone.utc).isoformat()

def ensure_schema():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS operator_actions(
          id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id TEXT NOT NULL, action TEXT NOT NULL,
          actor TEXT NOT NULL, note TEXT NOT NULL, previous_hash TEXT NOT NULL, entry_hash TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_operator_actions_profile ON operator_actions(profile_id,id);
        """)

def record(profile_id:str, action:str, actor:str, note:str=''):
    ensure_schema(); t=now()
    with connect() as db:
        row=db.execute('SELECT entry_hash FROM operator_actions WHERE profile_id=? ORDER BY id DESC LIMIT 1',(profile_id,)).fetchone()
        prev=row[0] if row else ''
        canonical=json.dumps({'profile_id':profile_id,'action':action,'actor':actor,'note':note,'previous_hash':prev,'created_at':t},sort_keys=True,separators=(',',':'))
        h=hashlib.sha256(canonical.encode()).hexdigest()
        db.execute('INSERT INTO operator_actions(profile_id,action,actor,note,previous_hash,entry_hash,created_at) VALUES(?,?,?,?,?,?,?)',(profile_id,action,actor,note,prev,h,t))
        return {'action':action,'actor':actor,'note':note,'previous_hash':prev,'entry_hash':h,'created_at':t}

def list_actions(profile_id:str):
    ensure_schema()
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT action,actor,note,previous_hash,entry_hash,created_at FROM operator_actions WHERE profile_id=? ORDER BY id',(profile_id,))]
