# Operations

How to run Peitho and how to onboard a company. The rationale for the design is in
[`DESIGN.md`](DESIGN.md); the module map is in [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Running it

The core has no third-party runtime dependencies, so the entry points run under a plain interpreter with
the source on the path:

```bash
PYTHONPATH=src python3 -m peitho.report      # the operator report (HTML) from the active cassette
PYTHONPATH=src python3 -m peitho.route        # the transfer plan, printed
```

With no environment set, the bundled `cassettes/example` (a synthetic retailer) is the active cassette, so
both commands produce output on a fresh checkout. Individual layers also run standalone for inspection —
`peitho.lenses.inventory` (the shortage watcher), `peitho.lenses.spatial` (the routing backbone),
`peitho.export` (the shadow-ledger JSON), and others — each printing a summary of its own stage.

Two environment variables control what runs and where it reads:

| Variable | Meaning | Default |
|---|---|---|
| `PEITHO_CASSETTE` | the company build to load (a cassette directory) | the bundled `cassettes/example` |
| `PEITHO_ROOT` | the data volume a file-backed adapter reads from (`$PEITHO_ROOT/data`) | auto-detected repo root |

```bash
export PEITHO_CASSETTE=/path/to/your/cassette
export PEITHO_ROOT=/path/to/your/data/volume     # only if your adapter reads from files
PYTHONPATH=src python3 -m peitho.report
```

## What a cassette is

A cassette is the only place company knowledge lives. It is a directory with four parts:

```
cassettes/<name>/
  manifest.toml     # identity: id, brand, currency, locale, report title, adapter module name
  network.toml      # the node graph: labels, zones, roles, edge-weight source
  taxonomy.toml     # the category vocabulary (optional)
  adapter/          # a Python package implementing SourceAdapter — reads your backend into canonical records
```

Swapping the cassette swaps the company; the core does not change. To build one, copy `cassettes/example`
and fill in the four parts.

## The adapter — the data-input contract

The adapter is a Python package (named by the manifest's `adapter` field, conventionally `adapter`) that
implements `peitho.source.SourceAdapter`: eighteen methods that turn your backend's raw data into the
core's canonical records. **All eighteen must be present** (the protocol is checked structurally), but
only one must return real data.

**Required — the substrate.** `load_grid(grid_dir=None, stores=None) -> Grid` returns the per-store ×
variant grid: for each `(article, color, size)`, a `{store: Cell}` map, where `Cell` carries stock, sale
quantity, recent sales, the sale-age spectrum, and the price fields. This is the only method that must
return real data; the grid is what every decision is read from.

**Optional — return empty and the corresponding feature simply stays quiet.** The remaining seventeen may
return `{}` / `[]` / `()`. A grid-only adapter with every other method empty — and no `taxonomy.toml` at
all — produces a valid report; fill each one in to light up its feature:

| Method | Returns | Lights up |
|---|---|---|
| `load_taxonomy` | `{article: {"section", "subsection"}}` | informative category labels (else everything is `unadjudicated`) |
| `load_article_ages` | `{article: age_days}` | shelf-age signals |
| `load_article_supplier` | `{article: supplier}` | the manufacturer edge + supplier reports |
| `load_supplier_purchases` | `{supplier: {sold, purchased, stock, profit}}` | supplier sell-through |
| `load_article_sections` | `{article: section}` | the merchandise-section axis |
| `load_article_attributes` | `{article: {"image", "style"}}` | per-article image + style attributes |
| `load_clearance_article_fields` | `(rsp_by_article, image_by_article)` | clearance report enrichment |
| `load_article_images` / `article_image_hashes` | `{article: filename}` / `{article: hash}` | image display + style dedupe |
| `fy_dirs` / `load_fy_articles` / `load_photo_hash` | per-financial-year article/photo sets | the base-vs-seasonal regime split |
| `load_bills_by_customer` / `load_clean_master` | customer bills / master records | the customer layer (PII) |
| `sample_sku_globs` | landed detail-dir globs | the SKU-code sample linkage |
| `daily_grid_dir` / `load_snapshot` | a dated snapshot dir / its `{(article,color,size,store): (stock,sale)}` | daily reconciliation |

The backend-specific parsing — which of your fields maps to which canonical value, where your files live,
how your codes are shaped — lives entirely inside this package. `peitho.source.parse_report_table` is a
company-agnostic helper for flattening a positional report table; you supply the column names.

## `manifest.toml`

Identity and wiring. Every field has an agnostic default, so a minimal manifest still loads.

```toml
id           = "acme"                      # short slug; also names the adapter's import
brand        = "Acme Retail"               # shown in the report header
currency     = "USD"
locale       = "en-US"
language      = "en"                       # report language register (English by default)
report_title = "Acme — Daily Inventory Report"
adapter      = "adapter"                   # the package inside the cassette implementing SourceAdapter
# data_root  = "data"                      # OPTIONAL: relative → resolved inside the cassette (the example
                                           # ships its own data); omit → $PEITHO_ROOT/data (a real build
                                           # reads the airgapped data in place)
```

## `network.toml`

The node graph. `nodes` is the roster; the live subset is induced per grid (a node absent from the data is
absent from the network). Roles are declared here where the sales geometry cannot see them; the coarse
warehouse-vs-selling split is otherwise induced from the data itself.

```toml
nodes = ["WH", "N1", "N2", "N3"]

[zones]                 # node -> geographic zone (drives the placeholder edge weights)
WH = "ZONE_A"
N1 = "ZONE_A"
N2 = "ZONE_B"
N3 = "ZONE_B"

[roles]                 # node -> role set. WAREHOUSE | SELL | TRIAGE | SOR | STORE. A node may hold several.
WH = ["WAREHOUSE"]
N1 = ["SELL", "TRIAGE"]
N2 = ["SELL"]
N3 = ["STORE"]

[weights]
source         = "placeholder"   # "osrm" to use a measured matrix, else the zone-distance placeholder
intra_zone_min = 15              # minutes within a zone
same_store_min = 0
# matrix       = "cost_matrix.json"   # OPTIONAL: a measured drive-time matrix, relative to data_root

[weights.zone_minutes]           # placeholder inter-zone minutes; keys are "ZONE_A|ZONE_B"
"ZONE_A|ZONE_B" = 40
```

## `taxonomy.toml`

The category vocabulary the deconvolution runs over. Entirely optional — omit the file and every article
resolves to `unadjudicated` (raw preserved, never guessed). The machinery is company-agnostic; only this
data differs.

```toml
clusters    = ["Footwear", "Apparel", "Accessories"]
placeholder = ["", "BLANK", "COLOR"]      # non-category filler labels

[relation]                                # raw token -> [cluster, sub_category]
"SHOES"   = ["Footwear", "Shoes"]
"SANDALS" = ["Footwear", "Sandals"]
"BAG"     = ["Accessories", "Bag"]

[gender]                                   # token -> gender code
"MENS"  = "M"
"WOMENS" = "F"

[age]                                      # substring token -> age label
"KIDS" = "kids"

[spelling_fixes]                           # curated typo fixes the fold can't reach
"SHOOS" = "SHOES"

[prefix_map]                               # article-code prefix -> forced category token (optional)
```

## Verifying your cassette

The permanent conformance guard (`tests/test_source_conformance.py`) checks that an adapter satisfies the
whole `SourceAdapter` protocol and that the full pipeline composes on it — run it against your cassette by
pointing `PEITHO_CASSETTE` at it. Then drive the real command:

```bash
PEITHO_CASSETTE=/path/to/your/cassette PYTHONPATH=src python3 -m peitho.report
```

A grid-only adapter is enough to get a first report; add the optional methods and `taxonomy.toml` as the
data behind them becomes available.
