import time
import os
from datetime import datetime, timedelta
import archivist   # Ton script V15
import summarizer  # Ton script ci-dessus
import config


def wait_for_db(path: str = None, timeout: int = 60):
    """Wait until the DB file exists and is readable.

    This replaces a fixed sleep() hack and cooperates better with Docker
    `depends_on` + healthchecks. Returns True if file available within timeout,
    False otherwise.
    """
    db_path = path or config.DB_DEFAULT_PATH
    start = time.time()
    while True:
        if os.path.exists(db_path):
            try:
                # Try opening read-only
                with open(db_path, 'rb'):
                    return True
            except Exception:
                pass
        if time.time() - start > timeout:
            return False
        time.sleep(1)


def main_loop():
    print("🤖 SYSTEME IA-MEMORY : DÉMARRAGE GLOBAL")

    # 1. SCAN IMMÉDIAT AU LANCEMENT (Pour ne pas attendre demain pour tester)
    print("\n--- 🚀 Lancement Cycle Initial ---")
    print("1. 📂 Exécution Archiviste...")
    archivist.scan_all()

    print("2. 🧠 Exécution Summarizer...")
    summarizer.run_summarization() # Cette fonction scanne tes fichiers et s'arrête quand fini

    print("--- ✅ Cycle Initial Terminé ---\n")

    # 2. BOUCLE INFINIE DU SCHEDULER
    while True:
        if config.INTERVAL_HOURS < 24:
            # Mode intervalle : toutes les X heures
            wait_seconds = config.INTERVAL_HOURS * 3600
            next_run = datetime.now() + timedelta(seconds=wait_seconds)
            print(f"💤 Système en veille. Prochain cycle toutes les {config.INTERVAL_HOURS}h : {next_run.strftime('%H:%M')} (dans {config.INTERVAL_HOURS}h)")
        else:
            # Mode horaire fixe
            wait_seconds, next_run = config.get_seconds_until_schedule()
            hours = int(wait_seconds // 3600)
            minutes = int((wait_seconds % 3600) // 60)
            print(f"💤 Système en veille. Prochain cycle : {next_run} (dans {hours}h {minutes}m)")

        # On dort
        time.sleep(wait_seconds)

        print(f"\n⏰ DRING ! Il est {datetime.now().strftime('%H:%M')}. Au travail !")

        # Séquence de travail
        try:
            print("📂 [1/2] Archivage DB -> JSON...")
            archivist.scan_all()

            print("🧠 [2/2] Résumé & Upload JSON -> AnythingLLM...")
            summarizer.run_summarization()

            print("✅ Cycle journalier terminé.")

        except Exception as e:
            print(f"❌ CRITICAL ERROR dans le cycle : {e}")

if __name__ == "__main__":
    # Wait for DB availability (mounted volume may take a short time)
    ok = wait_for_db()
    if not ok:
        print("❌ Timeout waiting for DB. Continuing anyway; scan may fail.")
    main_loop()
