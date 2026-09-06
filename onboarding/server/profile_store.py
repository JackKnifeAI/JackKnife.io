from __future__ import annotations
import json, secrets, sqlite3
from .workspace import ensure_workspace, write_json
from datetime import datetime, timezone, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "client_profiles.db"

class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None: self.commit()
            else: self.rollback()
        finally:
            self.close()
        return False

def _now(): return datetime.now(timezone.utc).isoformat()

def connect():
    db=sqlite3.connect(DB_PATH, factory=ClosingConnection)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS profiles(
      profile_id TEXT PRIMARY KEY, email TEXT NOT NULL, payment_provider TEXT NOT NULL,
      checkout_reference TEXT UNIQUE NOT NULL, payment_status TEXT NOT NULL, state TEXT NOT NULL,
      intake_json TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS sessions(
      token TEXT PRIMARY KEY, profile_id TEXT NOT NULL, expires_at TEXT, created_at TEXT NOT NULL,
      FOREIGN KEY(profile_id) REFERENCES profiles(profile_id));
    CREATE TABLE IF NOT EXISTS events(
      id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id TEXT NOT NULL, event_type TEXT NOT NULL,
      body_json TEXT NOT NULL, created_at TEXT NOT NULL);
    """)
    return db

def mark_paid(email:str, checkout_reference:str, provider:str="stripe"):
    profile_id="jk_"+secrets.token_hex(8); token=secrets.token_urlsafe(32); now=_now()
    with connect() as db:
      row=db.execute("SELECT profile_id FROM profiles WHERE checkout_reference=?",(checkout_reference,)).fetchone()
      if row:
        profile_id=row[0]
      else:
        db.execute("INSERT INTO profiles VALUES(?,?,?,?,?,?,?,?,?)",(profile_id,email,provider,checkout_reference,"paid","PROFILE_CREATED",None,now,now))
      exp=(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat()
      db.execute("INSERT OR REPLACE INTO sessions(token,profile_id,expires_at,created_at) VALUES(?,?,?,?)",(token,profile_id,exp,now))
      db.execute("INSERT INTO events(profile_id,event_type,body_json,created_at) VALUES(?,?,?,?)",(profile_id,"payment_verified",json.dumps({"provider":provider,"checkout_reference":checkout_reference}),now))
    ensure_workspace(profile_id,email)
    return profile_id,token

def profile_for_token(token:str):
    with connect() as db:
      row=db.execute("SELECT p.*,s.expires_at AS session_expires_at FROM profiles p JOIN sessions s ON s.profile_id=p.profile_id WHERE s.token=?",(token,)).fetchone()
    if not row: return None
    exp=row["session_expires_at"]
    if exp and datetime.fromisoformat(exp) <= datetime.now(timezone.utc): return None
    return row

def save_intake(token:str,payload:dict):
    row=profile_for_token(token)
    if not row or row["payment_status"]!="paid": raise PermissionError("paid onboarding session required")
    payload["profile_id"]=row["profile_id"]
    payload["payment"]={"status":"paid","provider":row["payment_provider"],"checkout_reference":row["checkout_reference"]}
    now=_now()
    with connect() as db:
      db.execute("UPDATE profiles SET intake_json=?,state=?,updated_at=? WHERE profile_id=?",(json.dumps(payload),"INTAKE_SUBMITTED",now,row["profile_id"]))
      db.execute("INSERT INTO events(profile_id,event_type,body_json,created_at) VALUES(?,?,?,?)",(row["profile_id"],"intake_submitted",json.dumps({"schema_version":payload.get("schema_version")}),now))
    write_json(row["profile_id"],"intake/latest.json",payload)
    return row["profile_id"]

def issue_session_for_checkout(checkout_reference:str):
    token=secrets.token_urlsafe(32); now=_now()
    with connect() as db:
      row=db.execute("SELECT profile_id,payment_status FROM profiles WHERE checkout_reference=?",(checkout_reference,)).fetchone()
      if not row or row["payment_status"]!="paid": raise PermissionError("verified paid checkout required")
      exp=(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat()
      db.execute("INSERT INTO sessions(token,profile_id,expires_at,created_at) VALUES(?,?,?,?)",(token,row["profile_id"],exp,now))
      db.execute("INSERT INTO events(profile_id,event_type,body_json,created_at) VALUES(?,?,?,?)",(row["profile_id"],"onboarding_session_issued",json.dumps({"checkout_reference":checkout_reference}),now))
      return row["profile_id"],token
