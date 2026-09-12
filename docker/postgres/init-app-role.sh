#!/bin/sh
# Create the least-privilege runtime role on first database bootstrap.
#
# Runs once via /docker-entrypoint-initdb.d on an empty data volume. The
# application role can never bypass row-level security (NOSUPERUSER,
# NOBYPASSRLS); migrations keep running as the bootstrap superuser through
# a separate PG_DSN. Keep APP_DB_PASSWORD alphanumeric in local development:
# it is interpolated into SQL below.
set -eu

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${APP_DB_PASSWORD:?APP_DB_PASSWORD is required for the runtime role}"
: "${WORKER_DB_PASSWORD:?WORKER_DB_PASSWORD is required for the worker role}"

psql -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    -v app_pw="$APP_DB_PASSWORD" \
    -v worker_pw="$WORKER_DB_PASSWORD" \
    -v db_name="$POSTGRES_DB" <<'EOSQL'
DO $do$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'travel_app') THEN
        CREATE ROLE travel_app LOGIN NOSUPERUSER NOBYPASSRLS
            NOCREATEDB NOCREATEROLE NOREPLICATION;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'travel_worker') THEN
        CREATE ROLE travel_worker LOGIN NOSUPERUSER NOBYPASSRLS
            NOCREATEDB NOCREATEROLE NOREPLICATION;
    END IF;
END
$do$;
-- Password assignment stays outside the DO body: psql variables do not
-- expand inside dollar-quoted strings.
ALTER ROLE travel_app WITH LOGIN NOSUPERUSER NOBYPASSRLS
    NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD :'app_pw';
ALTER ROLE travel_worker WITH LOGIN NOSUPERUSER NOBYPASSRLS
    NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD :'worker_pw';
GRANT CONNECT ON DATABASE :"db_name" TO travel_app;
GRANT CONNECT ON DATABASE :"db_name" TO travel_worker;
GRANT USAGE ON SCHEMA public TO travel_app;
GRANT USAGE ON SCHEMA public TO travel_worker;
-- NEITHER role receives a table grant here, deliberately. This script's job is
-- role lifecycle: create the role, give it LOGIN and CONNECT, give it USAGE on
-- the schema. Table privileges belong to migrations, for two reasons.
--
-- 1. This script runs from /docker-entrypoint-initdb.d on an empty data volume,
--    BEFORE Alembic has created any table. `GRANT ... ON ALL TABLES` is a
--    harmless no-op in that state, but a per-table grant is not: it fails with
--    `relation "..." does not exist`, and because this script runs under
--    `set -eu` with `psql -v ON_ERROR_STOP=1`, that aborts the bootstrap and the
--    database container never starts.
-- 2. A default privilege here would expose every future table to the role
--    automatically, which is the opposite of least privilege.
--
-- Migration 20260910_04 creates both roles and migration 20260911_05 enumerates
-- exactly the verbs each one needs, after the tables exist.
EOSQL
