from __future__ import annotations
import json, time, traceback
from .agent_jobs import claim_next, finish, fail, enqueue, completed
from .agents import AGENTS

def run_once():
    job=claim_next()
    if not job: return False
    try:
        fn=AGENTS[job['agent_type']]
        out=fn(job['profile_id'],json.loads(job['input_json']))
        finish(job['job_id'],out)
        pid=job['profile_id']
        if job['agent_type'] in ('discovery_analyst','business_architect','integration_planner') and completed(pid,['discovery_analyst','business_architect','integration_planner']):
            enqueue(pid,'model_advisor','analysis_complete',{})
        elif job['agent_type']=='model_advisor':
            enqueue(pid,'manifest_compiler','advisory_complete',{})
        elif job['agent_type']=='manifest_compiler':
            enqueue(pid,'review_prep','manifest_compiled',{})
        elif job['agent_type']=='review_prep':
            from .profile_store import connect
            with connect() as db:
                db.execute("UPDATE profiles SET state='BLUEPRINT_READY',updated_at=datetime('now') WHERE profile_id=?",(pid,))
                db.execute("INSERT INTO events(profile_id,event_type,body_json,created_at) VALUES(?,?,?,datetime('now'))",(pid,'agent_pipeline_completed','{}'))
        elif job['agent_type'] in ('infrastructure_planner','branding_config_compiler','integration_setup_coordinator') and completed(pid,['infrastructure_planner','branding_config_compiler','integration_setup_coordinator']):
            enqueue(pid,'deployment_validation_planner','deployment_plans_ready',{})
        elif job['agent_type']=='deployment_validation_planner':
            enqueue(pid,'acceptance_test_designer','validation_plan_ready',{})
        elif job['agent_type']=='acceptance_test_designer':
            from .profile_store import connect
            with connect() as db:
                db.execute("UPDATE profiles SET state='DEPLOYMENT_PLAN_READY',updated_at=datetime('now') WHERE profile_id=?",(pid,))
                db.execute("INSERT INTO events(profile_id,event_type,body_json,created_at) VALUES(?,?,?,datetime('now'))",(pid,'deployment_planning_agents_completed','{}'))
        elif job['agent_type']=='execution_workspace_prepare':
            enqueue(pid,'execution_branding_apply','execution_workspace_ready',{})
        elif job['agent_type']=='execution_branding_apply':
            enqueue(pid,'execution_platform_configure','branding_staged',{})
        elif job['agent_type']=='execution_platform_configure':
            enqueue(pid,'execution_smoke_test','platform_staged',{})
        elif job['agent_type']=='execution_smoke_test':
            enqueue(pid,'execution_rollback_verify','preflight_passed',{})
        elif job['agent_type']=='execution_rollback_verify':
            from .profile_store import connect
            from .execution import seed_steps, set_step
            seed_steps(pid)
            set_step(pid,'infrastructure_provision','waiting_human',{'reason':'external infrastructure provider authorization required'})
            from .agents import load
            integration_plan=load(pid,'integrations/plan.json',{'integrations':[]})
            if integration_plan.get('integrations'):
                set_step(pid,'integration_connect','waiting_human',{'reason':'client/provider authorization required'})
            else:
                set_step(pid,'integration_connect','waived',{'reason':'no external integrations declared in approved plan'})
            set_step(pid,'client_acceptance','waiting_human',{'reason':'client acceptance occurs after live validation'})
            with connect() as db:
                db.execute("UPDATE profiles SET state='EXECUTION_BLOCKED_ON_EXTERNALS',updated_at=datetime('now') WHERE profile_id=?",(pid,))
                db.execute("INSERT INTO events(profile_id,event_type,body_json,created_at) VALUES(?,?,?,datetime('now'))",(pid,'safe_execution_preflight_completed','{}'))
    except Exception as e:
        fail(job['job_id'],traceback.format_exc())
    return True

def main():
    while True:
        if not run_once(): time.sleep(1)
if __name__=='__main__': main()
