#!/bin/bash
# Setup script for OMOP Vocabulary Server
# Downloads Athena vocabularies and loads them into PostgreSQL

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}OMOP Vocabulary Setup Script${NC}"
echo "====================================="
echo ""

# Check prerequisites
echo "Checking prerequisites..."
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed${NC}"
    exit 1
fi

if ! command -v unzip &> /dev/null; then
    echo -e "${RED}Error: unzip is not installed${NC}"
    exit 1
fi

if ! command -v curl &> /dev/null; then
    echo -e "${RED}Error: curl is not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ All prerequisites met${NC}"
echo ""

# Create directories
VOCAB_DIR="./data/omop-vocab"
SCRIPTS_DIR="./scripts/omop"

mkdir -p "$VOCAB_DIR"
mkdir -p "$SCRIPTS_DIR"

echo -e "${GREEN}Created directories:${NC}"
echo "  - $VOCAB_DIR (for vocabulary CSV files)"
echo "  - $SCRIPTS_DIR (for SQL scripts)"
echo ""

# Check if vocabulary files exist
if [ -f "$VOCAB_DIR/CONCEPT.csv" ]; then
    echo -e "${YELLOW}Vocabulary files already exist in $VOCAB_DIR${NC}"
    read -p "Do you want to re-download? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Using existing vocabulary files."
        SKIP_DOWNLOAD=true
    fi
fi

if [ "$SKIP_DOWNLOAD" != "true" ]; then
    echo -e "${YELLOW}Manual Step Required: Download Athena Vocabularies${NC}"
    echo "====================================================="
    echo ""
    echo "1. Go to: https://athena.ohdsi.org"
    echo "2. Create an account (if you don't have one)"
    echo "3. Select vocabularies (recommended minimum):"  
    echo "   - SNOMED CT (Clinical findings, procedures)"
    echo "   - RxNorm (Drugs)"
    echo "   - LOINC (Lab tests, measurements)"
    echo "   - ICD10CM (Diagnoses)"
    echo "   - UCUM (Units of measure)"
    echo "4. Download the bundle (will be a .zip file, ~5-7GB)"
    echo "5. Save the ZIP file to: $VOCAB_DIR/athena-download.zip"
    echo ""
    read -p "Press Enter when you've downloaded the file to $VOCAB_DIR/athena-download.zip..."
    
    # Extract vocabulary files
    if [ ! -f "$VOCAB_DIR/athena-download.zip" ]; then
        echo -e "${RED}Error: $VOCAB_DIR/athena-download.zip not found${NC}"
        echo "Please download the vocabulary bundle from Athena."
        exit 1
    fi
    
    echo -e "${GREEN}Extracting vocabulary files...${NC}"
    unzip -o "$VOCAB_DIR/athena-download.zip" -d "$VOCAB_DIR"
    
    # Check for required files
    REQUIRED_FILES=("CONCEPT.csv" "CONCEPT_RELATIONSHIP.csv" "CONCEPT_SYNONYM.csv" "VOCABULARY.csv" "DOMAIN.csv" "CONCEPT_CLASS.csv")
    for file in "${REQUIRED_FILES[@]}"; do
        if [ ! -f "$VOCAB_DIR/$file" ]; then
            echo -e "${RED}Error: Required file $file not found in extracted archive${NC}"
            exit 1
        fi
    done
    
    echo -e "${GREEN}✓ Vocabulary files extracted successfully${NC}"
    echo ""
fi

# Start OMOP vocab database
echo -e "${GREEN}Starting OMOP vocabulary database...${NC}"
docker compose -f infra/docker-compose.yml up -d omop-vocab

# Wait for database to be ready
echo "Waiting for database to be ready..."
for i in {1..30}; do
    if docker compose -f infra/docker-compose.yml exec -T omop-vocab pg_isready -U postgres &>/dev/null; then
        echo -e "${GREEN}✓ Database is ready${NC}"
        break
    fi
    echo -n "."
    sleep 1
done
echo ""

# Load vocabulary
echo -e "${GREEN}Loading OMOP vocabulary into database...${NC}"
echo "This may take 10-20 minutes depending on the vocabulary size."
echo ""

# Run the loader script inside the container
docker compose -f infra/docker-compose.yml exec -T omop-vocab bash /docker-entrypoint-initdb.d/load-vocab.sh

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ OMOP vocabulary loaded successfully!${NC}"
    echo ""
    echo "Database connection details:"
    echo "  Host: localhost"
    echo "  Port: 5433"
    echo "  Database: omop_vocab"
    echo "  User: postgres"
    echo "  Password: postgres"
    echo ""
    echo "Test the connection:"
    echo "  psql -h localhost -p 5433 -U postgres -d omop_vocab -c 'SELECT COUNT(*) FROM concept;'"
    echo ""
    echo "Next steps:"
    echo "  1. Update your .env file with:"
    echo "     OMOP_VOCAB_URL=postgresql://postgres:postgres@localhost:5433/omop_vocab"
    echo "  2. Run: make run-dev"
else
    echo -e "${RED}Error loading vocabulary${NC}"
    exit 1
fi
