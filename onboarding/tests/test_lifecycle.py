import json, tempfile, unittest
from pathlib import Path

from onboarding.server import profile_store, workspace
from onboarding.server.profile_store import mark_paid, save_intake, connect
from onboarding.server.agent_jobs import enqueue
from onboarding.server.agent_worker import run_once
from onboarding.server.execution import approve, seed_steps, list_steps, set_step
from onboarding.server.authorizations import request, authorize, complete, issue_acceptance_token, accept

class LifecycleTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        root=Path(self.tmp.name)
        profile_store.DB_PATH=root/'test.db'
        workspace.CLIENTS_ROOT=root/'clients'
        self.pid,self.token=mark_paid('test@example.com','cs_test_lifecycle','stripe')
        self.intake={
          'schema_version':1,
          'business':{'company_name':'Test Trade Co','owner_name':'Owner','primary_email':'test@example.com','primary_phone':'','website':'https://example.com','industry':'plumbing','timezone':'America/Los_Angeles','service_area':'Test','jurisdiction':'Test','team_size':2},
          'operations':{'services':['service'],'pain_points':['calls'],'office_workflows':['schedule'],'field_workflows':['jobs'],'approval_preferences':'approval-first'},
          'systems':{'email':[],'phone_sms':[],'crm':[],'accounting':[],'calendar':[],'payments':[],'suppliers':[],'other':[]},
          'discovery':{'public_website_authorized':False,'website_url':'https://example.com','allowed_public_sources':[],'brand_assets':False,'crawl_notes':'','authenticated_sources':[]},
          'privacy':{'infrastructure_preference':'client','automation_level':'approval-first','retention_notes':''},
          'modules':['core_office','scheduling'],'uploads':[],
          'consents':{'terms':True,'privacy':True,'public_discovery':False,'timestamp':'2026-09-05T00:00:00Z'}
        }
    def tearDown(self): self.tmp.cleanup()

    def drain(self,limit=30):
        n=0
        while run_once():
            n+=1
            if n>=limit: break
        return n

    def state(self):
        with connect() as db:return db.execute('select state from profiles where profile_id=?',(self.pid,)).fetchone()[0]

    def test_end_to_end_gated_lifecycle(self):
        save_intake(self.token,self.intake)
        enqueue(self.pid,'discovery_analyst','intake_submitted',{})
        enqueue(self.pid,'business_architect','intake_submitted',{})
        enqueue(self.pid,'integration_planner','intake_submitted',{})
        with connect() as db: db.execute("update profiles set state='AGENTS_QUEUED' where profile_id=?",(self.pid,))
        self.assertEqual(self.drain(),6)
        self.assertEqual(self.state(),'BLUEPRINT_READY')
        enqueue(self.pid,'infrastructure_planner','operator_approved',{})
        enqueue(self.pid,'branding_config_compiler','operator_approved',{})
        enqueue(self.pid,'integration_setup_coordinator','operator_approved',{})
        with connect() as db: db.execute("update profiles set state='DEPLOYMENT_PLANNING' where profile_id=?",(self.pid,))
        self.assertEqual(self.drain(),5)
        self.assertEqual(self.state(),'DEPLOYMENT_PLAN_READY')
        approve(self.pid,'tester','approved safe execution',['workspace_prepare','branding_apply','platform_configure','deployment_smoke_test','rollback_verify'])
        seed_steps(self.pid)
        enqueue(self.pid,'execution_workspace_prepare','execution_approved',{})
        with connect() as db: db.execute("update profiles set state='EXECUTION_PREFLIGHT' where profile_id=?",(self.pid,))
        self.assertEqual(self.drain(),5)
        self.assertEqual(self.state(),'EXECUTION_BLOCKED_ON_EXTERNALS')
        states={x['step_type']:x['status'] for x in list_steps(self.pid)}
        self.assertEqual(states['integration_connect'],'waived')
        self.assertEqual(states['infrastructure_provision'],'waiting_human')
        request(self.pid,'infrastructure_provision','test-vps','tester','test')
        authorize(self.pid,'infrastructure_provision','test-vps','tester','auth-ref')
        complete(self.pid,'infrastructure_provision','test-vps','evidence-ref')
        set_step(self.pid,'infrastructure_provision','done',{'evidence_ref':'evidence-ref'})
        with connect() as db: db.execute("update profiles set state='CLIENT_ACCEPTANCE_PENDING' where profile_id=?",(self.pid,))
        tok=issue_acceptance_token(self.pid)
        pid,artifact_hash=accept(tok,'Test Signer','accepted',{'validation':'passed'})
        self.assertEqual(pid,self.pid); self.assertTrue(artifact_hash)
        with self.assertRaises(PermissionError): accept(tok,'Test Signer','again',{})

    def test_payment_idempotency(self):
        pid2,_=mark_paid('test@example.com','cs_test_lifecycle','stripe')
        self.assertEqual(pid2,self.pid)

if __name__=='__main__': unittest.main()
