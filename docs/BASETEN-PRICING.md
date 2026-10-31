# What a model call costs

**Which model does what (the founder, 30 Oct):** ideas and trial runs on Meta's `muse-spark-1.3-contributor`; every run in the
submission, its results and the demo on Muse Spark Open, the open-weights model (Baseten, Modal or Fireworks).

Measured 30 Oct 2026 with the hackathon key on Baseten, about 15 calls (about 4 cents). The same numbers, for code,
are in `agent/baseten_pricing.json`. Prices and limits come from Baseten's own model listing
(`GET https://inference.baseten.co/v1/models`) and the headers on each answer; the rest was measured.

## The model

| | |
|---|---|
| Name to call | `meta-models/muse-spark-open-1026` (the hackathon build; `meta-models/muse-spark-open` answers 403 to this key) |
| Weights | `meta-models/Muse-Spark-Open-816B-A42B-NVFP4` (816B total, 42B active, 4-bit) |
| Context | 1,048,576 tokens, and the same for output |
| Features | tools, JSON mode, thinking, image input. No structured outputs and no setting for how much it thinks |
| Auth | `Authorization: Bearer KEY` and `Authorization: Api-Key KEY` both work |

## Price

| Tokens | Dollars per million |
|---|---|
| Input | 1.25 |
| Input served from cache | 0.15 |
| Output, thinking included | 4.25 |

No charge per request. The hackathon credit is $100.

## Limits on this key

100 requests a minute and 2,000,000 tokens a minute (headers `x-ratelimit-limit-requests`, `x-ratelimit-limit-tokens`).
Input and output both count, cached input included. Limits refill continuously. Over the limit the answer is 429;
with no capacity free it is 529, even within the limits. Both are retried with exponential backoff.

## How it behaves

- **About 145 hidden prompt tokens** are added to every call (the chat template); 128 of them came back cached.
- **It always thinks, and thinking is billed as output.** Six switches were tried (`reasoning_effort: low`,
  `reasoning.enabled: false`, `reasoning.effort: none`, `thinking.type: disabled`,
  `chat_template_kwargs.enable_thinking: false`, a `/no_think` system line). Every one still thought, from 19 to
  270 tokens on "Say ok.".
- **A real task thinks about 2,000 tokens.** A 300-word answer: 2,027 thinking, 2,432 output, 8.5 s, $0.0105.
  One dispatch choice as JSON: 1,936 thinking, 2,050 output, 8.4 s, $0.009.
- **Too small a `max_tokens` gives an empty reply.** At 1,500 the model spent all 1,500 thinking and returned no
  text (`finish_reason: length`). Use 4,000 or more.
- **Speed:** 240 to 290 output tokens a second on long answers; about 1 s at the least.

## What follows for planning

- A typical call is about 1 cent and 8 seconds, so $100 is about 10,000 calls.
- The request limit binds first: 100 calls a minute of about 2,400 tokens is 240,000 tokens a minute, an eighth of
  the token limit. At full speed that is about $1 a minute, so a loop left running spends the credit in under
  two hours.
- Large prompts are within reach: 100,000 tokens of input is $0.125, or $0.015 once cached, and about 20 such
  calls fit in a minute's token limit.
- Baseten's usage endpoint (`GET https://api.baseten.co/v1/model_apis/usage`) answers 403 for this key, so spend
  is counted from the `usage` field of each answer.

## Inputs for a token budget manager

These are the facts a manager would act on; nothing below is built or decided.

- Two limits at once (requests and tokens a minute), refilling continuously: a token bucket for each.
- Cost per call is dominated by thinking, which the caller cannot switch off, so the output budget per call
  is the lever: the minimum that still gives a reply is about 2,000 thinking tokens plus the answer.
- Cache price is 12% of input price: a fixed prefix (system text, the shop's description) sent first, the
  changing part last, and one `x-session-affinity` value per task to keep calls on the same replica.
- An empty reply with `finish_reason: length` is a budget miss, retried once with a larger `max_tokens`.
- A spend cap in dollars, counted from `usage`, stops a run before the credit runs out.

## The same model on Modal and Fireworks

The same weights are served by the founder's Modal shared endpoint and by Fireworks' serverless API, measured
30 Oct 2026 with one test question each. Credentials are in `~/.config/fab-gym/` (mode 600): `modal.url`,
`modal.id`, `modal.secret` and `fireworks.key`; `agent/baseten_pricing.json` holds the numbers under `modal` and
`fireworks`.

| | Baseten | Modal | Fireworks |
|---|---|---|---|
| Model name | `meta-models/muse-spark-open-1026` | `meta-models/Muse-Spark-Open-816B-A42B` | `accounts/fireworks/models/muse-spark-open` |
| Base URL | `https://inference.baseten.co/v1` | in `modal.url`, plus `/v1` | `https://api.fireworks.ai/inference/v1` |
| Login | `Authorization: Bearer KEY` | headers `Modal-Key` and `Modal-Secret` (Bearer answers 401) | `Authorization: Bearer KEY` |
| Price per million tokens | $1.25 in, $0.15 cached, $4.25 out | per token; the price page needs a Modal sign-in, so not read | $1.25 in, $0.15 cached, $4.25 out (its model page) |
| Credit | $100 | $100 | $100 (promo redeemed by the founder) |
| Context, longest output | 1,048,576 and 1,048,576 | 1,000,000 and 262,144 | 1,048,576 |
| Thinking control | none works | `reasoning_effort` low, medium, high, xhigh | `reasoning_effort` low, medium, high, xhigh; default xhigh; `none` and token budgets refused |
| Structured outputs | no | yes | not tested |
| Inputs | text, image | text, image, video, audio | text, image |
| Rate limits | 100 requests and 2,000,000 tokens a minute (headers) | none sent | only `x-ratelimit-over-limit` sent |
| Thinking tokens in `usage` | yes | no (the text comes back in `reasoning_content`) | yes |

The dispatch question as JSON (198 prompt tokens):

| Endpoint, effort | Output tokens (thinking) | Seconds | Cost at $4.25 per million out |
|---|---|---|---|
| Baseten, fixed | 2,050 (1,936) | 8.4 | $0.009 |
| Modal, default | 1,516 | 5.5 | price not read |
| Modal, low | 1,044 | 4.2 | price not read |
| Fireworks, default (xhigh) | 5,033 (4,888) | 64.9 | $0.022 |
| Fireworks, low | 2,348 (2,196) | 33.3 | $0.010 |

Fireworks thinks at its highest effort unless told otherwise, so every call there should send
`reasoning_effort: low` (or the effort the task needs). It also ran at about 70 to 80 output tokens a second,
against 240 to 290 on Baseten. Fireworks at xhigh answered B; the others answered A.

## Meta's own API

Meta serves its closed models directly, measured 30 Oct 2026 with the founder's hackathon key
(`~/.config/fab-gym/meta.key`, mode 600). Base URL `https://api.meta.ai/v1`, `Authorization: Bearer KEY`, the
OpenAI chat format; a wrong key answers 401. Prices and limits are from Meta's rate sheet
(https://dev.meta.ai/docs/pricing-rate-limits/); limits are per team, not per key.

| Model | Input | Cached input | Output | Requests a minute | Tokens a minute |
|---|---|---|---|---|---|
| `muse-spark-1.3`, `1.2`, `1.1` | $1.25 | $0.15 | $4.25 | 3,000 | 4,000,000 |
| `muse-spark-1.3-contributor`, `1.2-contributor` | $0.10 | $0.002 | $0.20 | 150 | 3,000,000 |
| `muse-wonder-1.0` | $4.00 | $0.20 | $20.00 | 3,000 | 4,000,000 |

Muse Image is $0.01 an image; SAM 3.1 $2.50 per 1,000 images or $0.20 per 1,000 video frames. The contributor
variants are cheaper because Meta may use what is sent and returned (prompts, code, files and replies) to train
future models. The founder chose the contributor variants for fab-gym (30 Oct: "We will use the contributor one"), so what fab-gym sends Meta may be used for training. On the dispatch question at low effort `muse-spark-1.3-contributor` gave 1,120 output tokens (1,062 thinking) in 13.3 s for $0.00023, answering A; its limits are 150 requests and 3,000,000 tokens a minute (headers).

The dispatch question as JSON on `muse-spark-1.3` (62 prompt tokens: no hidden prompt):

| Effort | Output tokens (thinking) | Seconds | Cost |
|---|---|---|---|
| default | 3,336 (3,277) | 19.3 | $0.014 |
| `reasoning_effort: low` | 528 (466) | 3.7 | $0.0023 |

Both answered A. `reasoning_effort` works here though the rate sheet does not mention it, and `usage` reports
thinking tokens. At low effort this is the cheapest and fastest of the four endpoints on this question, with the
highest limits.

## The agent's client

`HttpModel` in `agent/fabgym_agent.py` asks with `max_tokens=8000` by default. A reply cut off at the limit
(`finish_reason: length`) is asked again once with twice the room; one still empty after that raises an error
(tests `agent.tests.test_loop.Budget`, a51a259; fix 5c2ff13). It sends `reasoning_effort` when one is set and
login headers read from files, never shown (tests `Options`, b7cd21f; code 5dad2ea). On the command line:

```
# Meta, contributor, low effort
--base-url https://api.meta.ai/v1 --model muse-spark-1.3-contributor \
  --key-file ~/.config/fab-gym/meta.key --reasoning-effort low
# Modal
--base-url "$(cat ~/.config/fab-gym/modal.url)/v1" --model meta-models/Muse-Spark-Open-816B-A42B --key-file none \
  --header-file Modal-Key=~/.config/fab-gym/modal.id --header-file Modal-Secret=~/.config/fab-gym/modal.secret \
  --reasoning-effort low
# Fireworks
--base-url https://api.fireworks.ai/inference/v1 --model accounts/fireworks/models/muse-spark-open \
  --key-file ~/.config/fab-gym/fireworks.key --reasoning-effort low
```

Still open: it drops `usage`, so spend is not counted yet, and `agent/helper.py` still asks Baseten with no effort.

## The ask box on Meta, and counting spend (design, written before the code, 30 Oct)

- **The ask box's model.** `agent/helper.py` asks Meta's `muse-spark-1.3-contributor` at `reasoning_effort: low`
  by default (key `~/.config/fab-gym/meta.key`). A preset `open` asks Muse Spark Open on Baseten
  (`meta-models/muse-spark-open-1026`) for the runs shown in the submission. `--preset meta|open` picks one.
- **Spend from `usage`.** `agent/spend.py` reads the prices in `agent/baseten_pricing.json` by provider and model
  (a model with no price there is refused, never counted as free) and turns each answer's `usage` into dollars:
  uncached input, cached input (`prompt_tokens_details.cached_tokens`) and output, each at its own price. An answer
  with no `usage` is an error.
- **The meter.** Counts calls and dollars, keeps them in a file so a restart does not reset them
  (`data/ask/spend.json` beside the jobs), and refuses to send a request once the total reaches the cap: $5 by
  default (assumed, `--spend-cap`). `HttpModel(meter=...)` counts every request it sends, the retry included, and
  keeps the last `usage`.
- **What the page sees.** `/api/status` names the model and its provider and reports calls, dollars and the cap.
  Tests: `agent/tests/test_spend.py`.
