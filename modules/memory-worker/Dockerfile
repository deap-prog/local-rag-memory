# Image Python légère
FROM python:3.10-slim

# 1. Création d'un utilisateur non-root dédié
ARG UID=1000
ARG GID=1000
RUN set -eux; \
    if ! id -u ${UID} >/dev/null 2>&1; then \
    groupadd -g ${GID} workeruser || true; \
    useradd -m -u ${UID} -g ${GID} -s /bin/bash workeruser || true; \
    fi; \
    chown -R workeruser:workeruser /app || true

# Dossier de travail
WORKDIR /app

# Copie et installation des dépendances minimales (pymongo)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du script
COPY . .

# 2. Assurer les permissions pour l'utilisateur du worker
RUN chown -R workeruser:workeruser /app

# 3. Exécution en tant qu'utilisateur non-root
USER workeruser

# Lancement (-u permet de voir les logs instantanément)
CMD ["python", "-u", "main.py"]