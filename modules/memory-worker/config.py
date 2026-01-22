import os
from datetime import datetime, timedelta

# --- CONFIGURATION GLOBALE DU WORKER (peut etre surchargé via .env)---

# Chemin par défaut de la base de données AnythingLLM (en lecture seule)
DB_DEFAULT_PATH = os.getenv("DB_PATH", "/app/source_db/anythingllm.db")
# Chemin par défaut pour les archives JSON générées par l'archivist
ARCHIVE_DEFAULT_PATH = os.getenv("ARCHIVE_PATH", "/app/archives")
# Chemin par défaut pour les résumés Markdown sauvegardés localement
MD_DEFAULT_PATH = os.getenv("MD_PATH", "/app/markdowns")
# Heure de l'archivage Format HH:MM (24h) ou intervalle en heures
SCHEDULE_TIME_STR = os.getenv("SUMMARY_TIME", "04:00")
INTERVAL_HOURS = int(os.getenv("INTERVAL_HOURS", "24"))

# Temps d'attente initial avant de tenter de se connecter à la DB (en secondes)
# Sera utilisé avec tenacity pour les retries
INITIAL_DB_CONNECT_DELAY_SECONDS = 5
MAX_DB_CONNECT_RETRIES = 10

# Temps entre chaque traitement de fichier JSON par le summarizer (en secondes)
RATE_LIMIT_SLEEP = int(os.getenv("RATE_LIMIT_SLEEP", "5"))
# Taille des morceaux de texte envoyés au LLM pour résumé (en caractères)
SUMMARY_CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "3000"))
# Limite de mots pour chaque résumé de morceau de texte par le LLM
SUMMARY_WORD_LIMIT = int(os.getenv("WORD_LIMIT", "200")) # Pour forcer la concision
# Timeout pour les appels API des LLM (en secondes)
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "600"))


def get_seconds_until_schedule(schedule_time_str: str = None):
    """Return tuple(seconds_until_next_run, next_run_datetime).

    schedule_time_str: string like '04:00' or '4h' or '04:00:00'. If omitted,
    uses the SCHEDULE_TIME_STR from the environment.

    The function normalizes formats and returns how many seconds remain until
    the next occurrence of that time (tomorrow if already past today).
    """
    clean_time = (schedule_time_str or SCHEDULE_TIME_STR).lower().replace('h', ':')
    if clean_time.isdigit():
        clean_time = "04:00"

    try:
        parts = clean_time.split(':')
        target_hour = int(parts[0])
        target_minute = int(parts[1]) if len(parts) > 1 else 0
    except Exception:
        target_hour, target_minute = 4, 0

    now = datetime.now()
    target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)

    return (target - now).total_seconds(), target
