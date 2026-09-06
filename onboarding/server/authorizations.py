from __future__ import annotations
import hashlib, json, secrets
from datetime import datetime, timezone, timedelta
from .profile_store import connect

def now(): return datetime.now(timezone.utc).isoformat()

def ensure_schema():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS external_authorizations(
          id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id TEXT NOT NULL, action_type TEXT NOT NULL,
          provider TEXT NOT NULL, status TEXT NOT NULL, requested_by TEXT NOT NULL, authorized_by TEXT,
          authorization_ref TEXT, note TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          UNIQUE(profile_id,action_type,provider)
        );
        CREATE TABLE IF NOT EXISTS acceptance_tokens(
          token_hash TEXT PRIMARY KEY, profile_id TEXT NOT NULL, expires_at TEXT, used_at TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS client_acceptance(
          profile_id TEXT PRIMARY KEY, decision TEXT NOT NULL, signer_name TEXT NOT NULL, note TEXT NOT NULL,
          artifact_hash TEXT NOT NULL, created_at TEXT NOT NULL
        );
        """)

def request(profile_id:str, action_type:str, provider:str, requested_by:str='operator', note:str=''):
    ensure_schema(); t=now()
    with connect() as db:
        db.execute('INSERT OR IGNORE INTO external_authorizations(profile_id,action_type,provider,status,requested_by,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(profile_id,action_type,provider,'awaiting_authorization',requested_by,note,t,t))
    return list_for(profile_id)

def authorize(profile_id:str, action_type:str, provider:str, authorized_by:str, authorization_ref:str, note:str=''):
    ensure_schema(); t=now()
    with connect() as db:
        db.execute('UPDATE external_authorizations SET status=?,authorized_by=?,authorization_ref=?,note=?,updated_at=? WHERE profile_id=? AND action_type=? AND provider=?',('authorized',authorized_by,authorization_ref,note,t,profile_id,action_type,provider))
        db.execute('INSERT INTO events(profile_id,event_type,body_json,created_at) VALUES(?,?,?,?)',(profile_id,'external_action_authorized',json.dumps({'action_type':action_type,'provider':provider,'authorized_by':authorized_by,'authorization_ref':authorization_ref}),t))

def complete(profile_id:str, action_type:str, provider:str, evidence_ref:str):
    ensure_schema(); t=now()
    with connect() as db:
        db.execute('UPDATE external_authorizations SET status=?,authorization_ref=?,updated_at=? WHERE profile_id=? AND action_type=? AND provider=?',('completed',evidence_ref,t,profile_id,action_type,provider))

def list_for(profile_id:str):
    ensure_schema()
    with connect() as db: return [dict(r) for r in db.execute('SELECT action_type,provider,status,requested_by,authorized_by,authorization_ref,note,created_at,updated_at FROM external_authorizations WHERE profile_id=? ORDER BY id',(profile_id,))]

def issue_acceptance_token(profile_id:str):
    ensure_schema(); raw=secrets.token_urlsafe(32); h=hashlib.sha256(raw.encode()).hexdigest(); t=now(); exp=(datetime.now(timezone.utc)+timedelta(days=7)).isoformat()
    with connect() as db: db.execute('INSERT INTO acceptance_tokens(token_hash,profile_id,expires_at,created_at) VALUES(?,?,?,?)',(h,profile_id,exp,t))
    return raw

def accept(token:str, signer_name:str, note:str, artifact:dict):
    ensure_schema(); h=hashlib.sha256(token.encode()).hexdigest(); ah=hashlib.sha256(json.dumps(artifact,sort_keys=True,separators=(',',':')).encode()).hexdigest(); t=now()
    with connect() as db:
        row=db.execute('SELECT profile_id,used_at,expires_at FROM acceptance_tokens WHERE token_hash=?',(h,)).fetchone()
        if not row or row['used_at']: raise PermissionError('invalid or used acceptance token')
        if row['expires_at'] and datetime.fromisoformat(row['expires_at']) <= datetime.now(timezone.utc): raise PermissionError('acceptance token expired')
        pid=row['profile_id']; state=db.execute('SELECT state FROM profiles WHERE profile_id=?',(pid,)).fetchone()
        if not state or state['state']!='CLIENT_ACCEPTANCE_PENDING': raise PermissionError('acceptance is not currently allowed')
        db.execute('UPDATE acceptance_tokens SET used_at=? WHERE token_hash=?',(t,h))
        db.execute('INSERT OR REPLACE INTO client_acceptance(profile_id,decision,signer_name,note,artifact_hash,created_at) VALUES(?,?,?,?,?,?)',(pid,'accepted',signer_name,note,ah,t))
        db.execute('INSERT INTO events(profile_id,event_type,body_json,created_at) VALUES(?,?,?,?)',(pid,'client_acceptance_recorded',json.dumps({'signer_name':signer_name,'artifact_hash':ah}),t))
    return pid,ah

def acceptance(profile_id:str):
    ensure_schema()
    with connect() as db:
        r=db.execute('SELECT decision,signer_name,note,artifact_hash,created_at FROM client_acceptance WHERE profile_id=?',(profile_id,)).fetchone(); return dict(r) if r else None
