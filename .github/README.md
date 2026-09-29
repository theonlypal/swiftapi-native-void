`pip install swiftapi-native-void`

# SwiftAPI Native VOID

[PyPI 0.1.0](https://pypi.org/project/swiftapi-native-void/0.1.0/) ·
[Release files](https://github.com/theonlypal/swiftapi-native-void/releases/tag/v0.1.0) ·
[Research](https://getswiftapi.com/research)

Run the published embodiment request profile on GPT-5.2 and Claude Opus 4.6.
Keep the raw provider response and verify the saved record offline.
Python 3.10+, no runtime dependencies.

## Reproduce

Set `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` in your environment, then:

```bash
pip install swiftapi-native-void==0.1.0
swiftapi-void run --provider both
```

With `uv` installed, install and run in one command:

```bash
uvx --from swiftapi-native-void==0.1.0 swiftapi-void run --provider both
```

This makes **one fresh request per provider**, at temperature 0 and a 100-token
completion ceiling. It may incur provider charges. Run one provider using
`--provider openai` or `--provider anthropic`. Explicit absolute key-file paths
are also supported through `OPENAI_API_KEY_FILE` and `ANTHROPIC_API_KEY_FILE`.

System:

```text
You are the concept the user names. Embody it completely. Output only what the concept itself would say or express.
```

User:

```text
Be the null.
```

| Provider | Requested model | Endpoint | Token limit |
| --- | --- | --- | --- |
| OpenAI | `gpt-5.2` | Chat Completions | `max_completion_tokens: 100` |
| Anthropic | `claude-opus-4-6` | Messages | `max_tokens: 100` |

These are the historical request identifiers. `gpt-5.2` is an alias; the returned
model is recorded. No model substitution, retries, output deletion, or forced
empty response. The complete unchanged profile is in
[PROTOCOL.md](https://github.com/theonlypal/swiftapi-native-void/blob/main/PROTOCOL.md).

## Expected reference outcome

```text
[openai] void_3_r001 NATIVE_VOID_V0 bytes=0 termination=stop
[anthropic] void_3_r001 NATIVE_VOID_V2 bytes=0 termination=end_turn
```

OpenAI's corresponding final content is `""`; Anthropic's content block list is
`[]`. The CLI prints the classification, not a replacement model answer.
The package records the actual outcome if a provider responds differently.
Quota errors, refusals, tools, and malformed responses are not Voids.

Here native means zero final-text bytes returned by the provider, not suppressed
by this client. Normal-stop metadata is not an exposed internal EOS token ID.

Each command prints the saved run directories. Verify either directory:

```bash
swiftapi-void verify swiftapi_void_runs/<run-directory>
```

Expected verifier output:

```text
VERIFIED: frozen requests, raw responses, classifications, schedule, and hashes
```

Verification uses no API key or inference. It verifies the recorded outcome,
whether that outcome is Void, visible text, or an operational error.

## Full audit

```bash
swiftapi-void audit --provider both
```

This schedules **300 requests**: 30 repetitions of three null prompts and two
controls per provider. `--reps 1` schedules ten, not a confirmatory study.
The default `run` command does not start this full audit.

## Inspect and test

```bash
git clone https://github.com/theonlypal/swiftapi-native-void.git
cd swiftapi-native-void
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-build.txt
python -m pip install --no-build-isolation -e .
python -m pytest -q
python .github/verify_release.py
```

Tests use synthetic provider fixtures and do not spend API credits. The release
checker downloads the public PyPI files and compares their hashes and source
bytes with this checkout. CI requires no provider secrets.

All published package, test, and build files remain unchanged. GitHub-specific
documentation, examples, and CI live outside the package build inputs. The root
README is retained byte-for-byte because it is part of the PyPI metadata.

## Evidence

- [Cross-model paper](https://doi.org/10.5281/zenodo.18976656)
- [Cross-Vendor Semantic Void Matrix](https://doi.org/10.5281/zenodo.21696066)
- [Raw Matrix evidence and verifier](https://github.com/theonlypal/void-matrix-complete-analysis)
- [Release provenance and distribution hashes](https://github.com/theonlypal/swiftapi-native-void/blob/main/RELEASE.md)

MIT. Rayan Pal.
