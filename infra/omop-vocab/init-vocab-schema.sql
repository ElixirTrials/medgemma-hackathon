-- OMOP CDM Vocabulary Tables (v5.4)
-- Only vocabulary tables needed for concept mapping
-- Full CDM clinical tables (PERSON, OBSERVATION, etc.) are NOT included

-- Vocabulary metadata
CREATE TABLE vocabulary (
  vocabulary_id VARCHAR(20) NOT NULL,
  vocabulary_name VARCHAR(255) NOT NULL,
  vocabulary_reference VARCHAR(255),
  vocabulary_version VARCHAR(255),
  vocabulary_concept_id INTEGER NOT NULL,
  PRIMARY KEY (vocabulary_id)
);

-- Domain classification
CREATE TABLE domain (
  domain_id VARCHAR(20) NOT NULL,
  domain_name VARCHAR(255) NOT NULL,
  domain_concept_id INTEGER NOT NULL,
  PRIMARY KEY (domain_id)
);

-- Concept class
CREATE TABLE concept_class (
  concept_class_id VARCHAR(20) NOT NULL,
  concept_class_name VARCHAR(255) NOT NULL,
  concept_class_concept_id INTEGER NOT NULL,
  PRIMARY KEY (concept_class_id)
);

-- Main concept table (~6M rows)
CREATE TABLE concept (
  concept_id INTEGER NOT NULL,
  concept_name VARCHAR(255) NOT NULL,
  domain_id VARCHAR(20) NOT NULL,
  vocabulary_id VARCHAR(20) NOT NULL,
  concept_class_id VARCHAR(20) NOT NULL,
  standard_concept VARCHAR(1),  -- 'S' = standard, 'C' = classification, NULL = non-standard
  concept_code VARCHAR(50) NOT NULL,
  valid_start_date DATE NOT NULL,
  valid_end_date DATE NOT NULL,
  invalid_reason VARCHAR(1),  -- 'D' = deleted, 'U' = updated, NULL = valid
  PRIMARY KEY (concept_id)
);

-- Concept relationships (~50M rows)
CREATE TABLE concept_relationship (
  concept_id_1 INTEGER NOT NULL,
  concept_id_2 INTEGER NOT NULL,
  relationship_id VARCHAR(20) NOT NULL,
  valid_start_date DATE NOT NULL,
  valid_end_date DATE NOT NULL,
  invalid_reason VARCHAR(1),
  PRIMARY KEY (concept_id_1, concept_id_2, relationship_id)
);

-- Relationship metadata
CREATE TABLE relationship (
  relationship_id VARCHAR(20) NOT NULL,
  relationship_name VARCHAR(255) NOT NULL,
  is_hierarchical VARCHAR(1) NOT NULL,
  defines_ancestry VARCHAR(1) NOT NULL,
  reverse_relationship_id VARCHAR(20) NOT NULL,
  relationship_concept_id INTEGER NOT NULL,
  PRIMARY KEY (relationship_id)
);

-- Concept synonyms for search (~10M rows)
CREATE TABLE concept_synonym (
  concept_id INTEGER NOT NULL,
  concept_synonym_name VARCHAR(1000) NOT NULL,
  language_concept_id INTEGER NOT NULL
);

-- Concept ancestors for hierarchy (~500M rows - optional, very large)
-- Uncomment if you need hierarchical queries (e.g., "all descendants of diabetes")
-- CREATE TABLE concept_ancestor (
--   ancestor_concept_id INTEGER NOT NULL,
--   descendant_concept_id INTEGER NOT NULL,
--   min_levels_of_separation INTEGER NOT NULL,
--   max_levels_of_separation INTEGER NOT NULL,
--   PRIMARY KEY (ancestor_concept_id, descendant_concept_id)
-- );

-- Source to concept mapping (if using custom source codes)
CREATE TABLE source_to_concept_map (
  source_code VARCHAR(50) NOT NULL,
  source_concept_id INTEGER NOT NULL,
  source_vocabulary_id VARCHAR(20) NOT NULL,
  source_code_description VARCHAR(255),
  target_concept_id INTEGER NOT NULL,
  target_vocabulary_id VARCHAR(20) NOT NULL,
  valid_start_date DATE NOT NULL,
  valid_end_date DATE NOT NULL,
  invalid_reason VARCHAR(1)
);

-- Drug strength (for drug dosage mapping)
CREATE TABLE drug_strength (
  drug_concept_id INTEGER NOT NULL,
  ingredient_concept_id INTEGER NOT NULL,
  amount_value NUMERIC,
  amount_unit_concept_id INTEGER,
  numerator_value NUMERIC,
  numerator_unit_concept_id INTEGER,
  denominator_value NUMERIC,
  denominator_unit_concept_id INTEGER,
  box_size INTEGER,
  valid_start_date DATE NOT NULL,
  valid_end_date DATE NOT NULL,
  invalid_reason VARCHAR(1)
);

-- Create foreign keys (after data load)
-- These will be created by 03-create-indexes.sql

COMMENT ON TABLE concept IS 'Core vocabulary table with ~6M clinical concepts from SNOMED, RxNorm, LOINC, etc.';
COMMENT ON TABLE concept_synonym IS 'Alternative names/synonyms for concepts, used for text search';
COMMENT ON TABLE concept_relationship IS 'Relationships between concepts (e.g., SNOMED -> RxNorm mappings)';
COMMENT ON COLUMN concept.standard_concept IS 'S = standard concept (use for queries), C = classification, NULL = map to standard first';
COMMENT ON COLUMN concept.concept_code IS 'Original code from source vocabulary (e.g., SNOMED code)';
