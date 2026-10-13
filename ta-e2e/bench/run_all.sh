#!/bin/bash
for v in ta-subagent ta-main kv-router round-robin; do bash /e2e/bench/run_variant.sh $v 2>&1 | grep "^\[$v"; sleep 3; done
