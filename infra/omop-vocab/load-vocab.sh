#!/bin/bash
# Load OMOP vocabulary CSV files into PostgreSQL
# This script is run inside the Docker container during initialization

set -e

VOCAB_DIR="/vocab-data"
DB_NAME="omop_vocab"
DB_USER="postgres"

echo "Loading OMOP Vocabulary into database..."
echo "=========================================="

# Check if vocabulary files exist
if [ ! -f "$VOCAB_DIR/CONCEPT.csv" ]; then
    echo "ERROR: Vocabulary files not found in $VOCAB_DIR"
    echo "Please run the setup script first to download and extract vocabulary files."
    exit 1
fi

echo "Vocabulary directory: $VOCAB_DIR"
echo "Database: $DB_NAME"
echo ""

# Function to load a CSV file
load_table() {
    local table_name=$1
    local file_name=$2
    
    if [ ! -f "$VOCAB_DIR/$file_name" ]; then
        echo "Warning: $file_name not found, skipping..."
        return
    fi
    
    echo "Loading $table_name..."
    
    # Count rows (minus header)
    local row_count=$(tail -n +2 "$VOCAB_DIR/$file_name" | wc -l)
    echo "  Rows to load: $row_count"
    
    # Use COPY command for fast bulk loading
    # Skip header row, use tab delimiter (Athena default)
    psql -U "$DB_USER" -d "$DB_NAME" -c "
        COPY $table_name FROM '$VOCAB_DIR/$file_name' 
        WITH (FORMAT CSV, HEADER true, DELIMITER E'\t', QUOTE E'\b', ESCAPE '\\');
    " 2>&1 | grep -v "^$" || true
    
    # Verify load
    local loaded_count=$(psql -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM $table_name;" | tr -d ' ')
    echo "  ✓ Loaded: $loaded_count rows"
    echo ""
}

# Load vocabulary metadata tables first
echo "Loading metadata tables..."
load_table "vocabulary" "VOCABULARY.csv"
load_table "domain" "DOMAIN.csv"
load_table "concept_class" "CONCEPT_CLASS.csv"
load_table "relationship" "RELATIONSHIP.csv"

# Load main concept table (largest, ~6M rows, takes 2-3 min)
echo "Loading main concept table (this may take a few minutes)..."
load_table "concept" "CONCEPT.csv"

# Load concept relationships (~50M rows, takes 5-10 min)
echo "Loading concept relationships (this may take 5-10 minutes)..."
load_table "concept_relationship" "CONCEPT_RELATIONSHIP.csv"

# Load concept synonyms for search (~10M rows, takes 2-3 min)
echo "Loading concept synonyms..."
load_table "concept_synonym" "CONCEPT_SYNONYM.csv"

# Load optional tables
echo "Loading optional tables..."
load_table "drug_strength" "DRUG_STRENGTH.csv"
load_table "source_to_concept_map" "SOURCE_TO_CONCEPT_MAP.csv"

# Uncomment if you downloaded concept_ancestor (very large, 500M+ rows)
# echo "Loading concept ancestor (this may take 30-60 minutes)..."
# load_table "concept_ancestor" "CONCEPT_ANCESTOR.csv"

echo "=========================================="
echo "✓ Vocabulary loading complete!"
echo ""
echo "Database statistics:"
psql -U "$DB_USER" -d "$DB_NAME" <<EOF
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
    n_live_tup AS row_count
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
EOF

echo ""
echo "Sample concepts:"
psql -U "$DB_USER" -d "$DB_NAME" <<EOF
SELECT 
    concept_id,
    concept_name,
    domain_id,
    vocabulary_id,
    concept_code,
    standard_concept
FROM concept
WHERE vocabulary_id = 'SNOMED'
  AND standard_concept = 'S'
  AND domain_id = 'Condition'
LIMIT 5;
EOF

echo ""
echo "Next: Indexes will be created in the next initialization step."
