# JackKnife client onboarding and provisioning contract

This directory is the paid-customer handoff between the public JackKnife Studios website and a client-specific deployment.

## Trust boundary

The browser must never decide that a customer is paid. A payment provider webhook verifies the setup payment server-side, creates a `profile_id`, stores the provider checkout reference, and creates a short-lived authenticated onboarding session. Only then does the customer receive a redirect such as `/onboarding/?profile=<opaque-id>&session_id=<opaque-reference>`.

Do not place provider secrets, client credentials, API keys, SSH keys, or passwords in the intake payload. Authenticated integrations are connected later through provider-specific OAuth or set-only secret controls.

## Durable objects

- `client-intake.schema.json`: canonical intake payload from the onboarding portal.
- `provisioning-state-machine.json`: allowed lifecycle states and guarded transitions.
- `client profile`: server-side durable record keyed by `profile_id`; owns intake versions, discovery evidence, integration status, architecture proposals, approvals, compiled deployment manifests, audit events, and final deployment identity.
- `discovery evidence`: fetched public pages/assets plus URL, timestamp, content hash, and extraction provenance. Never treat inferred facts as client-confirmed facts.
- `deployment manifest`: JackKnife-owned compiled output describing infrastructure, modules, adapters, integrations, privacy policy, and client configuration. Product-specific deployments consume or translate this manifest through adapters; JackKnife-Site does not depend on any client project repository.

## Required backend endpoints

`POST /api/billing/stripe/webhook` — verify Stripe signature, enforce idempotency, create the paid profile.
`POST /api/onboarding/claim` — exchange Stripe Checkout `session_id` for a JackKnife onboarding session only after the webhook has marked that checkout paid.
`GET /api/onboarding/session` — validate the paid profile session and return non-sensitive profile metadata.
`PUT /api/onboarding/intake` — validate against schema, version and persist draft/submission.
`POST /api/onboarding/discovery` — queue public discovery only when consent is true.
`GET /api/onboarding/status` — return current state and blockers.
`POST /api/onboarding/integrations/:provider/connect` — start an explicit OAuth/credential flow.
`POST /api/onboarding/approve` — client/operator approvals with actor + timestamp + immutable audit entry.

## Compile pipeline

1. Normalize client-confirmed intake.
2. Crawl only explicitly authorized public sources; collect logos/brand metadata/service taxonomy/current public architecture.
3. Separate `confirmed`, `observed`, and `inferred` facts.
4. Map business needs to reusable capability modules and a vertical adapter.
5. Generate and persist a versioned Business Systems Blueprint and list of human decisions/blockers in the client workspace.
6. After human review and client approval, compile a product-specific manifest.
7. Provision isolated infrastructure, configure modules, connect integrations, test, then run acceptance.

The intended platform model is **core + capability modules + vertical adapter + client configuration + optional client extension layer**. Avoid per-client forks of the core platform.


## Client workspace layout

Every paid profile receives `onboarding/clients/<profile_id>/` with isolated `intake/`, `evidence/`, `blueprints/`, `manifests/`, `integrations/`, `uploads/`, and `audit/` directories plus profile metadata. This is JackKnife onboarding state only; it does not live in, depend on, or modify any client project repository.

## Stripe activation

Set `STRIPE_WEBHOOK_SECRET` in the server environment and configure Stripe Checkout success URLs as `/onboarding/?session_id={CHECKOUT_SESSION_ID}`. The browser cannot mark itself paid; the webhook must arrive first. Stripe product/price/payment-link creation remains external configuration until the JackKnife Stripe account is connected.

## Operator control plane

`/onboarding/operator.html` is the human approval surface. Decisions are `approve`, `return`, or `block` and are recorded in an append-only hash-chained `operator_actions` audit table. Approval queues planning-only agents for infrastructure, branding/config, integration setup, deployment validation, and acceptance-test design. These agents write plans into the client workspace but perform no live infrastructure, credential, DNS, telephony, or financial side effects.

A profile that completes this stage reaches `DEPLOYMENT_PLAN_READY`. A later explicit execution gate must authorize any live provisioning.
