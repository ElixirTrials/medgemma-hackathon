#!/usr/bin/env bash
# Load OMOP vocabulary into Cloud SQL (or any remote Postgres) using client-side \copy.
# Run from repo root with Cloud SQL Proxy listening (e.g. localhost:5432).
# Requires: vocabulary CSVs in VOCAB_DIR (e.g. from Athena OHDSI).
#
# Data and format match the docker-compose omop-vocab service: same tables, same order,
# same COPY options (FORMAT CSV, HEADER true, DELIMITER tab, QUOTE \b, ESCAPE \) as load-vocab.sh.
#
# Usage:
#   export OMOP_VOCAB_URL="postgresql://USER:PASSWORD@localhost:5432/omop_vocab"
#   ./infra/omop-vocab/load-vocab-cloudsql.sh
# Or:
#   ./infra/omop-vocab/load-vocab-cloudsql.sh /path/to/data/omop_vocab

set -e

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VOCAB_DIR="${1:-$REPO_ROOT/data/omop_vocab}"
OMOP_VOCAB_URL="${OMOP_VOCAB_URL:-}"

if [ -z "$OMOP_VOCAB_URL" ]; then
  echo "ERROR: Set OMOP_VOCAB_URL (e.g. postgresql://USER:PASSWORD@localhost:5432/omop_vocab)" >&2
  echo "       Use Cloud SQL Proxy so the host is localhost and port is the proxy port." >&2
  exit 1
fi

if [ ! -f "$VOCAB_DIR/CONCEPT.csv" ]; then
  echo "ERROR: Vocabulary files not found in $VOCAB_DIR" >&2
  echo "       Download from https://athena.ohdsi.org and extract CONCEPT.csv, etc." >&2
  exit 1
fi

echo "Loading OMOP vocabulary into Cloud SQL..."
echo "  VOCAB_DIR=$VOCAB_DIR"
echo "  DB=omop_vocab (from OMOP_VOCAB_URL)"
if command -v pv &>/dev/null; then
  echo "  Progress: pv enabled"
else
  echo "  Progress: none (install 'pv' for a progress bar: brew install pv)"
fi
echo ""

# Session settings to speed up COPY (fewer syncs, more memory for sorts)
PSQL_COPY_OPTS="SET synchronous_commit = off; SET work_mem = '256MB';"
COPY_WITH="WITH (FORMAT CSV, HEADER true, DELIMITER E'\\t', QUOTE E'\\b', ESCAPE E'\\\\')"

load_table() {
  local table_name="$1"
  local file_name="$2"
  local path="$VOCAB_DIR/$file_name"
  if [ ! -f "$path" ]; then
    echo "  Skip $table_name ($file_name not found)"
    return 0
  fi
  local rows
  rows=$(tail -n +2 "$path" | wc -l | tr -d ' ')
  echo "  Loading $table_name ($rows rows)..."
  if command -v pv &>/dev/null; then
    # Progress bar: pipe file through pv into COPY FROM STDIN
    pv -pterb -N "$table_name" "$path" | psql "$OMOP_VOCAB_URL" -v ON_ERROR_STOP=1 -c "${PSQL_COPY_OPTS} COPY $table_name FROM STDIN $COPY_WITH;"
  else
    local path_sql="${path//\'/\'\'}"
    psql "$OMOP_VOCAB_URL" -v ON_ERROR_STOP=1 -c "${PSQL_COPY_OPTS} \\copy $table_name FROM '$path_sql' $COPY_WITH;"
  fi
  echo "  ✓ $table_name"
}

# Metadata tables first (small, sequential)
load_table "vocabulary" "VOCABULARY.csv"
load_table "domain" "DOMAIN.csv"
load_table "concept_class" "CONCEPT_CLASS.csv"
load_table "relationship" "RELATIONSHIP.csv"

# concept: single large table (~7M rows)
echo "  Loading concept (may take a few minutes)..."
load_table "concept" "CONCEPT.csv"

# Big tables: load in parallel to cut total time (only the slowest determines wait)
echo "  Loading concept_relationship + concept_synonym in parallel..."
load_table "concept_relationship" "CONCEPT_RELATIONSHIP.csv" &
PID1=$!
load_table "concept_synonym" "CONCEPT_SYNONYM.csv" &
PID2=$!
wait $PID1 $PID2

# Optional tables (smaller, can also run in parallel)
load_table "drug_strength" "DRUG_STRENGTH.csv" &
load_table "source_to_concept_map" "SOURCE_TO_CONCEPT_MAP.csv" &
wait

echo ""
echo "✓ Vocabulary load complete. Run create-indexes.sql next:"
echo "  psql \"\$OMOP_VOCAB_URL\" -f infra/omop-vocab/create-indexes.sql"
echo ""
