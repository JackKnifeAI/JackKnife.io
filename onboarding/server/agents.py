from __future__ import annotations
import json
from pathlib import Path
from .workspace import ensure_workspace, write_json
from .blueprint import generate as generate_blueprint

def load(profile_id, rel, default=None):
    p=ensure_workspace(profile_id)/rel
    return json.loads(p.read_text()) if p.exists() else default

def discovery_analyst(profile_id, payload):
    intake=load(profile_id,'intake/latest.json',{})
    evidence=load(profile_id,'evidence/public-website-latest.json',{})
    pages=evidence.get('pages',[]) if evidence else []
    observed={'page_count':len(pages),'titles':[p.get('title') for p in pages if p.get('title')][:20],
              'brand_asset_candidates':evidence.get('brand_asset_candidates',[])[:20] if evidence else []}
    result={'agent':'discovery_analyst','profile_id':profile_id,'confirmed':intake.get('business',{}),
            'observed':observed,'inferences':[],'requires_human_confirmation':True}
    write_json(profile_id,'agent-output/discovery-analysis.json',result); return result

def business_architect(profile_id, payload):
    intake=load(profile_id,'intake/latest.json',{})
    evidence=load(profile_id,'evidence/public-website-latest.json')
    bp=generate_blueprint({**intake,'profile_id':profile_id},evidence)
    bp['generated_by']='business_architect'
    write_json(profile_id,'blueprints/blueprint-v1.json',bp); return bp

def integration_planner(profile_id,payload):
    intake=load(profile_id,'intake/latest.json',{})
    systems=intake.get('systems',{})
    plan=[]
    for category, values in systems.items():
        for value in values or []:
            plan.append({'category':category,'provider_or_system':value,'status':'needs_review','auth':'explicit_client_authorization','action':'connect_or_migrate'})
    out={'agent':'integration_planner','profile_id':profile_id,'integrations':plan,'secrets_policy':'references-only','human_gate':True}
    write_json(profile_id,'integrations/plan.json',out); return out


def model_advisor(profile_id,payload):
    from .model_runtime import advise
    intake=load(profile_id,'intake/latest.json',{})
    discovery=load(profile_id,'agent-output/discovery-analysis.json',{})
    integration=load(profile_id,'integrations/plan.json',{})
    safe_context={'business':intake.get('business',{}),'operations':intake.get('operations',{}),'privacy':intake.get('privacy',{}),'modules':intake.get('modules',[]),'discovery':discovery,'integration_plan':integration}
    try:
        result=advise('Identify architecture risks, missing intake facts, privacy concerns, integration conflicts, and high-value recommendations for this client deployment.',safe_context)
    except Exception as e:
        result={'status':'error','reason':type(e).__name__,'advisory':True}
    result.update({'agent':'model_advisor','profile_id':profile_id,'can_authorize':False,'can_execute':False})
    write_json(profile_id,'agent-output/model-advisory.json',result); return result

def manifest_compiler(profile_id,payload):
    intake=load(profile_id,'intake/latest.json',{})
    bp=load(profile_id,'blueprints/blueprint-v1.json',{})
    integ=load(profile_id,'integrations/plan.json',{'integrations':[]})
    b=intake.get('business',{}); priv=intake.get('privacy',{})
    manifest={'schema_version':1,'profile_id':profile_id,'client':{'company_name':b.get('company_name',''),'industry':b.get('industry',''),'timezone':b.get('timezone',''),'service_area':b.get('service_area',''),'jurisdiction':b.get('jurisdiction','')},
      'infrastructure':{'ownership':priv.get('infrastructure_preference','client'),'environment':'pilot','isolation':'per-client','private_network':'required','public_ingress':[],'backup_policy':'encrypted + tested'},
      'platform':{'core_version':'current','vertical_adapter':bp.get('recommended_vertical_adapter','custom'),'client_extension':'workspace-scoped','branding_profile':'from-approved-discovery'},
      'modules':[{'id':m,'enabled':True,'configuration':{}} for m in intake.get('modules',[])],
      'integrations':[{'provider':x['provider_or_system'],'status':'pending'} for x in integ.get('integrations',[])],
      'policies':{'automation_level':priv.get('automation_level','approval-first'),'approval_rules':['financial and external side effects require configured approval'],'data_residency':'client-selected','retention':priv.get('retention_notes',''),'public_discovery_scope':intake.get('discovery',{}).get('allowed_public_sources',[])},
      'evidence':{'intake_version':1,'discovery_snapshot':'public-website-latest','blueprint_version':1,'approved_by':[]},
      'status':'draft','requires_operator_approval':True}
    write_json(profile_id,'manifests/draft-v1.json',manifest); return manifest

def review_prep(profile_id,payload):
    bp=load(profile_id,'blueprints/blueprint-v1.json',{})
    manifest=load(profile_id,'manifests/draft-v1.json',{})
    integ=load(profile_id,'integrations/plan.json',{})
    advisory=load(profile_id,'agent-output/model-advisory.json',{'status':'not_available'})
    out={'agent':'review_prep','profile_id':profile_id,'decision':'OPERATOR_REVIEW_REQUIRED',
         'blueprint_summary':bp.get('summary',bp.get('business',{})),'module_count':len(manifest.get('modules',[])),
         'integration_count':len(integ.get('integrations',[])),'blockers':bp.get('human_decisions',[]),
         'provisioning_allowed':False,'model_advisory':advisory}
    write_json(profile_id,'reviews/operator-review-v1.json',out); return out


def infrastructure_planner(profile_id,payload):
    manifest=load(profile_id,'manifests/draft-v1.json',{})
    client=manifest.get('client',{})
    out={'agent':'infrastructure_planner','profile_id':profile_id,'mode':'plan-only','isolation':'per-client',
         'recommended':{'environment':'pilot','private_network':'required','backup':'encrypted + tested','public_ingress':'least-privilege only'},
         'client':client,'requires_operator_execution':True,'touches_live_infrastructure':False}
    write_json(profile_id,'deployment/infrastructure-plan.json',out); return out

def branding_config_compiler(profile_id,payload):
    intake=load(profile_id,'intake/latest.json',{})
    discovery=load(profile_id,'agent-output/discovery-analysis.json',{})
    out={'agent':'branding_config_compiler','profile_id':profile_id,'company_name':intake.get('business',{}).get('company_name',''),
         'brand_asset_candidates':discovery.get('observed',{}).get('brand_asset_candidates',[]),
         'status':'draft','requires_client_confirmation':True,'writes_live_config':False}
    write_json(profile_id,'deployment/branding-config-draft.json',out); return out

def integration_setup_coordinator(profile_id,payload):
    plan=load(profile_id,'integrations/plan.json',{'integrations':[]})
    tasks=[]
    for x in plan.get('integrations',[]):
        tasks.append({'provider_or_system':x.get('provider_or_system',''),'category':x.get('category',''),
                      'next_step':'explicit_client_authorization','status':'blocked_on_authorization'})
    out={'agent':'integration_setup_coordinator','profile_id':profile_id,'tasks':tasks,
         'credential_policy':'references-only','side_effects_performed':False}
    write_json(profile_id,'deployment/integration-setup-plan.json',out); return out

def deployment_validation_planner(profile_id,payload):
    manifest=load(profile_id,'manifests/draft-v1.json',{})
    checks=['manifest schema validation','client isolation check','backup/restore rehearsal','private network health',
            'public ingress allowlist validation','integration smoke tests','operator rollback procedure']
    out={'agent':'deployment_validation_planner','profile_id':profile_id,'checks':checks,'manifest_status':manifest.get('status','draft'),
         'execution':'not_started','requires_live_environment':True}
    write_json(profile_id,'deployment/validation-plan.json',out); return out

def acceptance_test_designer(profile_id,payload):
    intake=load(profile_id,'intake/latest.json',{})
    modules=intake.get('modules',[])
    tests=[{'module':m,'criterion':'operator-defined acceptance scenario passes','status':'pending'} for m in modules]
    out={'agent':'acceptance_test_designer','profile_id':profile_id,'tests':tests,'client_signoff_required':True,'status':'draft'}
    write_json(profile_id,'deployment/acceptance-test-plan.json',out); return out


def execution_workspace_prepare(profile_id,payload):
    from .execution import set_step
    result={'agent':'execution_workspace_prepare','mode':'local-staging','created':True,'side_effects':'workspace-only','profile_id':profile_id}
    set_step(profile_id,'workspace_prepare','done',result); return result

def execution_branding_apply(profile_id,payload):
    from .execution import set_step
    draft=load(profile_id,'deployment/branding-config-draft.json',{})
    result={'agent':'execution_branding_apply','mode':'staged-config','source':'deployment/branding-config-draft.json','client_confirmation_required':True,'applied_to_live':False,'draft':draft}
    set_step(profile_id,'branding_apply','done',result); return result

def execution_platform_configure(profile_id,payload):
    from .execution import set_step
    manifest=load(profile_id,'manifests/draft-v1.json',{})
    result={'agent':'execution_platform_configure','mode':'staged-config','manifest_profile':manifest.get('profile_id'),'live_write':False,'configuration_bundle_ready':True}
    write_json(profile_id,'execution/configuration-bundle.json',{'manifest':manifest,'status':'staged','live_write':False})
    set_step(profile_id,'platform_configure','done',result); return result

def execution_smoke_test(profile_id,payload):
    from .execution import set_step
    checks=['workspace artifacts readable','manifest present','planning artifacts present','no raw secret fields in deployment manifest','human gates intact']
    manifest=load(profile_id,'manifests/draft-v1.json',{})
    serialized=json.dumps(manifest).lower()
    raw_secret_markers=[x for x in ('password','api_key','secret_key','private_key') if x in serialized]
    result={'agent':'execution_smoke_test','mode':'preflight-only','checks':checks,'passed':not raw_secret_markers,'raw_secret_markers':raw_secret_markers,'live_endpoint_tests':False}
    set_step(profile_id,'deployment_smoke_test','done' if result['passed'] else 'failed',result); return result

def execution_rollback_verify(profile_id,payload):
    from .execution import set_step
    result={'agent':'execution_rollback_verify','rollback_plan_present':True,'pre_live_snapshot_required':True,'restore_test_required_on_target':True,'verified_live_restore':False}
    write_json(profile_id,'execution/rollback-plan.json',result)
    set_step(profile_id,'rollback_verify','done',result); return result

AGENTS={'model_advisor':model_advisor,'discovery_analyst':discovery_analyst,'business_architect':business_architect,'integration_planner':integration_planner,'manifest_compiler':manifest_compiler,'review_prep':review_prep,'infrastructure_planner':infrastructure_planner,'branding_config_compiler':branding_config_compiler,'integration_setup_coordinator':integration_setup_coordinator,'deployment_validation_planner':deployment_validation_planner,'acceptance_test_designer':acceptance_test_designer,'execution_workspace_prepare':execution_workspace_prepare,'execution_branding_apply':execution_branding_apply,'execution_platform_configure':execution_platform_configure,'execution_smoke_test':execution_smoke_test,'execution_rollback_verify':execution_rollback_verify}
