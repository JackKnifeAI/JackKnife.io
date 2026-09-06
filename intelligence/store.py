from __future__ import annotations
import hashlib, json, sqlite3
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parent
DB=ROOT/'knowledge.db'
BRIEFS=ROOT/'briefs'

def connect():
    db=sqlite3.connect(DB); db.row_factory=sqlite3.Row
    db.executescript('''
    CREATE TABLE IF NOT EXISTS briefs(id INTEGER PRIMARY KEY AUTOINCREMENT, brief_date TEXT UNIQUE NOT NULL, path TEXT NOT NULL, content_hash TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS findings(finding_id TEXT PRIMARY KEY, topic TEXT NOT NULL, claim TEXT NOT NULL, confidence TEXT NOT NULL, status TEXT NOT NULL, supersedes TEXT, brief_date TEXT NOT NULL, source_ids_json TEXT NOT NULL, implications_json TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS sources(source_id TEXT PRIMARY KEY, url TEXT NOT NULL, title TEXT NOT NULL, publisher TEXT, published_at TEXT, retrieved_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS competitors(name TEXT PRIMARY KEY, latest_changes_json TEXT NOT NULL, threat_level TEXT NOT NULL, brief_date TEXT NOT NULL, updated_at TEXT NOT NULL);
    '''); return db

def ingest(doc:dict):
    required=('brief_date','generated_at','findings','sources')
    missing=[k for k in required if k not in doc]
    if missing: raise ValueError('missing fields: '+', '.join(missing))
    BRIEFS.mkdir(parents=True,exist_ok=True)
    date=doc['brief_date']; raw=json.dumps(doc,indent=2,sort_keys=True); h=hashlib.sha256(raw.encode()).hexdigest(); path=BRIEFS/f'{date}.json'; path.write_text(raw+'\n')
    now=datetime.now(timezone.utc).isoformat()
    db=connect()
    try:
      with db:
        db.execute('INSERT OR REPLACE INTO briefs(brief_date,path,content_hash,created_at) VALUES(?,?,?,?)',(date,str(path.relative_to(ROOT)),h,now))
        for s in doc.get('sources',[]): db.execute('INSERT OR REPLACE INTO sources VALUES(?,?,?,?,?,?)',(s['id'],s['url'],s['title'],s.get('publisher'),s.get('published_at'),s.get('retrieved_at',now)))
        for f in doc.get('findings',[]): db.execute('INSERT OR REPLACE INTO findings VALUES(?,?,?,?,?,?,?,?,?,?)',(f['id'],f['topic'],f['claim'],f.get('confidence','medium'),f.get('status','new'),f.get('supersedes'),date,json.dumps(f.get('source_ids',[])),json.dumps(f.get('implications',[])),now))
        for c in doc.get('competitors',[]): db.execute('INSERT OR REPLACE INTO competitors VALUES(?,?,?,?,?)',(c['name'],json.dumps(c.get('changes',[])),c.get('threat_level','unknown'),date,now))
    finally: db.close()
    return {'brief_date':date,'path':str(path),'content_hash':h,'findings':len(doc.get('findings',[])),'sources':len(doc.get('sources',[]))}

def latest_findings(limit=50):
    db=connect()
    try:return [dict(r) for r in db.execute('SELECT finding_id,topic,claim,confidence,status,supersedes,brief_date FROM findings ORDER BY brief_date DESC,updated_at DESC LIMIT ?',(limit,))]
    finally:db.close()
