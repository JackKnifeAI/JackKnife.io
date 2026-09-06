# JackKnife automated customer lifecycle — readiness

## Implemented
- Public JackKnife pricing can create a Stripe Checkout session once Stripe env configuration exists.
- Signed Stripe webhook is the only payment authority; paid checkout creates an idempotent isolated client profile.
- 24-hour onboarding sessions, versioned intake, explicit public-discovery consent, and per-client workspaces.
- Durable agent-job queue with retries and dependency DAGs.
- Discovery analysis, business architecture, integration planning, optional provider-neutral model advisory, manifest compilation, and operator review.
- Separate blueprint approval and execution approval with tamper-evident audit chains.
- Deployment planning agents for infrastructure, branding, integrations, validation, and client acceptance.
- Safe execution preflight agents for local workspace/config preparation, preflight smoke checks, and rollback planning.
- External infrastructure/integration actions require explicit authorization references and completion evidence.
- One-time, 7-day client acceptance links; acceptance is allowed only after live validation.
- Durable daily intelligence store with dated briefs, normalized sourced findings, confidence, supersession, competitor deltas, and automation ingestion.
- Systemd and reverse-proxy deployment examples; runtime/client state excluded from source control.

## Intentionally blocked until external setup exists
- Live Stripe product/price IDs, banking/payout verification, and production webhook secret.
- Production hostname/TLS/reverse proxy and deployment target.
- Real infrastructure provider executor(s).
- Provider-specific OAuth/credential connector implementations selected per customer.
- Live DNS/telephony/email/accounting actions; these remain explicit human/provider authorization gates.
- Real client acceptance cannot occur until live smoke/rollback evidence exists.

## Security invariants
- Browser cannot assert payment state.
- Model advisory cannot authorize or execute actions.
- Public website discovery does not authorize access to authenticated systems.
- Raw credentials are not written into client manifests or durable intelligence.
- Execution state cannot reach LIVE without infrastructure evidence, integration completion/waiver, live validation evidence, and one-time client acceptance.
