# On part de l'image officielle
FROM ghcr.io/berriai/litellm:main-latest
USER root

# Copie des fichiers
COPY config.yaml /app/config.yaml
COPY cleaner.py /app/cleaner.py

# Permissions: give ownership to a non-root user and restrict mode
# Avoid world-writable files (chmod 777). Use chown and safer permissions.
RUN chown -R 1000:1000 /app && \
    chmod 644 /app/config.yaml /app/cleaner.py || true

# Create a non-root user 'appuser' with UID 1000 if it doesn't exist, and
# ensure /app is owned by that user. Some base images may require a named user
# entry in /etc/passwd for runtime, so we create it here.
RUN set -eux; \
    if ! id -u 1000 >/dev/null 2>&1; then \
    groupadd -g 1000 appuser || true; \
    useradd -m -u 1000 -g 1000 -s /bin/bash appuser || true; \
    fi; \
    chown -R appuser:appuser /app || true

# Installation des dépendances (si besoin, mais pas pour toi)
# RUN pip install bcrypt passlib  # Décommenter si tu en as besoin ailleurs

# Ensure a python3 binary exists for the container healthcheck.
# Try apt-get (Debian/Ubuntu) then apk (Alpine) to be portable across base images.
RUN set -eux; \
    if command -v python3 >/dev/null 2>&1; then \
    echo "python3 already present"; \
    elif command -v apt-get >/dev/null 2>&1; then \
    apt-get update && apt-get install -y --no-install-recommends python3 && rm -rf /var/lib/apt/lists/*; \
    elif command -v apk >/dev/null 2>&1; then \
    apk add --no-cache python3; \
    else \
    echo "No known package manager to install python3; healthcheck may fail"; \
    fi

# AJOUT CRUCIAL : Python cherche dans /app
ENV PYTHONPATH="/app"

ENV LITELLM_CONFIG_PATH="/app/config.yaml"

# Note: Some minimal base images do not include `useradd`/`groupadd`.
# If those utilities are missing the image build cannot create a passwd entry
# and switching to a named user at build time will make the container fail
# at startup ("unable to find user ..."). To keep compatibility we run as root
# here. If you want a non-root runtime, enable user creation in the Dockerfile
# (remove the "|| true" from the groupadd/useradd lines) on a base image
# that provides those tools, then switch to USER appuser.
USER root

CMD ["--config", "/app/config.yaml", "--port", "4000", "--detailed_debug"]
