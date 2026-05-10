#!/usr/bin/env bash
# 5-pass eval over a chosen scenarios file (held-out variant).
# Usage: bash scripts/run_5pass_heldout.sh <role> [model_name]
set -euo pipefail
cd "$(dirname "$0")/.."
ROLE="$1"
MODEL="${2:-}"

PYTHON=./.venv/bin/python
SCEN=eval/scenarios_validation.json

for PASS in 1 2 3 4 5; do
  SEED=$((2000 + PASS))
  echo "=== ${ROLE} held-out pass ${PASS} (seed=${SEED}) ==="
  if [ -n "$MODEL" ]; then
    AGENT_SEED=$SEED $PYTHON -u scripts/run_baselines.py --role "$ROLE" --model "$MODEL" \
      --scenarios "$SCEN" --suffix ".heldout.pass${PASS}"
  else
    AGENT_SEED=$SEED $PYTHON -u scripts/run_baselines.py --role "$ROLE" \
      --scenarios "$SCEN" --suffix ".heldout.pass${PASS}"
  fi
done
echo "ALL ${ROLE} HELD-OUT 5 PASSES DONE"
