from __future__ import annotations
from datetime import datetime, timezone

MODULE_MAP={
 "core_office":"Core managed office","voice":"Voice answering and escalation","sms":"SMS/customer communications",
 "estimating":"Estimating and quoting","invoicing":"Invoicing and job costing","scheduling":"Scheduling and dispatch",
 "supplier_recon":"Supplier and pricing intelligence","field_app":"Field crew application","cad_blueprints":"CAD/blueprint workflows",
 "hiring":"Hiring and vetting","advertising":"Advertising operations","reviews":"Review and reputation operations","custom":"Custom extension"}

def generate(intake:dict, discovery:dict|None=None):
    b=intake.get("business",{}); ops=intake.get("operations",{}); systems=intake.get("systems",{}); privacy=intake.get("privacy",{})
    mods=[MODULE_MAP.get(x,x) for x in intake.get("modules",[])]
    integrations=[]
    for category,values in systems.items():
        for value in values or []: integrations.append({"category":category,"system":value,"status":"needs_connection_review"})
    observed=[]
    if discovery:
        for p in discovery.get("pages",[]):
            if p.get("title"): observed.append({"type":"public_page","url":p.get("url"),"title":p.get("title")})
        for a in discovery.get("brand_asset_candidates",[]): observed.append({"type":"brand_asset_candidate",**a})
    blockers=[]
    if integrations: blockers.append("Provider connections and credentials require explicit authorization before deployment.")
    if not b.get("jurisdiction"): blockers.append("Jurisdiction/regulatory configuration requires confirmation.")
    return {
      "schema_version":1,"generated_at":datetime.now(timezone.utc).isoformat(),"profile_id":intake.get("profile_id"),
      "executive_summary":f"Proposed JackKnife operating environment for {b.get('company_name','client')}, tailored to {b.get('industry','their business')}.",
      "confirmed":{"business":b,"operations":ops,"privacy":privacy,"selected_capabilities":mods},
      "observed_public_evidence":observed,"integration_plan":integrations,
      "recommended_architecture":{"model":"JackKnife core + capability modules + business adapter + client configuration + optional extension layer",
        "infrastructure_preference":privacy.get("infrastructure_preference","needs_confirmation"),
        "automation_level":privacy.get("automation_level","needs_confirmation")},
      "human_decisions_and_blockers":blockers,
      "next_gate":"OPERATOR_REVIEW"
    }
