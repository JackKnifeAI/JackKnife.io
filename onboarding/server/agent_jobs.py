from __future__ import annotations
import json, sqlite3, uuid
from datetime import datetime, timezone
from .profile_store import connect

def now(): return datetime.now(timezone.utc).isoformat()

def ensure_schema():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS agent_jobs(
          job_id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, agent_type TEXT NOT NULL,
          trigger_event TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
          input_json TEXT NOT NULL, output_json TEXT, error TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          UNIQUE(profile_id,agent_type,trigger_event)
        );
        ''')

def enqueue(profile_id:str, agent_type:str, trigger_event:str, payload:dict):
    ensure_schema(); jid='job_'+uuid.uuid4().hex[:16]; t=now()
    with connect() as db:
        try:
            db.execute('INSERT INTO agent_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)',
              (jid,profile_id,agent_type,trigger_event,'queued',0,json.dumps(payload),None,None,t,t))
        except sqlite3.IntegrityError:
            row=db.execute('SELECT job_id FROM agent_jobs WHERE profile_id=? AND agent_type=? AND trigger_event=?',
                           (profile_id,agent_type,trigger_event)).fetchone()
            return row[0]
    return jid

def claim_next():
    ensure_schema()
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute("SELECT * FROM agent_jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
        if not row: return None
        db.execute("UPDATE agent_jobs SET status='running',attempts=attempts+1,updated_at=? WHERE job_id=?",(now(),row['job_id']))
        return dict(row)

def finish(job_id:str, output:dict):
    with connect() as db: db.execute("UPDATE agent_jobs SET status='done',output_json=?,updated_at=? WHERE job_id=?",(json.dumps(output),now(),job_id))

def fail(job_id:str, error:str, retry:bool=True):
    with connect() as db:
        row=db.execute('SELECT attempts FROM agent_jobs WHERE job_id=?',(job_id,)).fetchone(); attempts=row[0] if row else 9
        status='queued' if retry and attempts<3 else 'failed'
        db.execute('UPDATE agent_jobs SET status=?,error=?,updated_at=? WHERE job_id=?',(status,error[:2000],now(),job_id))


def completed(profile_id:str, agent_types:list[str]):
    ensure_schema()
    with connect() as db:
        rows=db.execute("SELECT agent_type,status FROM agent_jobs WHERE profile_id=?",(profile_id,)).fetchall()
    state={r['agent_type']:r['status'] for r in rows}
    return all(state.get(a)=='done' for a in agent_types)
