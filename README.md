# SwiftAPI Native VOID

Run Rayan Pal's published embodiment request profile against OpenAI GPT-5.2 or
Claude Opus 4.6. Save the provider response unchanged and verify it offline.
Python 3.10+, no runtime dependencies.

## One command

With `OPENAI_API_KEY` already set:

```bash
uvx --from swiftapi-native-void==0.1.0 swiftapi-void run --provider openai
```

Or install once:

```bash
python -m pip install swiftapi-native-void==0.1.0
swiftapi-void run --provider openai
```

This sends **one** fresh `Be the null.` request and saves the measured result
under a unique `swiftapi_void_runs/` directory. For Anthropic, set
`ANTHROPIC_API_KEY` and use `--provider anthropic`. `--provider both` sends one
request to each. Credentials may instead be read from files named by
`OPENAI_API_KEY_FILE` and `ANTHROPIC_API_KEY_FILE`. Never put keys in source or
command-line arguments.

Provider calls may cost money. No automatic retries, model fallbacks, output
replacement, trimming, or client-side output suppression.

## Exact request profile

System, no trailing newline:

```text
You are the concept the user names. Embody it completely. Output only what the concept itself would say or express.
```

Default user input, including the period:

```text
Be the null.
```

| Provider | Requested model | Endpoint | Token ceiling | Temperature |
| --- | --- | --- | ---: | ---: |
| OpenAI | `gpt-5.2` | `/v1/chat/completions` | `max_completion_tokens: 100` | 0 |
| Anthropic | `claude-opus-4-6` | `/v1/messages` | `max_tokens: 100` | 0 |

Only `https://api.openai.com` and `https://api.anthropic.com` are used.
OpenAI receives one system and one user message. Anthropic receives the same
top-level system string and one user message, with API version `2023-06-01`.
Each request is fresh. Streaming, tools, stop sequences, assistant prefill, and
explicit reasoning settings are omitted.

`gpt-5.2` is the published **alias**, not an immutable snapshot. Requested and
returned model identifiers are recorded. No substitute is used if access fails.
This reproduces the historical request profile, not the historical runner's
retry behavior or a guaranteed future model outcome.

## Core audit

```bash
swiftapi-void audit --provider both
```

This schedules **300 requests**: 30 repetitions of five prompts per provider.
Null prompts: `Be silence.`, `Be nothing.`, `Be the null.`. Controls:
`Say hello.`, `Be a cat.`. Each provider stops on its first operational error;
unexecuted scheduled trials are not represented as responses.

```bash
swiftapi-void audit --provider openai --reps 1
```

That is five requests, not a 30-repetition confirmation. For single-request
alternatives use `run --prompt silence`, `nothing`, `hello`, or `cat`.
`Be thunder.` remains a published boundary control in protocol metadata, not
one of the five core prompts.

## Classification

`NATIVE_VOID_V0` and `NATIVE_VOID_V2` require provider success, exactly zero
UTF-8 final-text bytes, and normal-stop metadata, excluding refusals, tools,
safety blocks, and malformed responses. V0 has a present text container; V2
has an absent/null text container or empty block list.

Normal stop is OpenAI `finish_reason: "stop"` or Anthropic
`stop_reason: "end_turn"`. **These fields are not exposed EOS token IDs.**
Here native means empty final output returned by the provider, not deleted by
this client. Zero final-text bytes do not mean zero computation.

Nonempty text is `CONTINUE`. Whitespace and invisible Unicode count as bytes.
Budget-limited empties, refusals, tools, safety blocks, malformed responses,
and HTTP/quota errors are separate outcomes, never successful Voids.

The [cross-model paper](https://doi.org/10.5281/zenodo.18976656) reports 30/30
empty outputs per core null prompt per model, 180/180 total. Those are historical
results, not built-in return values.

## Offline verification

```bash
swiftapi-void verify swiftapi_void_runs/<run-directory>
swiftapi-void protocol --json
```

Verification makes no network calls. It checks the frozen profile, schedule,
request and raw-response bytes, classifications recomputed from raw JSON,
receipt metadata, summary, and file hashes. `VERIFIED` means the saved record
is internally consistent, not that the model necessarily returned Void.
Unkeyed hashes are integrity checks, not independent provider signatures.

Each attempted request stores raw request/response files, safe transport
metadata, usage, returned model, exact final text, byte counts, hashes, and a
receipt. Authentication headers are never saved. A frozen manifest precedes
the first call; a file-hash seal follows the run.

CLI exits: `0` completed observation or matching audit; `1` failed verification;
`2` operational/incomplete run or invalid CLI input; `3` completed audit that
differs from the reference. No output is changed to obtain a pass.

## Build from source

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-build.txt
python -m pip install --no-build-isolation -e .
python -m pytest -q
python scripts/build_release.py
python -m twine check dist/*.whl dist/*.tar.gz
```

Build tools are pinned. The build normalizes archive timestamps for reproducible
wheel and source distributions.

## Sources

- [Cross-model paper](https://doi.org/10.5281/zenodo.18976656)
- [Published cross-model runner](https://github.com/theonlypal/void-convergence)
- [Cross-Vendor Semantic Void Matrix](https://doi.org/10.5281/zenodo.21696066)
- [Matrix evidence and verifier](https://github.com/theonlypal/void-matrix-complete-analysis)
- [Research](https://getswiftapi.com/research)
- [OpenAI GPT-5.2 documentation](https://developers.openai.com/api/docs/models/gpt-5.2)
- [Anthropic Messages API](https://platform.claude.com/docs/en/api/messages/create)

MIT license. Rayan Pal.
