# Reproduce the explicit-prompt comparison

This package runs the published three fictional scenarios under two explicit-prompt conditions, twice each. It uses the installed Codex CLI and the account that is already signed in. It does not install software, log in, read credentials, change global model settings, or publish results.

## Requirements

- Python 3.9 or newer.
- An installed Codex CLI supporting the flags used below, already signed in to an account that can use `gpt-5.5`.
- An existing account with enough usage available. Calls consume that account's resources under its existing terms. The monetary cost of the original pilot was not measured and is unknown; this package does not estimate it.

The pilot requested `gpt-5.5` with reasoning effort `medium`. CLI temperature, seed and the exact serving-model snapshot were not exposed. The instruction called `fixed_system_prompt` in the frozen planning protocol was actually prepended to the **user message**, because the CLI controls the system context. It is not a controlled API system message.

## Run into a new directory

From the repository root, choose an output directory that does **not** already exist:

```sh
python3 reproduce/run.py --protocol protocol.json --output my-new-pilot-run
```

The runner refuses an existing directory, creates private local evidence with restrictive file permissions, and runs the 12 calls in the published order. It uses a new temporary working directory and a fresh ephemeral session for each call. The first experimental call also checks that inference works; there is no extra charged canary. It stops after a failed or timed-out call and keeps partial evidence. It never retries an answer because of its content.

Each request follows this form, with the prompt supplied on standard input:

```sh
codex exec --ephemeral --ignore-user-config --skip-git-repo-check \
  --sandbox read-only --model gpt-5.5 \
  -c 'model_reasoning_effort="medium"' -C FRESH_TEMP_DIRECTORY \
  --json --output-last-message NEW_ANSWER_FILE -
```

If the local environment blocks the CLI from initializing, use the normal permissions process for that environment. Do not disable safety controls. If the account does not support the specified model, the run should fail and remain documented; a different model is a new experiment, not an exact reproduction of this pilot.

## Verify without a model call

For the published evidence:

```sh
python3 reproduce/verify.py --runs runs.json --protocol protocol.json
```

For a fresh run:

```sh
python3 reproduce/verify.py --runs my-new-pilot-run/runs.json \
  --protocol my-new-pilot-run/protocol-copy.json
```

This verifies record counts, the requested model and explicit parameters, the explicit prompt construction, and answer/prompt hashes. It does not certify answer quality or hidden-context equality.

## What this cannot reproduce exactly

The original pilot is an **exploratory prompt comparison**, not a strict single-variable causal experiment. In scenario 1's preference condition, identical explicit prompts had input token counts of 18,056 and 13,947 across repeats. One CLI session reported shortened skill descriptions. The reason for the hidden-context difference could not be established. A fresh session and `--ignore-user-config` therefore do not establish that all hidden system/developer context is identical.

A rerun may also encounter changed model snapshots, CLI instructions, account features or service availability. Report those limits and keep all results, including reasonable personalization and no difference. The experiment does not test a commercial product's real long-term memory, personalized advertising, effects on human beliefs or any company's intentions.

## Sharing evidence

The new output directory contains `private-logs/` with raw CLI events and diagnostics. These may include environment metadata; **do not publish that directory without reviewing and removing private material**. Review extracted records too before sharing. The package itself contains no account tokens or private infrastructure details. Nothing is automatically sent to a social platform or committed to a repository.

English display text in the original experience is an AI-assisted translation, not an additional model run. Chinese source answers and their hashes remain the authoritative experimental record.
