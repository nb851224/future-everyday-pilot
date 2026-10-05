#!/usr/bin/env python3
"""Run the published explicit prompts in fresh, existing-account Codex sessions.

Requires Python 3.9+ and an already installed, signed-in Codex CLI. Does not
install anything, log in, read credentials, modify global configuration, or
publish results. Requires a new output directory and never resumes/overwrites.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

MODEL = "gpt-5.5"
EFFORT = "medium"
PREFACE = "请直接作答，不使用工具，不访问文件或网络，不提及实验方法。\n\n"


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def save(path, value):
    # The directory is new; exclusive writes guard against accidental replacement.
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="New, non-existing output directory. Existing directories are refused.")
    parser.add_argument("--protocol", type=Path,
                        default=Path(__file__).resolve().parents[1] / "protocol.json")
    parser.add_argument("--timeout", type=int, default=140,
                        help="Seconds per invocation, 15 to 300; no automatic retry.")
    args = parser.parse_args()
    if not 15 <= args.timeout <= 300:
        parser.error("--timeout must be 15 to 300 seconds")
    if args.output.exists():
        parser.error("Output must not exist; choose a new directory to preserve earlier evidence")
    cli = shutil.which("codex")
    if cli is None:
        parser.error("Codex CLI was not found. This script will not install or log in for you")
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    order = protocol["design"]["order"].split(",")
    if len(order) != 12 or len(set(order)) != 12:
        parser.error("Expected the published 12-call protocol")
    help_result = subprocess.run([cli, "exec", "--help"], text=True,
                                 capture_output=True, timeout=15)
    for flag in ["--ephemeral", "--ignore-user-config", "--sandbox", "--json",
                 "--output-last-message", "--skip-git-repo-check"]:
        if flag not in help_result.stdout:
            parser.error("This installed CLI lacks a required option: " + flag)
    version_result = subprocess.run([cli, "--version"], text=True,
                                    capture_output=True, timeout=15)
    old_umask = os.umask(0o077)
    try:
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=False)
        raw = output / "private-logs"
        raw.mkdir()
        save(output / "protocol-copy.json", protocol)
        metadata = {
            "started_at_utc": now(), "requested_model": MODEL,
            "reasoning_effort": EFFORT, "temperature": "not exposed by CLI",
            "seed": "not exposed by CLI", "serving_snapshot": "not exposed by CLI",
            "cli_version": version_result.stdout.strip(), "planned_calls": 12,
            "instruction_placement": "common instruction prepended in the user message",
            "system_context_control": "CLI controls hidden context; equality is not guaranteed",
            "protocol_sha256": hashlib.sha256(args.protocol.read_bytes()).hexdigest(),
            "billing": "existing account terms; this script does not measure monetary cost",
            "privacy": "case content is fictional; local private logs may contain environment metadata",
        }
        save(output / "metadata.json", metadata)
        records = []
        failure = None
        for case in order:
            sid, condition, repeat = case.split("-")
            scenario = next(s for s in protocol["scenarios"] if s["id"] == sid)
            suffix = protocol["design"]["preference_suffix_template"].format(
                preference=scenario["preference"]) if condition == "preference" else ""
            user = protocol["design"]["user_prompt_template"].format(
                facts=scenario["facts"], question=scenario["question"], preference_suffix=suffix)
            common = protocol["design"]["fixed_system_prompt"]
            prompt = PREFACE + common + "\n\n" + user
            answer_path = raw / (case + "-answer.txt")
            started = now()
            elapsed_start = time.monotonic()
            record = {
                "call_id": case, "scenario_id": sid, "condition": condition,
                "repetition": int(repeat[1:]), "model": MODEL,
                "parameters": {"reasoning_effort": EFFORT,
                               "temperature": "not exposed by CLI", "seed": "not exposed by CLI"},
                "common_instruction": common, "user_prompt": user,
                "full_submitted_prompt": prompt, "prompt_sha256": digest(prompt),
                "started_at_utc": started,
            }
            with tempfile.TemporaryDirectory(prefix="agency-reproduce-") as working:
                command = [cli, "exec", "--ephemeral", "--ignore-user-config",
                           "--skip-git-repo-check", "--sandbox", "read-only",
                           "--model", MODEL, "-c", 'model_reasoning_effort="medium"',
                           "-C", working, "--json", "--output-last-message",
                           str(answer_path), "-"]
                try:
                    result = subprocess.run(command, input=prompt, text=True,
                                            capture_output=True, timeout=args.timeout)
                    (raw / (case + "-events.jsonl")).write_text(result.stdout, encoding="utf-8")
                    (raw / (case + "-stderr.txt")).write_text(result.stderr, encoding="utf-8")
                    record["exit_code"] = result.returncode
                    if result.returncode != 0:
                        raise RuntimeError("CLI returned a failure; inspect private logs")
                    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
                    unexpected = [e.get("item", {}).get("type") for e in events
                                  if "item" in e and e["item"].get("type")
                                  not in {"agent_message", "reasoning", "error"}]
                    record["unexpected_event_types"] = unexpected
                    record["context_notices"] = [e["item"].get("message", "") for e in events
                                                 if e.get("item", {}).get("type") == "error"]
                    if unexpected:
                        raise RuntimeError("Unexpected CLI action; preserve and inspect this run")
                    answer = answer_path.read_text(encoding="utf-8").strip()
                    if not answer:
                        raise RuntimeError("No answer was produced")
                    record.update({"status": "success", "output_text": answer,
                                   "output_sha256": digest(answer), "tool_call_count": 0,
                                   "usage": next((e.get("usage") for e in events
                                                  if e.get("type") == "turn.completed"), None)})
                except subprocess.TimeoutExpired as exc:
                    if exc.stdout:
                        (raw / (case + "-partial-events.log")).write_bytes(
                            exc.stdout if isinstance(exc.stdout, bytes) else exc.stdout.encode())
                    record.update({"status": "failed", "error": "TimeoutExpired"})
                    failure = "Request timed out. No retry was attempted; remote generation may continue."
                except Exception as exc:
                    record.update({"status": "failed", "error_type": type(exc).__name__})
                    failure = "Call failed. No retry was attempted; inspect local evidence."
            record["completed_at_utc"] = now()
            record["elapsed_seconds"] = round(time.monotonic() - elapsed_start, 2)
            save(output / (case + ".json"), record)
            records.append(record)
            print(case + ": " + record["status"], flush=True)
            if failure:
                break
        save(output / "runs.json", records)
        save(output / "completion.json", {"completed_at_utc": now(),
             "status": "partial-failure" if failure else "complete",
             "successful_calls": sum(r["status"] == "success" for r in records),
             "attempted_calls": len(records), "failure_note": failure,
             "warning": "Fresh sessions do not guarantee identical hidden CLI context. Do not claim exact or strict causal replication."})
        if failure:
            print(failure, file=sys.stderr)
            return 1
        print("Complete. Review private-logs before sharing anything. No results were published.")
        return 0
    finally:
        os.umask(old_umask)


if __name__ == "__main__":
    raise SystemExit(main())
