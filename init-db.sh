#!/bin/sh
# Create the scanner's own role and database inside the existing Postgres
# (ADR-0026). Idempotent: safe to run on every `up`.
#
# The scanner gets a SEPARATE database and a SEPARATE login that owns only that
# database. It never receives the server's credentials, so a compromised scanner
# (it runs untrusted third-party packages) cannot read users, tokens or config.
#
# Runs as the Postgres superuser, once, from the init service, then exits.
# Expects: PGHOST, PGUSER, PGPASSWORD (admin), SCANNER_DB_PASSWORD (new role).
set -eu

: "${SCANNER_DB_PASSWORD:?set SCANNER_DB_PASSWORD}"

# A role name or password containing a quote would break the statement, so refuse
# anything that is not a plain token rather than trying to escape it.
case "$SCANNER_DB_PASSWORD" in
  *[\'\"\\]*) echo "SCANNER_DB_PASSWORD must not contain quotes or backslashes" >&2; exit 1 ;;
esac

# Role: create if missing, otherwise just refresh the password.
psql -v ON_ERROR_STOP=1 -d postgres <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'scanner') THEN
    CREATE ROLE scanner LOGIN PASSWORD '${SCANNER_DB_PASSWORD}'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
  ELSE
    ALTER ROLE scanner PASSWORD '${SCANNER_DB_PASSWORD}';
  END IF;
END
\$\$;
SQL

# Database: CREATE DATABASE cannot run inside a transaction or DO block.
exists=$(psql -At -d postgres -c "SELECT 1 FROM pg_database WHERE datname = 'scanner'")
if [ "$exists" != "1" ]; then
  psql -v ON_ERROR_STOP=1 -d postgres -c "CREATE DATABASE scanner OWNER scanner"
fi

# Lock the door both ways.
#
# Postgres grants CONNECT on every new database to the special PUBLIC group, so
# revoking it from the scanner ROLE alone does nothing: the role simply inherits
# it from PUBLIC. Verified on a throwaway instance: with only a role-level
# revoke, the scanner could still open the server's database. The revoke has to
# target PUBLIC. The database owner (the server's login) keeps its own access
# through ownership, so the server is unaffected.
psql -v ON_ERROR_STOP=1 -d postgres <<SQL
REVOKE ALL ON DATABASE scanner FROM PUBLIC;
GRANT CONNECT ON DATABASE scanner TO scanner;
REVOKE CONNECT ON DATABASE mcpc FROM PUBLIC;
SQL

echo "scanner role and database ready"
