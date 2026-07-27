# CLI

The `osclient` package offers a CLI entry point, `osclient`, with subcommands.

## Usage

Every invocation has the form:

```
osclient <subcommand> [options]
```

The subcommands are:

- `query`: run a SQL, PPL, or raw-DSL query
- `search`: a term-lookup convenience
- `index`: index-level operations
- `cluster`: cluster-level inspection
- `triage`: the guided threat-hunt workflow

By default, results are printed as YAML on stdout; failures are reported on
stderr with a non-zero exit status.

The connection is resolved from the `OPENSEARCH_*` environment variables (see
[Library](library.md)), so no credentials ever appear on the command line.

## Output format

Every command that prints data takes `--format`, one of `yaml` (the default),
`json`, `csv`, or `tsv`:

```
osclient query sql "SELECT client_ip FROM logs-*" --format json | jq '.[].client_ip'
osclient query sql "SELECT client_ip FROM logs-*" --format csv > stack.csv
osclient query sql "SELECT client_ip FROM logs-*" --format tsv | column -t
```

The tabular formats (`csv`, `tsv`) render one record per row. Nested objects
become dotted column names (`source.ip`), and the header is the union of every
record's keys, with a blank cell where a record lacks one. A list value is
written into its cell as JSON. A result that is a single object (such as
`cluster versions` or a triage summary) is rendered as a one-row table.

## `osclient query`

`query` runs a query in a chosen language and prints the result as YAML. Each
`<query>` may be given literally, as `-` to read it from stdin, or as `@PATH` to
read it from a file.

Run a SQL query. `--explain` prints its execution plan (the pushed-down DSL)
instead of running it:

```
osclient query sql "SELECT rule.level FROM logs-* LIMIT 5"
osclient query sql --explain "SELECT * FROM logs-* WHERE rule.level < 3"
osclient query sql @failed-logins.sql
osclient query sql - <<'EOF'
SELECT client_ip, COUNT(*) FROM logs-*
WHERE `event.outcome` = 'failure'
GROUP BY client_ip
EOF
```

Run a PPL query; `--explain` works here too:

```
osclient query ppl "source=logs-* | head 5"
osclient query ppl --explain "source=logs-* | where rule.level > 10"
```

Run a raw query DSL: a bare query object, or a full `_search` body (detected by
a top-level `query` key). Add `--count-only` to return just the number of
matching documents, routed to `_count` (so `size`, `sort`, and any aggregations
in the body are ignored):

```
osclient query dsl '{"query": {"bool": {"must": [{"term": {"event.action": "logon"}}]}}}'
osclient query dsl @rules/compiled/lateral-movement.json
osclient query dsl @rule.json --count-only
```

## `osclient search`

`search` finds the newest documents matching a set of exact `field=value` terms,
ANDed together, most recent first. `--count` controls how many are returned;
`--count-only` prints just the number of matches (via `_count`):

```
osclient search rule.id=5710 agent.name=web01 --count 3
osclient search source.ip=10.0.0.5 --count-only
```

## `osclient index`

`index` groups index-level operations. `mapping` shows the mapping for one or
more fields (comma-separated, wildcards allowed). An empty result means the
field is unmapped, and therefore cannot be queried by SQL or a term filter even
when it appears in a document's `_source`. `--index` overrides the configured
`OPENSEARCH_INDEX`:

```
osclient index mapping "data.event.*"
osclient index mapping source.ip --index logs-2026.07.14
```

## `osclient cluster`

`cluster` groups cluster-level inspection. `versions` reports the OpenSearch and
installed-plugin versions:

```
osclient cluster versions
```

## `osclient triage`

### What triage does

`triage` supports a layered-elimination threat hunt: instead of searching for a
needle in a haystack, eliminate the haystack.

The process:

- identify a set of documents you can explain (routine noise, known-good
  activity, an expected job, etc.)
- set them aside
- repeat until the remaining dataset can be reviewed manually

Each dataset you remove is labeled with a 'layer' number. Every document records
the layer that removed it, the query that selected it, and a short rationale.
That makes the hunt auditable: afterwards anyone can see exactly which logs were
eliminated, by what reasoning, and in what order.

### How it maps to OpenSearch

Each step runs through the client as an OpenSearch operation, all on a scratch
copy so the source data is never touched: the logs of interest are first copied
into a fresh, writable index with a server-side `_reindex`, and every copied
document is tagged `triage.layer: -1` (a sentinel meaning "untriaged").

The operations, mirroring the process above:

- identify a set by writing a SQL `WHERE` predicate, which the SQL engine's
  `_explain` turns into the query DSL the tool actually runs (see
  [SQL `_explain`](sql-explain.md))
- set it aside with a single `_update_by_query` that stamps the layer number,
  the predicate, and the rationale onto the matches, touching only documents
  still tagged `-1`
- repeat, reading back each pass's progress with a `size: 0` aggregation over
  `triage.layer`: how many documents are still `-1` versus how many sit in each
  eliminated layer

Because the layer, predicate, and rationale are written onto every eliminated
document, the audit trail the process promises lives in the data itself.

### How the tool performs those actions

You never issue those OpenSearch calls yourself; three subcommands drive them,
with guardrails:

- `init` creates the scratch index (with an explicit triage-field mapping) and
  runs the reindex, polling the async task to completion so a large copy does
  not hit a request timeout.
- `eliminate` translates your predicate, cross-checks the translation (see
  below), and, on `--apply`, runs the tagging `_update_by_query`, again polling
  to completion.
- `status` runs the aggregation and prints the per-layer breakdown.

Before tagging anything, `eliminate` cross-checks its work: it confirms the
translated DSL matches exactly as many documents as `SELECT COUNT(*)` for the
same predicate, and refuses if the two disagree, rather than risk tagging a set
the predicate did not mean. Without `--apply` it is a dry run that only reports
counts, the translated DSL, and a sample.

The triage index is always named explicitly with `--index` / `--dest`; it is
never taken from `OPENSEARCH_INDEX`, so a wildcard or the wrong index can never
be tagged by accident.

### The workflow

Copy the logs of interest into a fresh index, tagging every document untriaged.
The source index is only read, never modified:

```
osclient triage init --source logs-2026.07.14 --dest triage-hunt-001
```

Review the copied index (for example in a dashboard), pick a set you can
explain, and dry-run its elimination. `--where` takes a SQL `WHERE` predicate;
nothing is written without `--apply`. The dry run reports how many documents
match, how many are still untriaged (and so would be tagged), the translated
DSL, and a sample:

```
osclient triage eliminate --index triage-hunt-001 --layer 1 --where "rule.level < 3" --explanation "informational, below alert threshold"
```

When the counts look right, re-run the same command with `--apply` to write the
tags:

```
osclient triage eliminate --index triage-hunt-001 --layer 1 --where "rule.level < 3" --explanation "informational, below alert threshold" --apply
```

Check what remains, then repeat the review-and-eliminate step until the
untriaged count reaches zero. Omit `--layer` and each elimination
auto-increments to the next layer (2, 3, ...):

```
osclient triage status --index triage-hunt-001
```

### Predicate quoting

String literals in a predicate use single quotes and field names use backticks,
for example `` `event.action` = 'delivery' ``. Because backticks trigger command
substitution inside a double-quoted shell argument, either wrap the whole
predicate in single quotes, or pass `--where -` to read the predicate from
`stdin`, or `--where @PATH` to read it from a file:

```
osclient triage eliminate --index triage-hunt-001 --layer 1 --explanation "received emails" --where - <<'EOF'
`event.action` = 'delivery' AND `message` = 'Message received'
EOF
```
