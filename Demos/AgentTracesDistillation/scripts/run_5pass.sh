#!/usr/bin/env bash
# 5-pass eval with explicit AGENT_SEED per pass for reproducibility checking.
# Run with: bash scripts/run_5pass.sh <role> <model_name>
set -euo pipefail
cd "$(dirname "$0")/.."
ROLE="$1"
MODEL="${2:-}"

PYTHON=./.venv/bin/python
SCEN=eval/scenarios_train.json

# Each pass uses a distinct seed. With seed pinned, repeating the same pass
# should yield identical results modulo Azure provider routing.
for PASS in 1 2 3 4 5; do
  SEED=$((1000 + PASS))
  echo "=== ${ROLE} pass ${PASS} (seed=${SEED}) ==="
  if [ -n "$MODEL" ]; then
    AGENT_SEED=$SEED $PYTHON -u scripts/run_baselines.py --role "$ROLE" --model "$MODEL" \
      --scenarios "$SCEN" --suffix ".pass${PASS}" --verbose
  else
    AGENT_SEED=$SEED $PYTHON -u scripts/run_baselines.py --role "$ROLE" \
      --scenarios "$SCEN" --suffix ".pass${PASS}" --verbose
  fi
done
echo "ALL ${ROLE} 5 PASSES DONE"
