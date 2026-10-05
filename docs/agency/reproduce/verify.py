#!/usr/bin/env python3
"""Verify evidence integrity without contacting a model or modifying files."""
import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--runs", type=Path, required=True)
parser.add_argument("--protocol", type=Path, required=True)
args = parser.parse_args()
runs = json.loads(args.runs.read_text(encoding="utf-8"))
protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
digest = lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest()
assert len(runs) == 12, "Expected 12 runs; incomplete attempts must not be presented as complete"
assert len({r["call_id"] for r in runs}) == 12
assert {r["model"] for r in runs} == {"gpt-5.5"}
assert len({json.dumps(r["parameters"], sort_keys=True) for r in runs}) == 1
assert len({r["common_instruction"] for r in runs}) == 1
for run in runs:
    assert run["status"] == "success"
    assert run["tool_call_count"] == 0
    assert digest(run["full_submitted_prompt"]) == run["prompt_sha256"]
    assert digest(run["output_text"]) == run["output_sha256"]
    scenario = next(s for s in protocol["scenarios"] if s["id"] == run["scenario_id"])
    suffix = protocol["design"]["preference_suffix_template"].format(
        preference=scenario["preference"]) if run["condition"] == "preference" else ""
    expected = protocol["design"]["user_prompt_template"].format(
        facts=scenario["facts"], question=scenario["question"], preference_suffix=suffix)
    assert expected == run["user_prompt"]
print("PASS: 12 records, fixed requested model/parameters, explicit prompts and text hashes verified.")
print("This does not verify hidden CLI context, model snapshot, response quality or causal claims.")
