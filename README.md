# Peitho

[![CI](https://github.com/rohanvinaik/Peitho/actions/workflows/ci.yml/badge.svg)](https://github.com/rohanvinaik/Peitho/actions/workflows/ci.yml)
[![Quality gate](https://sonarcloud.io/api/project_badges/measure?project=rohanvinaik_Peitho&metric=alert_status&token=233dd3b2cc16d138e9bfeb0d460e2fa87960811c)](https://sonarcloud.io/summary/new_code?id=rohanvinaik_Peitho)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=rohanvinaik_Peitho&metric=coverage&token=233dd3b2cc16d138e9bfeb0d460e2fa87960811c)](https://sonarcloud.io/summary/new_code?id=rohanvinaik_Peitho)
[![Maintainability](https://sonarcloud.io/api/project_badges/measure?project=rohanvinaik_Peitho&metric=sqale_rating&token=233dd3b2cc16d138e9bfeb0d460e2fa87960811c)](https://sonarcloud.io/summary/new_code?id=rohanvinaik_Peitho)
[![Reliability](https://sonarcloud.io/api/project_badges/measure?project=rohanvinaik_Peitho&metric=reliability_rating&token=233dd3b2cc16d138e9bfeb0d460e2fa87960811c)](https://sonarcloud.io/summary/new_code?id=rohanvinaik_Peitho)
[![Security](https://sonarcloud.io/api/project_badges/measure?project=rohanvinaik_Peitho&metric=security_rating&token=233dd3b2cc16d138e9bfeb0d460e2fa87960811c)](https://sonarcloud.io/summary/new_code?id=rohanvinaik_Peitho)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![type checked: ty](https://img.shields.io/badge/type%20checked-ty-261230?labelColor=grey)](https://github.com/astral-sh/ty)
[![Behavior: mutation-pinned](https://img.shields.io/badge/behavior-mutation--pinned-8A2BE2)](#development)
[![Zero runtime deps](https://img.shields.io/badge/runtime%20deps-0-brightgreen)](#why-this-instead-of-a-dashboard-a-subscription-or-an-llm)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)

Peitho reads a multi-location retailer's own stock and sales and decides **what to move today, from where,
and why** — and what to reorder when no internal move can cover a shortage. It is a deterministic decision
engine: pure Python, no model, no cloud, and a reason attached to every line it emits.

It runs on the bundled synthetic data with no setup, so you can see the whole thing work before deciding
whether it fits your business:

```bash
# no install step — there are no dependencies to install
PYTHONPATH=src python3 -m peitho.route
```

```
Reorder horizon (target_cover_days) = 30  [the lead-time knob]
Transfer plan: 104 moves, 217 units, 6 store→store runs.
Supplier reorders: 0 cells, 0 units the network can't cover from spare.

Top 15 runs (cheapest first):
  WH→N1  15m   49 units /  19 variants
  N3→N2  15m   22 units /  11 variants
  WH→N3  40m   44 units /  20 variants
  WH→N2  40m   26 units /  14 variants
  WH→N4  70m   40 units /  20 variants
  WH→N5  70m   36 units /  20 variants
```

That is a complete transfer plan: consolidated source→destination runs, cheapest to move first, a source
only ever giving its spare. `python -m peitho.report` renders the same decision as an operator report,
where each move carries the read that produced it — `below target`, `low cover`, `selling fast` — in plain
language, so the person acting on it can check the machine against their own judgement.

## Why this instead of a dashboard, a subscription, or an LLM

- **It decides; it does not report.** A dashboard hands you a measurement of a state you already perceive.
  Peitho computes the move — ship this pair from that store — and the reorder when nothing internal can
  cover it.
- **It is deterministic and explainable by construction.** The reason on each line is not a model
  explaining itself after the fact; it *is* the computation. The same data produces the same decisions,
  every time, and every figure traces back to the source. No probability, no black box, nothing to
  hallucinate — by design, not by disclaimer.
- **It costs almost nothing to run.** Zero runtime dependencies — pure Python standard library, no ML
  framework, no GPU, no model weights, no network. The whole engine is ~6,600 lines and runs a full
  decision in a fraction of a second on one core; the algorithms are near-linear over sub-gigabyte data,
  so a real catalogue is seconds, not minutes. It is lighter than the browser tab you would open a hosted
  dashboard in, and your data never leaves the machine.
- **Its behaviour is pinned, not hoped.** Every pure decision is verified to a mutation-complete
  specification — the suite is proven to catch a corrupted version of each decision line, not merely to
  pass. See [Development](#development).

## Plug in your data

The core carries no company knowledge. Everything specific to a business — its store network, its category
vocabulary, and the adapter that reads its data — lives in a **cassette**, a directory the engine loads at
runtime. The bundled `cassettes/example` is a synthetic retailer; a real build is a copy of it with the
three files filled in.

```bash
export PEITHO_CASSETTE=/path/to/your/cassette   # your data, your machine — nothing leaves
PYTHONPATH=src python3 -m peitho.report
```

The onboarding procedure — the adapter contract, which methods are required, and the network/taxonomy
config — is in [`OPERATIONS.md`](OPERATIONS.md).

## How it works

The intelligence is a read-out of the structure of the data, not a model reasoning on top of it. Each item
is placed on four independent signed axes against norms mined from the data itself — days of cover, price
markdown, spatial surplus or deficit, and recent sales velocity — each axis reading `+1`, `-1`, or `0`
(this axis has no opinion here). A decision is what survives after those axes eliminate the verdicts they
rule out. So a line reads *below its cover norm, short of its own target, selling faster than its recent
tempo → move it*, and that signature is both the decision and its full justification, computed before any
higher-order reasoning runs.

The rationale for building it this way — and why a statistical stack is the wrong tool for a
seasonal, event-driven, single-catalogue business — is in [`DESIGN.md`](DESIGN.md). The module map and the
data-flow spine are in [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Development

```bash
uv sync --extra dev          # ruff · pylint · pytest for local checks
uv run pytest -q             # the pinned suite: mutation-complete synth suites + hand-authored intent tests
uvx ty check src/peitho      # type check
uv run ruff check . && uv run ruff format --check .
```

Every function is built to one loop: extract the pure decision, confirm with the language server that it is
wired, pin its behaviour with a mutation-complete test, type-check, commit. "Green" here means *behaviour is
pinned* — the suite would catch a corrupted version of each decision — not "nothing I wrote a test for
broke".
