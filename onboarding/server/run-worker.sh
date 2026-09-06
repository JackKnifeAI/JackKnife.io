#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
exec python3 -m onboarding.server.agent_worker
