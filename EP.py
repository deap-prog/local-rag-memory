import os

# --- CONFIGURATION ---
ROOT_DIR = "."  # Dossier courant
OUTPUT_FILE = "projet_complet.txt"

# Dossiers à EXCLURE (ne rentre pas dedans)
EXCLUDE_DIRS = {"data", ".git", "__pycache__", "node_modules", "archives", "documents", "vectors", "backup", ".devcontainer", ".venv"}

# Extensions de fichiers à INCLURE
INCLUDE_EXTS = {".py", ".yml", ".yaml", ".txt", ".env", ".json"}
INCLUDE_FILES = {"Dockerfile", "docker-compose.yml", "requirements.txt", "README.md"}

def pack_project():
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        for root, dirs, files in os.walk(ROOT_DIR):
            # 1. On retire les dossiers exclus de la liste de recherche
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

            for file in files:
                # 2. On vérifie si le fichier nous intéresse
                is_valid = file in INCLUDE_FILES or any(file.endswith(ext) for ext in INCLUDE_EXTS)

                if is_valid:
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read()
                            out.write(f"\n\n{'='*50}\n")
                            out.write(f"📂 FICHIER : {filepath}\n")
                            out.write(f"{'='*50}\n")
                            out.write(content)
                            print(f"✅ Ajouté : {filepath}")
                    except Exception as e:
                        print(f"❌ Erreur lecture {filepath}: {e}")

    print(f"\n✨ Terminé ! Tout est dans '{OUTPUT_FILE}'")

if __name__ == "__main__":
    pack_project()
