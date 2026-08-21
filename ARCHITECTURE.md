# Architecture

Peitho is a pure-Python decision engine over per-location inventory and sales data, plus a pluggable
per-company **cassette** that supplies all domain knowledge. This document maps the as-built system: the
data-flow spine, the modules and their key symbols, the seam a company plugs into, and what is implemented
versus specified. It is an engineering reference; the rationale for the design is in
[`DESIGN.md`](DESIGN.md), and running it and onboarding a company is in [`OPERATIONS.md`](OPERATIONS.md).

The map below is derived from the language server's view of the code — symbols, signatures, references —
so it names what exists rather than what the prose intends.

## Dependencies and footprint

The decision path has **zero third-party runtime dependencies** — pure Python standard library plus the
package's own code (~6,600 lines). No ML framework, no GPU, no numeric stack (`numpy`/`pandas`/`scipy`),
no network client. A full run — compute the routing decision and render the report — imports and executes
in a fraction of a second on one core over synthetic data. Development tooling (`ruff`, `pylint`,
`pytest`, Detective) is optional-only.

## 1. The spine

Data flows one direction. A company's backend becomes a `Grid`; each cell is placed on independent signed
axes (the **banks**); the per-cell signature is surfaced as an anomaly **field** (the noticer); **consumers**
orient that field into decisions (restock, routing, resolution); the result is projected into flat, per-domain
**shadow-ledger** JSON (`ledgers`), which the **report** renderer turns into an operator page.

```
  CASSETTE (per company)                 THE CORE (company-agnostic · pure Python)
  +--------------------+
  | data               |  SourceAdapter
  | adapter            | ------------->  Grid  -->  Banks  -->  signature  -->  Noticer
  | network.toml       |                 per-       four        per-cell        the anomaly field
  | taxonomy.toml      |                 store x    signed       ternary         (every off-norm cell)
  +--------------------+                 variant    dims off     coordinate             |
                                         cells      a mined                             |
                                                    zero                                v
                                                                          +-- Restock --+
                                                                          +-- Route   --+   orient the field
                                                                          +-- Resolve --+   into a decision
                                                                                 |
                                                                                 v
                                                                     Ledgers (domain shadow-ledger JSON)
                                                                                 |
                                                                                 v
                                                                     Report  (operator HTML)
```

Every stage is deterministic; no number in the path comes from a stochastic component. Each pure decision
function is verified to a mutation-complete specification (Detective) and paired with a hand-authored intent
test; the I/O shells are verified end-to-end through the real command.

## 2. Foundation primitives

The bottom layer — small, pure, no I/O.

| Module | Key symbols | Role |
|---|---|---|
| `otp.py` | `ternary`, `tally`, `interference`; `SUPPORT/OPPOSE/ORTHOGONAL`, `CONSTRUCTIVE/DESTRUCTIVE/AMBIGUOUS/SILENT` | The signed-ternary algebra. `ternary` maps a signed magnitude to `{-1,0,+1}`; `interference` is the elimination decision over a set of signs, returning a named verdict — not a weighted sum. |
| `geometry.py` | `deviation` | The fractional deviation `(value − zero)/zero` — the unit-free distance a bank measures off its mined zero. |
| `position.py` | `DimensionPosition`, `deviation_position`, `signature`, `hamming`, `discriminates` | An entity's placement: `deviation_position` → `DimensionPosition(dimension, sign, depth, zero, path)`. `signature` orders a position dict into the canonical bank-space tuple; `hamming`/`discriminates` compare signatures. |
| `grid.py` | `Cell`, `Grid`, `load_grid` | The canonical record. A `Cell` is one variant×store fact (stock, sales, the sale-age spectrum, price fields); a `Grid` maps `(article, color, size) → {store: Cell}`. `load_grid` delegates to the active cassette's adapter. |
| `stats.py` | `weighted_median`, `robust_price` | Robust summaries used when mining a zero (a demand-weighted median, so a non-seller cannot drag the norm). |
| `text.py` | `levenshtein`, `fuzzy_fold`, `canon_map` | The shared spelling-canonicalization fold, applied to raw idiom before taxonomy deconvolution. |

## 3. The cassette seam

The core reads landed data and domain config **only** through this seam; swapping the cassette swaps the
company with no core change. See [`OPERATIONS.md`](OPERATIONS.md) for the onboarding procedure.

| Module | Key symbols | Role |
|---|---|---|
| `config.py` | `ROOT`, `DATA`, `EXPORT`, `REPORTS`, `RECON`, `ASSETS` | Filesystem roots via `$PEITHO_ROOT` (env override, else auto-detected). Data-volume paths only. |
| `cassette.py` | `Cassette`, `active`, `load_cassette`, `resolve_cassette_dir`, `manifest_value`, `cassette_source`, `reset`, `register_cache_clearer` | The pluggable domain plug-in. `active()` is the process-shared cassette (`$PEITHO_CASSETTE`, else `cassettes/example`). Lazy accessors: `.network`, `.taxonomy`, `.adapter`, `.data_root`. `reset()` clears every cassette-derived cache together (dependency-inverted via `register_cache_clearer`, so the cassette never imports its consumers). |
| `source.py` | `SourceAdapter` (Protocol), `adapter`, `parse_report_table` | The data-input contract — 18 methods returning canonical records (grid, taxonomy, ages, supplier/customer/image/history readers). A cassette's adapter implements it; backend-specific parsing lives only in that adapter. `parse_report_table` is the company-agnostic report-table flattener (column names supplied by the adapter). |
| `network.py` | `NetworkState`, `active_network`, `network_from_cassette`, `sells_position`, `mine_sales_zero`, `coarse_role`, `induce_coarse_roles`; `ROLES` | The node graph as a data-induced, role-typed structure. A node's coarse role is read off the sales geometry (`sells_position` against a mined sales-zero): a node holding stock but selling ~nothing is a source, a selling node is a sink. Finer roles the geometry cannot see are declared by the cassette. |
| `product.py` | `Taxonomy`, `active_taxonomy`, `taxonomy_from_cassette`, `translate_taxonomy`, `translate_category`, `resolve_token`, `extract_gender_age` | The category axis: raw section/subsection + code-prefix deconvolved into an informative category. Machinery only — the vocabulary is cassette data (`taxonomy.toml`). Raw is preserved; an unknown token passes through flagged `unadjudicated`. |

## 4. The banks

`banks.py` places a `Cell` on four independent signed dimensions. Each reads a raw fact through a lens
primitive and returns a signed-ternary position off its own mined zero. Banks do not fuse or average.

| Bank | Function | Reads | `+1 / −1` |
|---|---|---|---|
| `INVENTORY` | `inventory_position` | days-of-cover vs the store×category mined cover baseline | surplus / deficit |
| `PRICE` | `price_position` | markdown depth vs the store's mined markdown baseline | marked-down / full-price |
| `SPATIAL` | `spatial_position` | unit surplus/deficit vs the node's own coverage target | spare / short |
| `VELOCITY` | `velocity_position` | recent sale-rate vs the store's mined tempo | accelerating / fading |

`SPATIAL` is unit-based (the surplus/deficit *is* the position the routing navigates); the other three are
fractional deviations off a mined zero with an informational-zero tolerance band (`noticer.DEFAULT_TOL`).

## 5. The noticer — the anomaly field

`noticer.py` builds every cell's signature and surfaces the field.

- `cell_positions(cell, …)` → the four `DimensionPosition`s for one cell.
- `signature(positions)` → the canonical bank-space tuple.
- `emission(sig)` → `FLAGGED` if any bank is non-zero, else `SILENT` (silence is the default; a cell with
  no opinion is dropped).
- `notice(grid)` → the list of `Anomaly` (variant, store, signature, mechanical label, full positions) for
  every flagged cell — the field consumers read.
- `describe(sig)` / `axis_word` / `VOCAB` → the mechanical `BANK:word` label (`INVENTORY:deficit …`).
- `class_distribution(anomalies)` → `(signature, label, count)`, each distinct signature its own class.

## 6. Consumers — orienting the field

A consumer takes the question-neutral field and orients it toward one decision.

### 6.1 Restock (`restock.py`)
`orient` turns each bank's sign toward the restock question (`RESTOCK_ORIENTATION`); `restock_votes` /
`restock_decision` run the oriented interference to a verdict in `{RESTOCK, HOLD, ESCALATE, IGNORE}`;
`restock_plan(field)` maps the field to `RestockItem`s.

### 6.2 Routing (`route.py` + `query/`)
Turn shortages into a concrete, batched, min-cost transfer plan.

| Module | Key symbols | Role |
|---|---|---|
| `route.py` | `plan_transfers`, `plan_transfers_global`, `batch_transfers`, `coverage_target`, `target_stock`, `spare_units`, `deficit_units`, `allocate`, `reorder_priority`, `manufacturer_significant`; `Transfer/Reorder/Batch` | Coverage math (the ≥1-unit floor) + the transfer plan; a source gives only its spare. |
| `query/edges.py` | `admissible`, `roles_of`, `edge_kind`; role + edge-kind constants | Which moves the controller permits, given node roles (WAREHOUSE/SELL/TRIAGE/SOR/STORE). |
| `query/flow.py` | `min_cost_flow` | The min-cost transportation solve over the admissible graph; verified optimal against brute force on seeded instances. |
| `query/significance.py` | `move_verdict`, `run_verdict`, `net_transfers`, `significant_moves` | Noise removal + cross-cycle netting → the sparse significant set (the daily handout). |
| `query/supply.py` | `base_stock_level`, `reorder_qty`, `critical_fractile`, `regime_order`, `supply_plan`; `SupplyOrder` | The reorder decision (regime-gated), for what the network can't cover from spare. |
| `query/regime.py` | `regime`, `article_fy_counts`, `classify`, `article_regimes`; `BASE/SEASONAL/UNKNOWN` | Per-article regime from cross-financial-year presence. |
| `query/rules.py` | `stagnant_action`, `dead_stock_actions`; `Action`; `TRIAGE_HUB`, `RETURN_WAREHOUSE` | Dead-stock rules; destinations sourced from the induced network. |
| `query/preclear.py` | `high_sale_propensity`, `should_preclear`, `preclear_actions` | The anticipatory pre-clear pass (scaffold; orchestrator dark until its inputs land — §8). |
| `query/plan.py` | `build_plan`; `Plan` | Assembles the full daily plan. |

### 6.3 Resolution (`resolve.py`)
`resolve_routing` + `gate` produce a per-signal verdict (`ResolvedSignal`; `ROUTE/ORDER/KEEP/DROP`) — the
layer that reconciles the routing and reorder reads.

## 7. Lenses — the raw-fact readers

`lenses/` turns raw `Cell` fields into primitives (a rate, a depth, a cover) and mines the per-store zeros
the banks measure against.

| Module | Key symbols | Role |
|---|---|---|
| `lenses/inventory.py` | `classify_cell`, `cover_days`, `recent_velocity`, `velocity`, `urgency_band`, `mine_store_baselines`, `mine_store_velocity_baselines`, `node_role`, `coarse_roles`, `find_graded_shortages`, `rank_surplus`; `Shortage/GradedShortage` | Cover, recency-weighted velocity, the mined cover/velocity zeros, shortage detection. |
| `lenses/price.py` | `discount_depth`, `margin_pct`, `clearance_band`, `mine_store_discount_baselines`, `store_clearance`, `load_article_ages`, `taste_verdicts`; `StoreClearance/ClearedItem/TasteVerdict` | Markdown depth, the mined markdown zero, clearance + the taste ledger. |
| `lenses/spatial.py` | `zone_of`, `edge_minutes`, `cost_matrix`, `all_pairs_min_cost`, `rank_sources`, `load_real_cost_matrix`; `NODES`, `STORE_ZONE` | The routing backbone: the node×node cost matrix (a measured drive-time matrix when the cassette declares one, else a transparent zone-distance placeholder) + all-pairs min-cost. `NODES`/`STORE_ZONE` are shims over `network.active_network()`. |
| `lenses/supplier.py` | `sell_through`, `supplier_band`, `mine_supplier_baseline`, `rank_suppliers`; `SupplierScore` | Per-supplier sell-through vs the mined supplier baseline. |
| `lenses/season.py` | `age_cohort`, `cohort_consistency`, `is_seasonal_cohort`, `deduce_seasonal_events`; `SeasonalEvent` | Seasonal-cohort deduction from the age spectrum. |

## 8. Projection — the domain shadow ledgers and the report

The substrate is projected into flat, parseable JSON **shadow ledgers, one per semantic domain** (see
[`DESIGN.md`](DESIGN.md) §6): each ledger holds everything worth knowing about its domain, assembled from one
or more substrate reads, its flat rows carrying both the raw facts and the signed-ternary geometry reads. A
report is a subset of one ledger, a join across two, or a metric over atomics from several — so adding one is
adding fields to a ledger and re-running, never a new file.

- `ledgers.py` — the domain-ledger assemblers. `build_operational`/`export_operational` → `operational.json`
  (locations, store performance, routing, manufacturer orders, supplier sell-through, store-grain clearance,
  the node network); `build_item`/`export_item` → `item.json` (per-SKU and item inventory, the wide
  crystallized projection with sell-dynamics, item-grain clearance, seasonal, sale digest, outliers, the
  signed-ternary restock field); `build_customer`/`export_customer` → `customer.json` (the pseudonymous
  structural customer node-network, separable-PII). `report()` (`python -m peitho.ledgers`) builds all three.
  Each `build_<domain>` composes pure section-builders over shared grid loads; the I/O is only the final write.
- `export.py` — the shared substrate the ledgers compose from: the portable record builders (`build_sku_record`,
  `build_item_record`, `build_wide_item_record`, `build_movement`), the adapter-backed loaders
  (`load_taxonomy`, `load_article_attributes`, `load_clearance_article_fields`), `article_image_map`; plus the two
  projections not domain-consolidated — `export_taste_ledger` (an append-only dated *stream*, not a snapshot
  section) and `export_morning` (the digest-of-digests that reads the domain ledgers). Every value referenced
  comes from the source pull, not the local encoding.
- `report/` — the public operator report renderer (`python -m peitho.report`):
  - `render.py` — pure render decisions (`parse_reason`, `humanize_reason`, `group_runs`) + `render_report`
    (the operational ledger's routing section → operator HTML: transfers grouped into runs, each move with its
    humanized signed-ternary reason; the raw `BANK:word` tokens never reach the operator).
  - `style.py` — the presentation chassis: a white-ground stylesheet, `prettify_category`, the operator
    lexicon over `noticer.VOCAB`.
  - `__init__.py` / `__main__.py` — the I/O shell: refresh the operational ledger, render its routing section,
    write. Brand and title come from the cassette manifest.
- `digest.py`, `morning.py` — the surprise/outlier and morning-router pure layers the item ledger and the
  morning export consume.
- `customer.py` — customer-master handling: separable-PII resolution, nodes keyed by a stable customer identifier.
- `reconcile.py` — daily-snapshot reconciliation (the back-run over dated snapshots).
- `sku.py` — SKU parsing, image-hash clustering, cross-year dedupe, the product-code sample linkage.

## 9. Build status

Marked per component, because the design is specified past the current implementation.

**Implemented** — code exists, compiles, and every pure decision function is mutation-complete with an
intent test: the signed-ternary core (`otp`, `position`, `banks`, `noticer`), the consumers (`restock`,
`route` + `query/flow`/`significance`/`supply`/`regime`/`rules`/`preclear`/`plan`, `resolve`), the flat
estimator (`grid`, `lenses/*`), the domain shadow ledgers (`ledgers`, over the shared `export` record builders
and loaders), the `report` renderer, and the `cassette`/`source`/`network`/`product` seam.

**Specified, not implemented** — four package-only stubs, each with a docstring pointing at its design
section:

| Package | Will hold |
|---|---|
| `store/` | immutable landing zone + provenance ledger |
| `ingest/` | the read-only backend pull |
| `inbound/` | a natural-language request surface (sender allowlist; message-as-data) |
| `preempt/` | the pre-emptive push layer |

The larger designed-but-unbuilt surface — the multi-network substrate, the cross-network resolution
operator, the predictive layer — is described in [`DESIGN.md`](DESIGN.md) §8.

## 10. Invariants

The rules a change must not break (the *why* is in [`DESIGN.md`](DESIGN.md)).

1. **Signed-ternary only in the decision path.** Positions are `{-1, 0, +1}` off a mined zero; the decision
   is interference/elimination (`otp.interference`). Never a weighted mean, a `[0,1]` score, or a learned model.
2. **Raw is sacred.** Untouched backend fields are always carried through; derived values are added
   non-destructively.
3. **Asymmetric emission.** Silence is the default — a cell with no bank opinion is dropped.
4. **Abstain, don't fabricate.** An unresolved token/position passes through flagged, never guessed.
5. **The core is company-agnostic.** Every domain fact lives in the active cassette; no backend name,
   schema, or path appears in the core.
6. **Pure decisions are pinned.** Each is Detective mutation-complete with a hand-authored intent test; the
   I/O shells are verified end-to-end through the real command.
