import sqlite3
import json
import os
import time
import glob
import tempfile
import hashlib
import logging
from datetime import datetime, timedelta, time as dt_time
from typing import Any, Dict, List, Optional, Tuple
import config as worker_config # Module de configuration partagé

# --- CONFIGURATION ---
# DB_PATH est maintenant récupéré via worker_config
# ARCHIVE_DEFAULT_PATH est maintenant récupéré via worker_config
# SCHEDULE_TIME_STR est maintenant passé en argument depuis main.py

# logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('archivist')

# --- UTILITAIRES ---
def clean_filename(text: str) -> str:
    """
    Nettoie une chaîne de caractères pour en faire un nom de fichier sûr.
    """
    if not text: return "unknown"
    safe = "".join([c if c.isalnum() or c in " _-" else "_" for c in text])
    return safe.strip().replace(" ", "_")[:60]

def force_permissions(path: str, is_dir: bool = False):
    """
    Applique des permissions par défaut sécurisées aux fichiers et répertoires.
    Pour les fichiers: 0o644 (rw-r--r--)
    Pour les répertoires: 0o755 (rwxr-xr-x)
    """
    try:
        if is_dir:
            os.chmod(path, 0o755) # rwxr-xr-x
        else:
            os.chmod(path, 0o644) # rw-r--r--
    except Exception as e:
        logger.debug(f"Impossible d'appliquer les permissions à {path}: {e}")

def clean_ai_response(response_text: Optional[str]) -> str:
    """Nettoie le JSON imbriqué de l'IA pour avoir du texte propre.
    Tente d'extraire le champ 'text' d'une réponse JSON potentiellement structurée,
    sinon retourne le texte brut.
    """
    if not response_text: return ""
    if not response_text.strip().startswith("{"): return response_text
    try:
        parsed = json.loads(response_text)
        if isinstance(parsed, dict) and 'text' in parsed:
            return parsed['text']

    except json.JSONDecodeError as e:
        logger.debug(f"clean_ai_response: Not a valid JSON, trying text extraction. Error: {e}")
    try:
        if 'text":"' in response_text:
            start = response_text.find('text":"') + 7
            end = response_text.find('","sources"', start)
            if end == -1: end = response_text.find('"}', start)
            if end != -1:
                return response_text[start:end].replace('\\"', '"').replace('\\n', '\n')

    except Exception as e:
        logger.debug(f"clean_ai_response: Error during text extraction from JSON-like string: {e}")
    return response_text

def format_date(timestamp_val: Any) -> str:
    """Convertit un timesta mp (secondes ou millisecondes) en date lisible.

    The DB can store createdAt as seconds or milliseconds. We detect the
    magnitude and normalize to milliseconds before formatting.
    """
    try:
        if timestamp_val is None:
            return ""
        ts_ms = normalize_to_ms(timestamp_val)
        if ts_ms is None:
            return str(timestamp_val)
        return datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(timestamp_val)

def normalize_to_ms(ts_val: Any) -> Optional[int]:
    """Return timestamp in milliseconds (int) given ts_val in seconds or ms.

    Returns None when ts_val cannot be parsed.
    """
    try:
        t = int(ts_val)
    except Exception:
        return None
    if t > 1_000_000_000_000:
        return t
    if t > 1_000_000_000:
        return t * 1000
    return t

def get_db_connection() -> sqlite3.Connection:
    """
    Établit une connexion en lecture seule à la base de données SQLite.
    """
    return sqlite3.connect(f"file:{worker_config.DB_DEFAULT_PATH}?mode=ro", uri=True)

def save_json(workspace_name: str, filename: str, data: Dict[str, Any]):
    """
    Écrit le JSON seulement si le contenu a changé pour éviter de réveiller
    le Summarizer inutilement.
    """
    safe_ws = clean_filename(workspace_name)
    ws_dir = os.path.join(worker_config.ARCHIVE_DEFAULT_PATH, safe_ws) # Utilise ARCHIVE_DEFAULT_PATH du config
    
    if not os.path.exists(ws_dir):
        os.makedirs(ws_dir, exist_ok=True)
        try:
            force_permissions(ws_dir, is_dir=True)
        except Exception:
            pass

    filepath = os.path.join(ws_dir, f"{filename}.json")

    # --- 🔽 AJOUT : VÉRIFICATION INTELLIGENTE 🔽 ---
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
            
            # On compare le contenu (Python gère très bien la comparaison de dicts profonds)
            # Si c'est identique, on ne touche à rien (la date de modif reste vieille)
            if existing_data == data:
                # logger.debug(f"   💤 [ARCHIVIST] Pas de changement pour {filename}")
                return
        except Exception as e:
            logger.warning(f"Impossible de lire l'ancien fichier {filepath} pour comparaison: {e}")
    # --- 🔼 FIN AJOUT 🔼 ---

    # Si on arrive ici, c'est que le fichier est nouveau ou différent
    try:
        with tempfile.NamedTemporaryFile('w', delete=False, dir=ws_dir, encoding='utf-8', suffix='.tmp') as tf:
            json.dump(data, tf, indent=2, ensure_ascii=False)
            tempname = tf.name
        
        os.replace(tempname, filepath)
        force_permissions(filepath)
        logger.info(f"   💾 [ARCHIVIST] Sauvegardé (Nouveau/Modifié) : {safe_ws}/{filename}.json")
    except Exception as e:
        logger.error(f"Erreur écriture JSON {filepath}: {e}")

# --- CLEANUP ---
def delete_ghost_files(workspace_name: str, valid_ids: List[int]):
    """
    Supprime les fichiers JSON d'archives qui ne correspondent plus
    à des threads existants dans la base de données AnythingLLM.
    """
    safe_ws = clean_filename(workspace_name)
    ws_dir = os.path.join(worker_config.ARCHIVE_DEFAULT_PATH, safe_ws)
    if not os.path.exists(ws_dir): return

    files = glob.glob(os.path.join(ws_dir, "*.json"))
    for f in files:
        fname = os.path.basename(f)
        if fname == "default.json": continue # Ignorer un éventuel fichier default.json
        try:
            base = fname[:-5] # Retire ".json"
            parts = base.rsplit('_', 1) # Sépare le nom du thread de l'ID
            if len(parts) > 1 and parts[1].isdigit():
                fid = int(parts[1])
                if fid not in valid_ids:
                    os.remove(f)
                    print(f"   🗑️ [CLEANUP] Fantôme supprimé : {fname}")
        except Exception as e:
            logger.debug(f"Erreur lors du nettoyage du fichier fantôme {fname}: {e}")

# --- SCAN PROCESS ---
def process_workspace(cursor: sqlite3.Cursor, ws_id: int, ws_name: str):
    """
    Traite un espace de travail AnythingLLM : extrait les threads nommés
    et le thread default (messages sans thread_id) et les sauvegarde en JSON.
    """
    logger.info(f"📂 Workspace : {ws_name}")

    # 1. THREADS NOMMÉS (Table: workspace_threads / Col: workspace_id)
    cursor.execute("SELECT id, name FROM workspace_threads WHERE workspace_id = ?", (ws_id,))
    threads = cursor.fetchall()
    valid_ids = [t['id'] for t in threads]

    for thread in threads:
        t_id = thread['id']
        t_name = thread['name']

        # Table: workspace_chats / Col: thread_id
        cursor.execute("SELECT prompt, response, createdAt FROM workspace_chats WHERE thread_id = ? ORDER BY id ASC", (t_id,))
        messages = cursor.fetchall()
        if not messages:
            continue

        # If thread name is missing or is the generic 'Thread', prefer the first user message
        first_user = messages[0]['prompt'] if messages and messages[0] and messages[0]['prompt'] else None
        if t_name and str(t_name).strip() and str(t_name).strip().lower() != 'thread':
            final_title = t_name
        elif first_user:
            # use first sentence of first_user
            sentence = str(first_user).split('\n')[0]
            sentence = sentence.split('.')[0].split('?')[0].split('!')[0].strip()
            final_title = sentence if sentence else f"Thread_{t_id}"
        else:
            final_title = f"Thread_{t_id}"

        # Ajout de format_date() ici
        msgs_formatted = []
        for m in messages:
            msgs_formatted.append({
                "date": format_date(m['createdAt']),
                "user": m['prompt'],
                "ai": clean_ai_response(m['response'])
            })

        data = {
            "id": t_id,
            "type": "thread",
            "workspace": ws_name,
            "title": final_title,
            "messages": msgs_formatted
        }
        # filename contains cleaned title and thread id for traceability
        save_json(ws_name, f"{clean_filename(final_title)}_{t_id}", data)

    # 2. DEFAULT THREAD (Table: workspace_chats / Col: workspaceId)
    # ATTENTION: Ici on utilise workspaceId (CamelCase) comme tu l'as validé
    cursor.execute("""
        SELECT prompt, response, createdAt
        FROM workspace_chats
        WHERE workspaceId = ? AND thread_id IS NULL
        ORDER BY id ASC
    """, (ws_id,))

    default_msgs = cursor.fetchall()
    if default_msgs:
        # Ajout de format_date() ici aussi
        msgs_formatted = []
        for m in default_msgs:
            msgs_formatted.append({
                "date": format_date(m['createdAt']),
                "user": m['prompt'],
                "ai": clean_ai_response(m['response'])
            })
        data = {
            "id": "default",
            "type": "default_thread",
            "workspace": ws_name,
            "title": "defaultThread",
            "messages": msgs_formatted
        }
        # name default files explicitly so you can spot them easily
        save_json(ws_name, f"defaultThread_{ws_id}", data)
    # 3. NETTOYAGE
    delete_ghost_files(ws_name, valid_ids)

def scan_all():
    """
    Scanne tous les espaces de travail dans la base de données AnythingLLM
    et archive leurs conversations.
    """
    if not os.path.exists(worker_config.DB_DEFAULT_PATH):
        logger.error("❌ DB introuvable: %s", worker_config.DB_DEFAULT_PATH)
        raise FileNotFoundError(f"Database not found at {worker_config.DB_DEFAULT_PATH}") # Lève une erreur pour le retry
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, name FROM workspaces")
        workspaces = cursor.fetchall()
        for ws in workspaces:
            process_workspace(cursor, ws['id'], ws['name'])
        logger.info("✅ Cycle terminé.")
    except Exception as e:
        logger.exception("❌ Erreur lors du scan_all: %s", e)
        raise # Re-lève l'exception pour que tenacity puisse la capturer
    finally:
        conn.close()

# Fonction appelée par main.py
def run_archiving():
   """
   Lance le processus d'archivage des conversations AnythingLLM.
   Cette fonction est désormais appelée par main.py.
   """
   logger.info("烙 ARCHIVIST V15 (Dates Formatées) : DÉMARRÉ")

   try:
       logger.info("🚀 Lancement du scan initial...")
       scan_all()
   except Exception as e:
       logger.exception("❌ Erreur pendant l'archivage initial: %s", e)
       raise

   # La boucle de scheduling est maintenant gérée par main.py

if __name__ == "__main__":
    # Si archivist.py est exécuté directement, il utilise une heure par défaut
    # pour le scheduling (ici 4h du matin).
    # En production, il est appelé par main.py qui lui passe l'heure.
    default_scheduled_time = dt_time(hour=4, minute=0, second=0, microsecond=0)
    run_archiving()
