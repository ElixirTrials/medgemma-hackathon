-- Create indexes for OMOP Vocabulary tables
-- These indexes are critical for fast concept lookups and searches
-- Run AFTER data loading (indexes slow down COPY)

\echo 'Creating indexes for OMOP Vocabulary tables...'
\echo 'This may take 10-20 minutes depending on vocabulary size.'
\echo ''

-- CONCEPT table indexes
\echo 'Creating concept indexes...'
CREATE INDEX idx_concept_concept_id ON concept (concept_id);
CREATE INDEX idx_concept_code ON concept (concept_code);
CREATE INDEX idx_concept_vocabulary_id ON concept (vocabulary_id);
CREATE INDEX idx_concept_domain_id ON concept (domain_id);
CREATE INDEX idx_concept_class_id ON concept (concept_class_id);
CREATE INDEX idx_concept_standard_concept ON concept (standard_concept);
-- Most common query pattern: find standard concepts by domain and vocabulary
CREATE INDEX idx_concept_domain_vocab_standard ON concept (domain_id, vocabulary_id, standard_concept);
-- For text search on concept names
CREATE INDEX idx_concept_name_trgm ON concept USING gin (concept_name gin_trgm_ops);

-- CONCEPT_SYNONYM indexes for fast text search
\echo 'Creating concept_synonym indexes...'
CREATE INDEX idx_concept_synonym_concept_id ON concept_synonym (concept_id);
CREATE INDEX idx_concept_synonym_name_trgm ON concept_synonym USING gin (concept_synonym_name gin_trgm_ops);
-- For exact matches (faster than trigram)
CREATE INDEX idx_concept_synonym_name_lower ON concept_synonym (LOWER(concept_synonym_name));

-- CONCEPT_RELATIONSHIP indexes
\echo 'Creating concept_relationship indexes...'
CREATE INDEX idx_concept_relationship_id_1 ON concept_relationship (concept_id_1);
CREATE INDEX idx_concept_relationship_id_2 ON concept_relationship (concept_id_2);
CREATE INDEX idx_concept_relationship_id_1_2 ON concept_relationship (concept_id_1, concept_id_2);
CREATE INDEX idx_concept_relationship_relationship_id ON concept_relationship (relationship_id);

-- CONCEPT_ANCESTOR indexes (if table exists)
-- Uncomment if you loaded concept_ancestor
-- \echo 'Creating concept_ancestor indexes...'
-- CREATE INDEX idx_concept_ancestor_ancestor_id ON concept_ancestor (ancestor_concept_id);
-- CREATE INDEX idx_concept_ancestor_descendant_id ON concept_ancestor (descendant_concept_id);

-- SOURCE_TO_CONCEPT_MAP indexes
\echo 'Creating source_to_concept_map indexes...'
CREATE INDEX idx_source_to_concept_source_code ON source_to_concept_map (source_code);
CREATE INDEX idx_source_to_concept_source_vocab ON source_to_concept_map (source_vocabulary_id);
CREATE INDEX idx_source_to_concept_target_id ON source_to_concept_map (target_concept_id);

-- DRUG_STRENGTH indexes
\echo 'Creating drug_strength indexes...'
CREATE INDEX idx_drug_strength_drug_concept_id ON drug_strength (drug_concept_id);
CREATE INDEX idx_drug_strength_ingredient_concept_id ON drug_strength (ingredient_concept_id);

-- Foreign key constraints (for data integrity)
\echo 'Creating foreign key constraints...'
ALTER TABLE concept ADD CONSTRAINT fk_concept_domain FOREIGN KEY (domain_id) REFERENCES domain (domain_id);
ALTER TABLE concept ADD CONSTRAINT fk_concept_vocabulary FOREIGN KEY (vocabulary_id) REFERENCES vocabulary (vocabulary_id);
ALTER TABLE concept ADD CONSTRAINT fk_concept_class FOREIGN KEY (concept_class_id) REFERENCES concept_class (concept_class_id);

ALTER TABLE concept_relationship ADD CONSTRAINT fk_concept_relationship_concept_1 FOREIGN KEY (concept_id_1) REFERENCES concept (concept_id);
ALTER TABLE concept_relationship ADD CONSTRAINT fk_concept_relationship_concept_2 FOREIGN KEY (concept_id_2) REFERENCES concept (concept_id);
ALTER TABLE concept_relationship ADD CONSTRAINT fk_concept_relationship_relationship FOREIGN KEY (relationship_id) REFERENCES relationship (relationship_id);

ALTER TABLE concept_synonym ADD CONSTRAINT fk_concept_synonym_concept FOREIGN KEY (concept_id) REFERENCES concept (concept_id);

-- Enable pg_trgm extension for fuzzy text search (if not already enabled)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Analyze tables for query planner statistics
\echo 'Analyzing tables...'
ANALYZE concept;
ANALYZE concept_synonym;
ANALYZE concept_relationship;
ANALYZE vocabulary;
ANALYZE domain;
ANALYZE concept_class;
ANALYZE relationship;
ANALYZE drug_strength;
ANALYZE source_to_concept_map;

\echo ''
\echo '✓ All indexes created successfully!'
\echo ''
\echo 'Vocabulary database is ready for queries.'
\echo ''
\echo 'Example queries:'
\echo ''
\echo '-- Find standard SNOMED concepts for "diabetes"'
\echo 'SELECT concept_id, concept_name, concept_code'
\echo 'FROM concept'
\echo 'WHERE vocabulary_id = ''SNOMED'''
\echo '  AND standard_concept = ''S'''
\echo '  AND LOWER(concept_name) LIKE ''%diabetes%'''
\echo 'LIMIT 10;'
\echo ''
\echo '-- Find all synonyms for a concept'
\echo 'SELECT cs.concept_synonym_name'
\echo 'FROM concept c'
\echo 'JOIN concept_synonym cs ON c.concept_id = cs.concept_id'
\echo 'WHERE c.concept_id = 201826;  -- Type 2 Diabetes Mellitus'
\echo ''
