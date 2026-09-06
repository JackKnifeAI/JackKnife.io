from __future__ import annotations
import json, os
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from .profile_store import profile_for_token, save_intake, connect, issue_session_for_checkout
from .discovery import crawl
from .workspace import write_json
from .blueprint import generate as generate_blueprint
from .stripe_webhook import handle as handle_stripe_webhook
from .stripe_checkout import create_core_checkout
from .agent_jobs import enqueue
from .approval import record as record_action, list_actions
from .execution import approve as approve_execution, seed_steps, list_steps, set_step, approvals as execution_approvals
from .authorizations import request as request_external, authorize as authorize_external, complete as complete_external, list_for as external_authorizations, issue_acceptance_token, accept as record_client_acceptance, acceptance as client_acceptance

SITE_ROOT=Path(__file__).resolve().parents[2]
OPERATOR_TOKEN=os.environ.get('JK_OPERATOR_TOKEN','')

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw): super().__init__(*a,directory=str(SITE_ROOT),**kw)
    def send_json(self,status,obj):
        body=json.dumps(obj).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def raw_body(self):
        n=int(self.headers.get('Content-Length','0')); return self.rfile.read(n)
    def token(self): return self.headers.get('Authorization','').removeprefix('Bearer ').strip()
    def do_GET(self):
        parsed=urlparse(self.path)
        if parsed.path=='/api/health': return self.send_json(200,{"ok":True,"service":"jackknife-onboarding"})
        if parsed.path=='/api/profile':
            row=profile_for_token(self.token()); return self.send_json(200,{k:row[k] for k in ('profile_id','email','payment_status','state','created_at','updated_at')}) if row else self.send_json(401,{"error":"invalid session"})
        if parsed.path=='/api/operator/review':
            if not OPERATOR_TOKEN or self.token()!=OPERATOR_TOKEN: return self.send_json(401,{"error":"operator authentication required"})
            pid=parse_qs(parsed.query).get('profile',[''])[0]
            with connect() as db:
                profile=db.execute('SELECT profile_id,email,payment_status,state,created_at,updated_at FROM profiles WHERE profile_id=?',(pid,)).fetchone()
                jobs=[dict(r) for r in db.execute('SELECT agent_type,status,attempts,error,created_at,updated_at FROM agent_jobs WHERE profile_id=? ORDER BY created_at,rowid',(pid,))]
            if not profile: return self.send_json(404,{"error":"profile not found"})
            def artifact(rel):
                q=SITE_ROOT/'onboarding'/'clients'/pid/rel
                try: return json.loads(q.read_text())
                except Exception: return None
            return self.send_json(200,{"profile":dict(profile),"jobs":jobs,"blueprint":artifact('blueprints/blueprint-v1.json'),"manifest":artifact('manifests/draft-v1.json'),"integration_plan":artifact('integrations/plan.json'),"review":artifact('reviews/operator-review-v1.json'),"operator_actions":list_actions(pid),"execution_approvals":execution_approvals(pid),"execution_steps":list_steps(pid),"external_authorizations":external_authorizations(pid),"client_acceptance":client_acceptance(pid),"deployment":{"infrastructure":artifact('deployment/infrastructure-plan.json'),"branding":artifact('deployment/branding-config-draft.json'),"integration_setup":artifact('deployment/integration-setup-plan.json'),"validation":artifact('deployment/validation-plan.json'),"acceptance":artifact('deployment/acceptance-test-plan.json')}})
        return super().do_GET()
    def do_POST(self):
        parsed=urlparse(self.path)
        raw=self.raw_body()
        if parsed.path=='/api/billing/checkout':
            try: result=create_core_checkout()
            except Exception as e: return self.send_json(503,{"error":str(e)})
            return self.send_json(201,result)
        if parsed.path=='/api/billing/stripe/webhook':
            try: result=handle_stripe_webhook(raw,self.headers.get('Stripe-Signature',''))
            except Exception as e: return self.send_json(400,{"error":str(e)})
            return self.send_json(200,result)
        try: data=json.loads(raw or b'{}')
        except Exception: return self.send_json(400,{"error":"invalid json"})
        if parsed.path=='/api/onboarding/claim':
            try: pid,tok=issue_session_for_checkout(data.get('checkout_session_id',''))
            except PermissionError as e: return self.send_json(403,{"error":str(e)})
            return self.send_json(200,{"profile_id":pid,"onboarding_token":tok,"redirect":f"/onboarding/?profile={pid}"})
        if parsed.path=='/api/operator/action':
            if not OPERATOR_TOKEN or self.token()!=OPERATOR_TOKEN: return self.send_json(401,{"error":"operator authentication required"})
            pid=data.get('profile_id',''); action=data.get('action',''); actor=data.get('actor','operator'); note=data.get('note','')
            if action not in ('approve','return','block'): return self.send_json(400,{"error":"invalid action"})
            with connect() as db:
                row=db.execute('SELECT state FROM profiles WHERE profile_id=?',(pid,)).fetchone()
                if not row: return self.send_json(404,{"error":"profile not found"})
                if row['state']!='BLUEPRINT_READY' and action=='approve': return self.send_json(409,{"error":"approval requires BLUEPRINT_READY"})
                new_state={'approve':'DEPLOYMENT_PLANNING','return':'HUMAN_REVIEW','block':'BLOCKED'}[action]
                db.execute("UPDATE profiles SET state=?,updated_at=datetime('now') WHERE profile_id=?",(new_state,pid))
                db.execute("INSERT INTO events(profile_id,event_type,body_json,created_at) VALUES(?,?,?,datetime('now'))",(pid,'operator_'+action,json.dumps({'actor':actor,'note':note})))
            audit=record_action(pid,action,actor,note)
            jobs=[]
            if action=='approve':
                jobs=[enqueue(pid,'infrastructure_planner','operator_approved',{}),enqueue(pid,'branding_config_compiler','operator_approved',{}),enqueue(pid,'integration_setup_coordinator','operator_approved',{})]
            return self.send_json(200,{"profile_id":pid,"state":new_state,"audit":audit,"agent_jobs":jobs})
        if parsed.path=='/api/operator/execution-approve':
            if not OPERATOR_TOKEN or self.token()!=OPERATOR_TOKEN: return self.send_json(401,{"error":"operator authentication required"})
            pid=data.get('profile_id',''); actor=data.get('actor','operator'); note=data.get('note',''); scope=data.get('scope') or ['workspace_prepare','branding_apply','platform_configure','deployment_smoke_test','rollback_verify']
            with connect() as db:
                row=db.execute('SELECT state FROM profiles WHERE profile_id=?',(pid,)).fetchone()
                if not row: return self.send_json(404,{"error":"profile not found"})
                if row['state']!='DEPLOYMENT_PLAN_READY': return self.send_json(409,{"error":"execution approval requires DEPLOYMENT_PLAN_READY"})
                db.execute("UPDATE profiles SET state='EXECUTION_PREFLIGHT',updated_at=datetime('now') WHERE profile_id=?",(pid,))
                db.execute("INSERT INTO events(profile_id,event_type,body_json,created_at) VALUES(?,?,?,datetime('now'))",(pid,'execution_approved',json.dumps({'actor':actor,'note':note,'scope':scope})))
            audit=approve_execution(pid,actor,note,scope); seed_steps(pid)
            jid=enqueue(pid,'execution_workspace_prepare','execution_approved',{'scope':scope})
            return self.send_json(200,{"profile_id":pid,"state":"EXECUTION_PREFLIGHT","approval":audit,"agent_jobs":[jid]})
        if parsed.path=='/api/operator/external-request':
            if not OPERATOR_TOKEN or self.token()!=OPERATOR_TOKEN: return self.send_json(401,{"error":"operator authentication required"})
            pid=data.get('profile_id',''); action_type=data.get('action_type',''); provider=data.get('provider',''); note=data.get('note','')
            if action_type not in ('infrastructure_provision','integration_connect'): return self.send_json(400,{"error":"unsupported external action type"})
            if not provider: return self.send_json(400,{"error":"provider required"})
            rows=request_external(pid,action_type,provider,'jackknife-operator',note)
            return self.send_json(201,{"profile_id":pid,"authorizations":rows})
        if parsed.path=='/api/operator/external-authorize':
            if not OPERATOR_TOKEN or self.token()!=OPERATOR_TOKEN: return self.send_json(401,{"error":"operator authentication required"})
            pid=data.get('profile_id',''); action_type=data.get('action_type',''); provider=data.get('provider',''); ref=data.get('authorization_ref',''); actor=data.get('authorized_by','')
            if not all((pid,action_type,provider,ref,actor)): return self.send_json(400,{"error":"profile_id, action_type, provider, authorized_by and authorization_ref required"})
            authorize_external(pid,action_type,provider,actor,ref,data.get('note',''))
            return self.send_json(200,{"profile_id":pid,"authorizations":external_authorizations(pid)})
        if parsed.path=='/api/operator/external-complete':
            if not OPERATOR_TOKEN or self.token()!=OPERATOR_TOKEN: return self.send_json(401,{"error":"operator authentication required"})
            pid=data.get('profile_id',''); action_type=data.get('action_type',''); provider=data.get('provider',''); evidence=data.get('evidence_ref','')
            rows=external_authorizations(pid); match=next((r for r in rows if r['action_type']==action_type and r['provider']==provider),None)
            if not match or match['status']!='authorized': return self.send_json(409,{"error":"external action must be authorized before completion"})
            if not evidence: return self.send_json(400,{"error":"evidence_ref required"})
            complete_external(pid,action_type,provider,evidence)
            set_step(pid,action_type,'done',{'provider':provider,'evidence_ref':evidence})
            return self.send_json(200,{"profile_id":pid,"authorizations":external_authorizations(pid)})
        if parsed.path=='/api/operator/live-validation':
            if not OPERATOR_TOKEN or self.token()!=OPERATOR_TOKEN: return self.send_json(401,{"error":"operator authentication required"})
            pid=data.get('profile_id',''); rows=external_authorizations(pid); steps=list_steps(pid)
            infra=[r for r in rows if r['action_type']=='infrastructure_provision']
            if not infra or any(r['status']!='completed' for r in infra): return self.send_json(409,{"error":"completed infrastructure authorization evidence required"})
            if any(r['status']!='completed' for r in rows): return self.send_json(409,{"error":"all requested external actions require completion evidence"})
            required_safe={'workspace_prepare','branding_apply','platform_configure','deployment_smoke_test','rollback_verify'}
            states={x['step_type']:x['status'] for x in steps}
            if any(states.get(x)!='done' for x in required_safe): return self.send_json(409,{"error":"safe execution preflight incomplete"})
            if states.get('infrastructure_provision')!='done': return self.send_json(409,{"error":"infrastructure execution evidence incomplete"})
            if states.get('integration_connect') not in ('done','waived'): return self.send_json(409,{"error":"integration execution requires completion or explicit waiver"})
            evidence=data.get('evidence') or {}
            if not evidence.get('smoke_tests_passed') or not evidence.get('rollback_ready'): return self.send_json(400,{"error":"smoke_tests_passed and rollback_ready evidence required"})
            write_json(pid,'execution/live-validation.json',evidence)
            with connect() as db:
                db.execute("UPDATE profiles SET state='CLIENT_ACCEPTANCE_PENDING',updated_at=datetime('now') WHERE profile_id=?",(pid,))
                db.execute("INSERT INTO events(profile_id,event_type,body_json,created_at) VALUES(?,?,?,datetime('now'))",(pid,'live_validation_passed',json.dumps(evidence)))
            return self.send_json(200,{"profile_id":pid,"state":"CLIENT_ACCEPTANCE_PENDING"})
        if parsed.path=='/api/operator/acceptance-link':
            if not OPERATOR_TOKEN or self.token()!=OPERATOR_TOKEN: return self.send_json(401,{"error":"operator authentication required"})
            pid=data.get('profile_id','')
            with connect() as db:
                row=db.execute('SELECT state FROM profiles WHERE profile_id=?',(pid,)).fetchone()
                if not row: return self.send_json(404,{"error":"profile not found"})
                if row['state']!='CLIENT_ACCEPTANCE_PENDING': return self.send_json(409,{"error":"acceptance link requires CLIENT_ACCEPTANCE_PENDING"})
            tok=issue_acceptance_token(pid)
            return self.send_json(201,{"profile_id":pid,"acceptance_path":f"/onboarding/accept.html?token={tok}"})
        if parsed.path=='/api/client/accept':
            token=data.get('token',''); signer=data.get('signer_name','').strip(); note=data.get('note','')
            if not signer: return self.send_json(400,{"error":"signer name required"})
            try: pid,artifact_hash=record_client_acceptance(token,signer,note,data.get('artifact') or {})
            except PermissionError as e: return self.send_json(403,{"error":str(e)})
            with connect() as db:
                row=db.execute('SELECT state FROM profiles WHERE profile_id=?',(pid,)).fetchone()
                if not row or row['state']!='CLIENT_ACCEPTANCE_PENDING': return self.send_json(409,{"error":"client acceptance requires CLIENT_ACCEPTANCE_PENDING"})
                db.execute("UPDATE profiles SET state='LIVE',updated_at=datetime('now') WHERE profile_id=?",(pid,))
            set_step(pid,'client_acceptance','done',{'signer_name':signer,'artifact_hash':artifact_hash})
            return self.send_json(200,{"profile_id":pid,"decision":"accepted","artifact_hash":artifact_hash,"state":"LIVE"})
        if parsed.path=='/api/onboarding/submit':
            try: pid=save_intake(self.token(),data)
            except PermissionError as e: return self.send_json(401,{"error":str(e)})
            except Exception as e: return self.send_json(400,{"error":str(e)})
            discovery=None
            if data.get('discovery',{}).get('public_website_authorized') and data.get('consents',{}).get('public_discovery'):
                discovery=crawl(data.get('business',{}).get('website',''))
                write_json(pid,'evidence/public-website-latest.json',discovery)
            jobs=[]
            jobs.append(enqueue(pid,'discovery_analyst','intake_submitted',{'has_discovery':bool(discovery)}))
            jobs.append(enqueue(pid,'business_architect','intake_submitted',{}))
            jobs.append(enqueue(pid,'integration_planner','intake_submitted',{}))
            with connect() as db:
                state='AGENTS_QUEUED'
                db.execute("INSERT INTO events(profile_id,event_type,body_json,created_at) VALUES(?,?,?,datetime('now'))",(pid,'onboarding_agents_queued',json.dumps({'jobs':jobs})))
                db.execute("UPDATE profiles SET state=?,updated_at=datetime('now') WHERE profile_id=?",(state,pid))
            return self.send_json(202,{"profile_id":pid,"state":state,"agent_jobs":jobs})
        return self.send_json(404,{"error":"not found"})

def main():
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('--host',default='127.0.0.1'); ap.add_argument('--port',type=int,default=8790); a=ap.parse_args()
    ThreadingHTTPServer((a.host,a.port),Handler).serve_forever()
if __name__=='__main__': main()
