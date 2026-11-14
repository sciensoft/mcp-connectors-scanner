# Connector security scanner image.
#
# Everything the scanner needs lives in this image so that NOTHING is installed
# or executed on the host. The scanner resolves and inspects untrusted
# third-party packages, so it runs as an unprivileged user, with no database
# credentials and no .env (see ADR-0026).
#
# Tool versions are pinned build args so a rebuild is reproducible. Bump them
# deliberately; the scan DBs (Trivy, OSV) refresh at runtime regardless.

ARG TRIVY_VERSION=0.58.1
ARG OSV_SCANNER_VERSION=2.0.0

FROM aquasec/trivy:${TRIVY_VERSION} AS trivy

FROM ghcr.io/google/osv-scanner:v${OSV_SCANNER_VERSION} AS osv

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# git for shallow clones of git-pinned connectors, nodejs/npm to resolve npm
# trees lockfile-only (--ignore-scripts), ca-certificates for registry TLS.
RUN apt-get update && \
    apt-get install -y --no-install-recommends git nodejs npm ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY --from=trivy /usr/local/bin/trivy /usr/local/bin/trivy
COPY --from=osv /osv-scanner /usr/local/bin/osv-scanner

# GuardDog (malicious-code heuristics), Cisco mcp-scanner (tool poisoning, YARA
# analyzer works offline), and uv for resolving PyPI trees without installing.
RUN pip install guarddog cisco-ai-mcp-scanner uv "psycopg[binary]>=3.2"

# GuardDog refreshes its list of popular packages (used for typosquatting
# checks) by writing into its own install directory. The runtime filesystem is
# read-only, so prime both lists here, while it is still writable. One scan of
# a tiny well-known package per ecosystem triggers the download. This also
# removes a scan-time dependency on GitHub.
RUN guarddog npm scan is-odd --version 3.0.1 >/dev/null 2>&1 || true; \
    guarddog pypi scan six --version 1.16.0 >/dev/null 2>&1 || true; \
    ls /usr/local/lib/python3.12/site-packages/guarddog/analyzer/metadata/resources/ | grep -c top_ || true

RUN useradd --create-home --uid 10002 scanner && \
    mkdir -p /work /out && chown scanner:scanner /work /out

WORKDIR /app
COPY engine/ ./engine/

USER scanner

# Scan work happens under /work (ephemeral), results land in /out.
ENV SCAN_WORK_DIR=/work \
    SCAN_OUT_DIR=/out

EXPOSE 9090

CMD ["python3", "-m", "engine.main"]
