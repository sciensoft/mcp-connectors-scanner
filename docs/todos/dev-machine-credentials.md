# Recreate the dev machine's scanner credentials

- **Area:** Operations / secrets
- **Refs:** `.env.example`, `Makefile`

## Context

The development machine (hrollers) runs the scanner with a copy of the production
`.env`: the same database password, API token and feed token. That was a shortcut to
get it running. It means a leak of the dev file would expose production credentials,
and the values also passed through a connector call log when copied.

## What to do

Generate fresh values on the development machine only (a new database password and two
new tokens, as described in `.env.example`) and point it at its own application server
and database, so the two machines no longer share any secret.

## Revisit when

- The dev machine and the production machine need to run different scanner versions, or
- Before anyone else gets access to the dev machine, or
- At the next token rotation for production, whichever comes first.
