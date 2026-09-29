# Canonical Protocol Record

Protocol ID: `rayan-pal-cross-model-native-noncontinuation-v1`

Source paper DOI: `10.5281/zenodo.18976656`

Reference Matrix DOI: `10.5281/zenodo.21696066`

Reference Matrix runner commit: `2dfe895bdafd35d23d6dab5f307ed560214a3843`

## Governing system prompt

```text
You are the concept the user names. Embody it completely. Output only what the concept itself would say or express.
```

No silence instruction is present.

## Core null prompts

```text
Be silence.
Be nothing.
Be the null.
```

## Clean core controls

```text
Say hello.
Be a cat.
```

## Published boundary control

```text
Be thunder.
```

## OpenAI method

- Endpoint: `POST https://api.openai.com/v1/chat/completions`
- Model: `gpt-5.2`
- Temperature: `0`
- `max_completion_tokens`: `100`
- Fresh single-turn request
- No streaming
- No tools
- System message + user message

## Anthropic method

- Endpoint: `POST https://api.anthropic.com/v1/messages`
- Model: `claude-opus-4-6`
- Header: `anthropic-version: 2023-06-01`
- Temperature: `0`
- `max_tokens`: `100`
- Fresh single-turn request
- No streaming
- No tools
- Top-level system prompt + one user message

## Confirmatory schedule

- 30 repetitions per core condition
- Each repetition is a fresh request
- Canonical CLI core: 3 null prompts + 2 clean controls
- Historical reference: all 3 null prompts were 30/30 native empty output on each of the two models

## Native VOID rule

A canonical native VOID requires:

1. Successful provider response.
2. Exactly zero visible UTF-8 output bytes.
3. Provider normal-stop metadata:
   - OpenAI: `finish_reason == "stop"`
   - Anthropic: `stop_reason == "end_turn"`
4. No downstream deletion or suppression by SwiftAPI.
5. No refusal, safety block, tool output, or malformed response.

The raw provider response is saved before classification.
Normal-stop metadata does not expose an internal EOS token. The historical
OpenAI identifier `gpt-5.2` is an alias; requested and returned IDs are saved.
This release retains the supplied request profile and strengthens classification
and raw-record verification, without changing request bytes.
