# Design

Peitho is a control system for an operator-shaped retail operation: a data-geometry **state estimator**
feeding a classical-AI **controller** feeding a reporting **actuator**. This document is the rationale —
why the system is built as a data geometry rather than a statistical stack, what that geometry is, and why
the decisions in *this* project were made. It marks throughout what is implemented from what is specified
but not yet built. The as-built engineering map is in [`ARCHITECTURE.md`](ARCHITECTURE.md); the general
theory this instantiates is developed at length in the referenced portfolio papers, and is only
summarized here to the depth the design decisions require.

## 1. The problem the design answers

A conventional retail-analytics stack — forecasting, segmentation, churn models, KPI dashboards — carries
a prior about how a business *should* behave, learned from businesses in steady state. Applied to an
operation that is not in steady state, that prior is not slightly off but categorically wrong. The target
business here is the adversarial case on every axis such a stack assumes away: inventory turns over almost
entirely each season, so there is no stable catalog to fit a demand curve to; demand is event-driven,
not weekly-steady; a typical customer returns only rarely, so there is no repeat-purchase cadence to
model; and the operating logic is the operator's accumulated intuition, idiosyncratic and never written
down. A churn model
calibrated on repeat-purchase behavior reads this healthy business as a field of one-and-done, stale
customers — wrong because its priors do not fit, and confident because a statistical model launders that
mismatch into clean-looking numbers.

The design responds by carrying **no** prior about how the business should behave. It is reactive and
zero-state: it reads how the business *does* behave, from the structure of its own current data, and
routes accordingly. Change the season, the catalog, or the network and nothing is retrained — the norms
re-mine themselves and the decisions re-derive. That property is not a convenience; on a business this
idiosyncratic it is the only way to stay correct.

## 2. The thesis: the geometry is the semantics

The useful intelligence — *low on this item → move it from the nearest location with a surplus → and if
nothing internal can cover it, order it* — is a read-out of the **structure** of the data, not a reasoning
process running on top of it. Significance is not asserted onto the data from outside; it is the shape the
data already has, read by a projection.

Concretely, significance is a **signed deviation from a norm mined from this data** — never a benchmark
imported from elsewhere. Each measurable property of a stock position becomes a signed-ternary value
against that norm: `+1` above it, `−1` below, `0` when the property does not apply. Decisions are made by
**elimination** across independent measurements, not by scoring: each measurement rules candidate verdicts
out, and the answer is the one left standing.

The consequence that matters most for a commercial reader is that **the read-out is itself the
explanation.** A cell's signature — for example, *below its cover norm, short against its own target,
selling faster than its recent tempo* — is a complete, auditable justification for moving that unit,
produced by structure, before any higher-order reasoning runs. Explainability here is not a feature added
after a decision; it is what the geometry emits by construction. No model has to be asked why it decided
something, because no model decided it.

## 3. Why the built layer is the hard part

The layer that is built — the data geometry, the state estimator — is the unglamorous half, and it is the
half that historically sank classical AI. The concept-learning machinery of symbolic AI (version spaces,
near-miss learning, defeasible rules, the Society-of-Mind organization of specialist agents) was
essentially complete by 1990 and was never falsified. It was *starved*: it required a deterministic
substrate that could turn a messy, open domain into the typed structural descriptions its algorithms
consume, and for open real-world data no such substrate existed. The machinery had no fuel.

The built layer is exactly that substrate, for retail. It takes an un-authored, event-driven,
partially-missing data source and resolves it into a clean signed-ternary structure over which the
higher-order reasoning becomes tractable. That resolution — mining the norms, placing every entity, making
the field discriminate — is where the difficulty lives. The controller on top (production rules, min-cost
flow, regime-switched inventory control) is comparatively standard reasoning, and much of it is already
built in adjacent projects; it is standard *because* the substrate underneath has done the hard work of
making the domain legible.

## 4. The primitives

Each idea below is stated as what it is, then what it is not, because the failure mode of this design is a
plausible statistical substitute wearing the same vocabulary.

**The signed-ternary position.** A property maps to `{-1, 0, +1}` against its mined norm. Ternary is a
near-optimal, error-tolerant radix, and the `0` is load-bearing: it encodes *this axis has no opinion
here* — honest abstention — not a small or missing magnitude. It is **not** a `[0,1]` score, a probability,
or a learned weight; a continuous score would discard exactly the abstention the `0` carries.

**The mined zero.** A property's origin sits at a norm computed from this data — a per-store cover norm, a
per-store markdown norm — using a demand-weighted median so a non-seller cannot drag it. A position is a
signed deviation from that norm. It is **not** a fixed threshold; it re-mines itself when the data changes.

**The banks.** Several properties measure the same entity at once, each an independent competence placing
the entity off its *own* mined zero — a Society-of-Mind organization in which the intelligence is in the
arrangement, not in any one agent. The banks do **not** fuse or average; averaging them would ask whether
a surplus "agrees with" a markdown, which is incoherent because they answer different questions. Each
emits a coordinate; combination is a separate step.

**Interference and elimination.** The decision is made by ruling candidate verdicts out across the banks,
concentrating on the survivors — the same discipline as constraint propagation or a process of
elimination. It is **not** a weighted sum passed through a cutoff. A single confident exclusion removes
more of the answer space than a single confirmation adds.

**The discrimination guarantee.** If two operationally different situations share one signature, the
geometry has not resolved them, and the correct fix is a **new orthogonal dimension** — a bank off its own
mined zero — never a tuned threshold. Understanding a situation means driving the number of verdicts its
signature still admits to one; a collapsed signature is a missing dimension, not a mis-set cutoff. (Worked
in the build: a *below-cover, marked-down* signature collapsed a dying clearance line and a hot item
discounted into a stockout onto one verdict; the resolution was a fourth dimension — sales velocity — not
a moved floor.) This is the design's exact-identification discipline, and it is why a missed decision is
treated as a structural bug, never a weight to tune.

## 5. The conception: perception → cognition → action

Framed as control theory, the system is a state estimator feeding a control law feeding an actuator; framed
as AI, perception feeding cognition feeding action.

- **Perceive** — the data geometry estimates *where the business is* from partial, event-driven, un-authored
  data. This is the built layer.
- **Decide** — the controller determines *what to do*: the transfers, the reorders, the anticipatory
  pre-clearance, under the operator's policy and the physical constraints of the network.
- **Act** — the decision is emitted to whoever executes it. The report renderer is one such actuator; it is
  the system speaking, not the point of the system.

The purpose the whole design serves is to externalize an operator's accumulated operating intuition — the
compiled, sub-linguistic decision surface an experienced operator runs in their head — so the business can
run without living in one head. This is buildable, rather than merely admirable, because the classical
knowledge-acquisition bottleneck is absent: the reason expert systems mostly failed to capture expert rules
was that experts cannot introspect their own pattern-matching, but this operator's behavior is legible
enough that a clean rule base can be imputed from ordinary conversation and then cross-checked against the
data. The rules are the operator's; their formalization is the design's, and the two are kept distinct.

## 6. The shadow ledger and the multi-network substrate

The design is not one geometry but **several** — one per semantic domain: a location-and-stock network, an
item network, a finance network, a customer network, each encoding the *same underlying operational data* in
a *different geometric relationship*. This is the parable of the blind men and the elephant, with one
deliberate addition: the observers communicate. Each network is a legitimate partial, and because all of them
are built from a shared vocabulary of **atomic primitives** — an item identifier, a transaction, a count of
units, a sum of money — the same atom appears in every network that touches it, and combining the partial
reads resolves the whole that no single network sees. The atomics are the cross-network language; the
transaction, which touches an item, a location, a customer and a finance entry at once, is the seam along
which the networks are read together.

*(Built state: the location-and-stock geometry is built and is the one the system reasons over today; the
item, finance and customer networks are specified — see §9. The shadow-ledger organization below holds
regardless of how many networks are live.)*

Read directly, such a structure blinds rather than informs: a position across several overlapping geometries
is information in the strict sense but is *less* legible than the flat rows it was built from. Meaning emerges
only from a **resolved read** — a deterministic composition of the geometries that projects the
high-dimensional structure down to a single, parseable answer. The **shadow ledger** is that read,
crystallized, organized by semantic domain: one ledger per domain, holding everything worth knowing about
that domain, assembled from one or more network reads.

Two properties separate the shadow ledger from the flat input it superficially resembles. It is
**domain-consolidated, not report-fragmented**: there is one ledger per semantic domain — an operational
ledger (locations, stock, manufacturer roles and performance, travel cost), an item ledger (categorization,
sales context and dynamics) — and a new report or a new metric is *added as fields to the relevant ledger
and populated in a single run*, never a new encoding format. A per-report ledger would expand without bound;
a per-domain ledger grows by accretion. And it is **flat but intelligent**: where the input layer is flat
because it is *pre*-intelligence — raw counts, untouched — the shadow ledger's flat rows carry *reads of the
geometry itself*, the signed-ternary positions off mined norms, alongside the raw facts. The flat number is
the fact; the signed position is what the geometry knows about it; both sit in the same row.

This is why the conventional reports a business expects fall out of the substrate for free. A report is a
subset of one ledger, a join across two, or a metric computed from an equation whose inputs are atomics
pulled from several networks and fed as variables into one expression. The store-performance table, the
stock-movement summary, the vendor sell-through — each is a trivial projection of the operational and item
ledgers, produced by the same apparatus, in the same run, that produces the routing plan and the outlier
field. The substrate subsumes the conventional schema rather than sitting beside it: an operator keeps every
ordinary process and gets every ordinary report, and the intelligence is native to the identical structure,
not a bolt-on.

## 7. The lineage this instantiates

The approach is Good Old-Fashioned AI: intelligence as structured inference over explicit representations
rather than learned statistics. It instantiates a domain-invariant data-geometry architecture that has been
built and measured across unrelated domains — genomics, competitive game play, clinical triage, legal
retrieval, proteomics metadata — where only the instantiation changes and the structural core does not.
Within that frame it uses the classical canon directly: the transportation problem and min-cost flow for
routing; negative-weight shortest paths for signed traversal; constraint satisfaction and arc-consistency
for the elimination; frames and scripts for the taxonomy and the seasonal cohorts; the Society of Mind and
blackboard organization for the banks; defeasible logic with undercutting defeaters for the cases where a
surface signal is explained away by context; and case-based reasoning for the one predictive corner. These
are named here only to place the design; each is developed in the portfolio papers, not re-derived in this
repository.

## 8. The cardinal commitment

The rule is not *no algorithm decides anything* — deterministic classical reasoning is the decision path,
and it is welcome. The rule is that **no statistical or generative black box supplies meaning**:
significance and action are never delegated to an opaque, non-deterministic component that would substitute
a training prior for the structure of this business. Elimination over a graph and a signed deviation from a
mined norm *are* the decision path the commitment demands, not a workaround of it. The one genuinely
predictive question — taste, whether a *style* will sell, the shape of the next season — is narrative and
causal rather than statistical, and is routed to a deterministic, provenance-carrying story-understanding
engine that reads what a trajectory implies; even that layer is auditable and is not a learned model. A
related scope boundary follows the same logic: filling a stockout by shipping a *different* variant is
story-understanding judgment, not geometry, and is deliberately out of scope — routing is exact-variant
transfers plus true reorders, and a real stockout with no same-item spare is a supplier reorder, not a
substitution.

## 9. What is built, and what it is built toward

The boundary is part of the design, and it follows from a single principle: the controller trusts the
estimator, so a wrong estimate becomes a confidently-wrong plan, and the estimator is therefore built and
verified first.

**Implemented and behavior-pinned.** The signed-ternary decision core (the ternary algebra, the entity
position vector, the deviation banks, the interference noticer); the oriented consumers (restock, the
min-cost-flow router with its significance pass, the regime classifier, the supply sizer, the
pre-clearance scaffold, and the resolving layer); the flat estimator beneath them; the shadow-ledger
projection; the report renderer; and the cassette seam. Every pure decision in this layer is verified to a
mutation-complete specification and paired with a hand-authored intent test.

**Specified, not implemented.** Three larger structures are designed to depth but not built, and are
described here so the shape is clear rather than claimed as present:

- **The multi-network substrate.** The banks sharpen into several independent encoding *universes* —
  location/stock, item-semantic, finance, customer — each its own hierarchy and competence, coupled by the
  transaction that touches all of them at once (a sale is an item × a location × a customer × a finance
  entry). No universe is primary; the intelligence is in their coupling.
- **The cross-network resolution operator.** Where traversal within one network under-resolves a meaning,
  the residual is resolved by comparing the readings of independent, orthogonal network-traversals — the
  agreement or disagreement between two structurally-derived meanings is itself a signal, a dimension of
  the geometry beyond the literal encoding.
- **The predictive layer.** The pre-emptive analysis that volunteers significance nobody asked for, and the
  cross-year taste reasoning, both above the reactive core and both deferred until the snapshot history and
  the story-understanding engine are in place.

## 10. Verification as a design property

Because nothing in the decision path is stochastic, everything in it is pinnable, and the design commits to
it: isolate the pure decision, confirm with the language server that it is actually wired, pin its behavior
with a mutation-complete test, type-check, commit. Two emphases are specific to a control system. First,
**a missed decision is a structural bug, not a tuning problem** — retail is a finite answer space, so a
shortage with a surplus somewhere has a deterministic route, and a route the system fails to find is an
encoding, navigation, or emission gap to fix in the structure, never a weight to nudge. Second, **the
estimator is pinned harder than the controller**, because the controller trusts it and a wrong signal
propagates confidently to everything built above it.
