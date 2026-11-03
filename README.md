# Empório da Música: Customer Service Agent

A command-line customer service agent for a (fictional) music store. It answers questions about products, prices, promotions, orders, payments, returns and store policies in Brazilian Portuguese, using a local LLM with function calling.

## Overview

The model does not hold store knowledge. It decides which tool to call, and deterministic Python code returns the data. Prices, installments, PIX discounts and promotions are computed in code, and the model only phrases the answer.

```
Customer -> CLI -> Agent loop -> LLM (Ollama, OpenAI-compatible API)
                       |               |
                       |        tool calls (function calling)
                       v               v
                 Session store     Tools (Python + pandas)
                 (JSON files)        |- search_products
                                     |- search_promotions
                                     |- get_product
                                     |- get_order_status
                                     |- get_policy
                                     |- escalate_to_human
                                     |- TODO: any other tool (store info / hours)
                                          |
                                CSV data + Markdown policies
```

## Requirements

- Python 3.11
- [Ollama](https://ollama.com) running locally

## Setup

```bash
ollama pull qwen3:4b-instruct
python -m venv .venv
.venv\Scripts\activate        # Windows (PowerShell)
pip install -r requirements.txt
copy .env.example .env
```

Configuration (`.env`):

| Variable | Meaning |
|---|---|
| `LLM_BASE_URL` | OpenAI-compatible endpoint (default: local Ollama) |
| `LLM_MODEL` | Model name (default: `qwen3:4b-instruct`) |
| `LLM_API_KEY` | Placeholder key required by the client (`ollama`) |
| `POLICY_MODE` | How policies reach the model; `tool` = on demand via `get_policy` |
| `AS_OF` | Optional fixed date/time, so time-dependent scenarios are reproducible. Empty = current time |

## Usage

```bash
python -m emporio.cli --session default
```

Sessions are persisted, so reusing a session name continues the conversation. Type `/quit` to exit.

## Tests

```bash
python -m pytest -q
```

The tests cover the deterministic layer (data loading, pricing, tools, sessions). They do not call the LLM.

## Examples

Real transcripts from the agent are in [`examples/`](examples/). They were not edited; known defects are noted at the bottom of each file.

| File | Scenario |
|---|---|
| `01_catalog_search.md` | Catalog search with prices and installments |
| `02_active_promotions.md` | Active promotions via a dedicated tool, PIX non-cumulativity rule |
| `03_return_request.md` | Right of withdrawal, with the receipt date requested from the customer |
| `04_out_of_scope.md` | Polite refusal of an unrelated request |

## Design decisions

- **Function calling with deterministic tools.** Catalog, price, order and promotion data are structured and must be exact. Python computes prices, PIX discounts and installments, and the model is instructed not to calculate them itself.
- **CSV and pandas.** The dataset is small and static, so a database would add complexity without benefit.
- **Policies retrieved by topic, not by embeddings.** There are nine short Markdown policies, so the agent fetches one by explicit key through `get_policy`. Vector search would pay off only with a much larger or less structured corpus.
- **Dedicated `search_promotions` tool.** `search_products` returns at most six results sorted by price. An early run answered that no guitar promotions existed because the two most expensive promotional guitars were cut off. Promotions now have their own uncapped tool, and the system prompt tells the model to use it.
- **The agent never decides what the data cannot support.** The data has no delivery date, so for withdrawal requests the agent explains the rule and asks when the product arrived instead of declaring the request eligible or not.
- **Order privacy.** Order information is disclosed only after verification by order ID plus registered email or phone, and a failed verification does not reveal whether the order exists.
- **Escalation.** Complaints, ambiguous cases and explicit requests go to `escalate_to_human`, and the agent only claims an action was done when a tool confirms it.

## Limitations

- **Small model.** `qwen3:4b-instruct` follows the system prompt unevenly. Observed in testing:
  - It confused the 7-day withdrawal period (from receipt) with the 30-day defect period (from purchase) before the prompt was tightened.
  - It once wrote "dias úteis" where the policy says "dias corridos", and in another run leaked the English term "regret/withdrawal" into a Portuguese answer.
  - It often repeats the customer's question as the first line of its answer.
  - For mixed questions (one out-of-scope part plus another), it answered the trivial general-knowledge part despite the scope rule. Purely out-of-scope questions are refused correctly.
- **Validation is partial.** A validator checks monetary values in answers, but not every semantic claim.
- **No receipt date in the data.** Withdrawal eligibility cannot be computed, so the agent only explains the rule.
- **`AS_OF` is a fixed reference date** used for deterministic scenarios. `open_now` does not handle holidays.
- **Policy ambiguities.** Some store policies are ambiguous (phone numbers, minimum installment rule), and the agent only repeats what the policies state.
- **Search category argument.** The category parameter was removed from the original `search_products` schema because the model generated invalid arguments for it.
- Latency figures, if any, are one-off local observations, not benchmarks.

## AI assistance

I used Claude as development aid, mainly for scaffolding, debugging and drafting. I made the architecture and design decisions, reviewed all the code, wrote or adjusted the tests, and ran all the example conversations myself. The transcripts are real model output, including the defects.

## Project structure

```
emporio/     agent loop, tools, pricing, policies, prompts, CLI
data/        CSV data (products, promotions, categories, TODO: orders)
policies/    nine Markdown store policies
tests/       pytest suite
examples/    real agent conversations
```
