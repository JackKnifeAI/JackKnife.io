# JackKnife durable intelligence

Daily research is stored as immutable dated brief JSON plus normalized SQLite facts. Findings carry source IDs, confidence, status, and optional supersession links so newer research can replace stale claims without erasing history.

The research agent must cite current sources in the human brief and ingest only sourced claims. Model speculation belongs in implications/recommended actions, never as factual findings. Competitor pricing and capabilities are re-verified rather than copied forward from old briefs.

Usage: run `python3 -c "from intelligence.store import ingest; import json; ingest(json.load(open('brief.json')))"` from the JackKnife-Site root after producing a schema-compatible brief.
