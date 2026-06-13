#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE ragtime_db_user WITH LOGIN PASSWORD '$DB_PASSWORD';
    GRANT ALL PRIVILEGES ON DATABASE ragtime_db TO ragtime_db_user;
    GRANT CONNECT ON DATABASE ragtime_db TO ragtime_db_user;
EOSQL
