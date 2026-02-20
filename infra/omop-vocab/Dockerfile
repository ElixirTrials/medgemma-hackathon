FROM postgres:16-alpine

# Install required tools
RUN apk add --no-cache bash

# Create directory for vocabulary files
RUN mkdir -p /vocab-data

# Copy initialization scripts
COPY infra/omop-vocab/init-vocab-schema.sql /docker-entrypoint-initdb.d/01-init-vocab-schema.sql
COPY infra/omop-vocab/load-vocab.sh /docker-entrypoint-initdb.d/02-load-vocab.sh
COPY infra/omop-vocab/create-indexes.sql /docker-entrypoint-initdb.d/03-create-indexes.sql

# Make scripts executable
RUN chmod +x /docker-entrypoint-initdb.d/02-load-vocab.sh

# Set environment variables
ENV POSTGRES_DB=omop_vocab
ENV POSTGRES_USER=postgres
ENV POSTGRES_PASSWORD=postgres

VOLUME /vocab-data

EXPOSE 5432
