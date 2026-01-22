import os
import json
import requests
import glob
import time
import logging
import re
from datetime import datetime
from typing import Optional
import anything_client
import config as worker_config  # Module de configuration partagé

def normalize_to_ms(ts_val: any) -> Optional[int]:
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

def parse_date_to_ms(date_str: str) -> Optional[int]:
    """Parse date string like '2026-01-12 14:18:57' to milliseconds."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        return int(dt.timestamp() * 1000)
    except Exception:
        return None

# --- DEBUG MODE ---
# Mettre à True/False pour simuler l'IA et aller très vite sans appel API 
DEBUG_MODE = False

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('summarizer')

# --- CONFIGURATION ---
LITELLM_BASE_URL = (os.getenv("LITELLM_URL") or "").strip().rstrip('/')
LLM_API_URL = f"{LITELLM_BASE_URL}/chat/completions" if LITELLM_BASE_URL else ""

# Le modèle est défini dans le .env (ex: qwen2.5:3b ou phi3:mini)
MODEL_NAME = os.getenv("BASE_MODEL", "qwen2.5:3b")

ANY_KEY = os.getenv("ANYTHING_LLM_API_KEY")

# Paramètres depuis le module de configuration
ARCHIVE_DIR = worker_config.ARCHIVE_DEFAULT_PATH
MD_DIR = worker_config.MD_DEFAULT_PATH
# On peut surcharger le timeout via ENV, sinon config par défaut
API_TIMEOUT = int(os.getenv("LLM_TIMEOUT", worker_config.LLM_TIMEOUT))

# --- FONCTION API ---
def upload_to_anything(content_md: str, filename: str, workspace_slug: str) -> Optional[str]:
    """
    Envoie le résumé markdown à AnythingLLM via l'API.
    Gère la suppression de l'ancien document si nécessaire et trigger l'embedding.
    """
    if not ANY_KEY:
        logger.warning("❌ [API] Erreur : Pas de clé API configurée. Upload skipped.")
        return None

    logger.info(f"📡 [API] Envoi de {filename}...")

    doc_id, resp = anything_client.upload_document(content_md, filename, workspace_slug)
    if not doc_id:
        logger.error(f"❌ [API] Upload failed: {resp}. Contenu (début): {content_md[:200]}...")
        return None

    logger.info(f"   ✅ Upload réussi, doc_id={doc_id}")

    # Gestion de l'ancien ID pour éviter les doublons dans AnythingLLM
    _, entry = anything_client.find_entry_by_filename(filename)
    prev_id = None
    if entry:
        prev_id = entry.get('previous_any_document_id') or entry.get('any_document_id')

    if prev_id and prev_id != doc_id:
        try:
            deleted = anything_client.delete_document(prev_id, workspace_slug)
            if deleted:
                logger.info(f"   🗑️ Ancien document supprimé: {prev_id}")
            else:
                logger.warning(f"   ⚠️ Impossible de supprimer l'ancien document {prev_id}")
        except Exception as e:
            logger.warning(f"   ⚠️ Erreur suppression ancien document {prev_id}: {e}")

    # Mise à jour des embeddings (Vecteurs)
    anything_client.trigger_embeddings(workspace_slug)

    # Mise à jour du manifest local
    updated = anything_client.update_entry_docid(filename, doc_id)
    if updated:
        logger.info(f"   🔖 Manifest mis à jour avec any_document_id={doc_id}")
    else:
        logger.warning(f"   ⚠️ Impossible de mettre à jour le manifest pour {filename}")

    return doc_id

# --- FONCTION LLM (Résumé) ---
def summarize_chunk(text_chunk: str, workspace: str, date_str: str, part_number: int) -> str:
    """
    Envoie un bloc de conversation au LLM pour résumé.
    Optimisé pour la concision (listes à puces) sur des modèles locaux (CPU).
    """
    # 👇 DEBUG: Simulation pour ne pas consommer de CPU
    if DEBUG_MODE:
        logger.debug(f"   🐛 [DEBUG] Simulation résumé IA (Partie {part_number})")
        return f"- Point clé simulé 1\n- Point clé simulé 2 (Debug Mode)"

    # 👇 PROMPT OPTIMISÉ POUR CPU/LOCAL (Qwen, Phi-3)
    system_prompt = (
        f"Tu es un assistant technique chargé de synthétiser des logs de conversation ('{workspace}').\n"
        f"Ton objectif : Extraire l'essentiel en un minimum de mots.\n"
        f"RÈGLES ABSOLUES :\n"
        f"1. Ne fais AUCUNE phrase d'introduction ('Voici le résumé...') ni de conclusion.\n"
        f"2. Utilise UNIQUEMENT des listes à puces (- point clé).\n"
        f"3. Ignore les salutations et le bavardage.\n"
        f"4. Si le texte contient une solution technique, note-la précisément (commandes, paramètres).\n"
        f"5. Limite ta réponse à {worker_config.SUMMARY_WORD_LIMIT} mots maximum."
    )

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text_chunk}
        ],
        "temperature": 0.1, # Très bas pour être factuel
        "max_tokens": 500
    }

    try:
        if not LLM_API_URL:
            logger.error("LLM API URL not configured. Set LITELLM_URL env var.")
            return "[LLM NOT CONFIGURED]"

        response = requests.post(LLM_API_URL, json=payload, timeout=API_TIMEOUT)
        response.raise_for_status()

        raw_summary = response.json()['choices'][0]['message']['content']

        # --- Nettoyage post-LLM (Anti-écho) ---
        cleaned_summary = raw_summary
        system_marker = "### System:"
        user_marker = "### User:"

        # Si le modèle répète le prompt (défaut fréquent des petits modèles)
        if system_marker in cleaned_summary and user_marker in cleaned_summary:
            user_prompt_end_idx = cleaned_summary.find(user_marker)
            if user_prompt_end_idx != -1:
                # On cherche le début de la réponse réelle
                content_start_idx = cleaned_summary.find("\n\n", user_prompt_end_idx)
                if content_start_idx != -1:
                    cleaned_summary = cleaned_summary[content_start_idx:].strip()
                else:
                    first_newline = cleaned_summary.find("\n", user_prompt_end_idx)
                    if first_newline != -1:
                        cleaned_summary = cleaned_summary[first_newline:].strip()

        if not cleaned_summary:
            cleaned_summary = raw_summary

        return cleaned_summary

    except requests.exceptions.Timeout:
        logger.error(f"❌ [LLM] Timeout (>{API_TIMEOUT}s) sur la partie {part_number}.")
        return "[Timeout LLM]"
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ [LLM] Erreur API sur la partie {part_number}: {e}")
        return "[Erreur API LLM]"
    except Exception as e:
        logger.exception(f"❌ [LLM] Erreur inattendue partie {part_number}: {e}")
        return "[Erreur Inattendue LLM]"

def process_file(json_filepath: str):
    """
    Traite un fichier JSON : Découpage intelligent -> Résumé -> Upload.
    """
    # 1. Vérification marqueur .done
    done_marker = json_filepath + ".done"
    if os.path.exists(done_marker):
        if os.path.getmtime(done_marker) >= os.path.getmtime(json_filepath):
            return # Déjà traité

    # 2. Lecture du JSON
    try:
        with open(json_filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"❌ Erreur lecture JSON {json_filepath}: {e}")
        return

    base_name = os.path.basename(json_filepath)
    # Extract original filename by removing UUID if present
    uuid_pattern = r'-([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})\.json$'
    match = re.search(uuid_pattern, base_name)
    if match:
        original_filename = base_name[:-len(match.group(0))]  # remove -UUID.json
        summary_filename = original_filename
    else:
        summary_filename = base_name.replace(".json", "_summary.md")
    workspace_slug = data.get('workspace', 'default')

    logger.info(f"🚜 [SUMMARIZER] Traitement : {summary_filename}")

    msgs = data.get("messages", [])
    if not msgs:
        logger.warning(f"⚠️ Pas de messages dans {json_filepath}. Skipped.")
        return

    # --- 3. INCREMENTAL LOGIC ---
    md_path = os.path.join(MD_DIR, summary_filename)
    old_content = ""
    if os.path.exists(md_path):
        try:
            with open(md_path, 'r', encoding='utf-8') as f:
                old_content = f.read()
            logger.info(f"   📖 Ancien résumé chargé depuis {md_path}")
        except Exception as e:
            logger.warning(f"   ⚠️ Impossible de lire l'ancien résumé {md_path}: {e}")

    # Get last processed timestamp from manifest
    _, entry = anything_client.find_entry_by_filename(summary_filename)
    last_ts = entry.get('last_message_timestamp', 0) if entry else 0

    # Filter new messages
    new_msgs = [m for m in msgs if (parse_date_to_ms(m.get('date', '')) or 0) > last_ts]
    if not new_msgs:
        logger.info(f"   ⏭️ Aucun nouveau message depuis le dernier traitement. Skipped.")
        return

    logger.info(f"   🆕 {len(new_msgs)} nouveaux messages à traiter.")

    # --- 4. DÉCOUPAGE INTELLIGENT DES NOUVEAUX MESSAGES ---
    chunks = []
    current_chunk_str = ""
    msg_count_in_chunk = 0

    # Paramètres d'optimisation CPU/Contexte
    MAX_MSG_PER_CHUNK = 10    # Max 10 échanges pour ne pas noyer l'IA
    MAX_CHAR_PER_CHUNK = 3500 # Max caractères pour rester dans la fenêtre de contexte

    for m in new_msgs:
        u_text = m.get('user', '') or ""
        a_text = m.get('ai', '') or ""

        # Format lisible pour l'IA
        entry = f"User: {u_text}\nAI: {a_text}\n\n"

        # Si on dépasse la taille ou le nombre de messages, on coupe
        if (len(current_chunk_str) + len(entry) > MAX_CHAR_PER_CHUNK) or (msg_count_in_chunk >= MAX_MSG_PER_CHUNK):
            if current_chunk_str.strip():
                chunks.append(current_chunk_str)
            current_chunk_str = entry
            msg_count_in_chunk = 1
        else:
            current_chunk_str += entry
            msg_count_in_chunk += 1

    if current_chunk_str.strip():
        chunks.append(current_chunk_str)

    logger.info(f"   🧩 {len(chunks)} morceaux (basés sur les nouveaux messages) à traiter.")

    # --- 5. RÉSUMÉ PAR L'IA DES NOUVEAUX CHUNKS ---
    summary_date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title_name = original_filename if 'original_filename' in locals() else base_name.replace('.json', '')
    if old_content:
        # Append to old content
        final_content = old_content + f"\n## Mise à jour : {summary_date_str}\n\n"
    else:
        final_content = f"# Mémoire : {title_name}\n**Workspace:** {workspace_slug} | **Date:** {summary_date_str}\n\n"

    for i, chunk in enumerate(chunks):
        logger.info(f"   ⏳ Morceau {i+1}/{len(chunks)}...")
        res = summarize_chunk(chunk, workspace_slug, summary_date_str, i + 1)
        final_content += f"### Partie {len(chunks) - len(chunks) + i + 1}\n{res}\n\n"  # Adjust part number if appending

        # Petite pause pour laisser souffler le CPU si besoin
        if not DEBUG_MODE:
            time.sleep(1)

    # --- 6. SAUVEGARDE DU RÉSUMÉ LOCAL ---
    try:
        os.makedirs(MD_DIR, exist_ok=True)
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(final_content)
        logger.info(f"   💾 Résumé sauvegardé localement : {md_path}")
    except Exception as e:
        logger.error(f"   ❌ Erreur sauvegarde résumé local {md_path}: {e}")

    # --- 7. ENVOI API ---
    success = upload_to_anything(final_content, summary_filename, workspace_slug)

    # --- 8. MISE À JOUR MANIFEST AVEC TIMESTAMP ---
    if success:
        # Update manifest with last message timestamp
        max_ts = max((parse_date_to_ms(m.get('date', '')) or 0 for m in msgs), default=0)
        anything_client.update_entry_timestamp(summary_filename, max_ts)
        with open(done_marker, 'w') as f:
            f.write("uploaded_via_api")
        logger.info(f"   🏁 Cycle terminé pour {base_name}")
    else:
        logger.error(f"❌ Échec upload pour {base_name}. Pas de marqueur .done créé.")

def run_summarization():
    """
    Point d'entrée principal : Scanne le dossier archives.
    """
    logger.info("🧠 SUMMARIZER V2 (Smart Chunking + Strict Prompt) : START")
    
    path_pattern = os.path.join(worker_config.ARCHIVE_DEFAULT_PATH, "**", "*.json")
    files = sorted(glob.glob(path_pattern, recursive=True))
    
    if not files:
        logger.info(f"   Aucun fichier JSON trouvé dans {worker_config.ARCHIVE_DEFAULT_PATH}")
        return

    for i, f in enumerate(files):
        # On ignore les fichiers .done , manifest.json et autres fichiers non-json
        if not f.endswith(".json"):
            continue
        if os.path.basename(f) == "manifest.json":
            logger.debug(f"   ⏩ Ignoré : {f} (fichier manifest)")
            continue
    
        process_file(f)
        
        # Pause entre les fichiers pour le Rate Limit
        if i < len(files) - 1:
            time.sleep(worker_config.RATE_LIMIT_SLEEP)

if __name__ == "__main__":
    run_summarization()