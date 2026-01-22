# 🧠 Mon IA Locale avec Mémoire Autonome

Ce projet déploie une stack complète d'IA générative locale pour étudiants et développeurs. Il combine un système de chat avancé (RAG), une passerelle de sécurisation et un **archiviste autonome** qui transforme vos conversations en mémoire à long terme.

> **Note pour les étudiants :** Ce projet est optimisé pour fonctionner avec un abonnement **Google Gemini Pro** (via l'API) pour une fenêtre de contexte large, couplé à une recherche web via **Tavily** pour combler les lacunes de connaissances post-2023.

## 🏗️ Architecture

- **AnythingLLM** : Interface de chat et gestionnaire de documents (RAG).
- **LiteLLM** : Passerelle unifiée qui centralise les modèles (Gemini, Groq, Ollama) et **nettoie les données sensibles** (anonymisation) avant envoi.
- **Memory Worker** : Script autonome qui :
  1. Archive les conversations à intervalle régulier.
  2. Résume les échanges via un modèle local (Ollama).
  3. Upload les résumés dans AnythingLLM (pour vectorisation future).
- **Ollama** : Moteur local pour l'IA de résumé (gratuit et hors-ligne).

## 🚀 Installation

### Prérequis
* [Docker Desktop](https://www.docker.com/products/docker-desktop/) installé.
* Au moins **16 Go de RAM** (recommandé pour faire tourner les résumés en local).
* Clés API optionnelles (si vous utilisez Groq, Gemini ou OpenAI), sinon tout peut tourner en local via Ollama.

## 🚀 Installation (Windows)

### 1. Prérequis
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installé et lancé.
- Une clé API **Google Gemini** (Requis pour le chat principal).
- Une clé API **Tavily** (Requis pour la recherche web à jour).

### 2. Démarrage Automatique
Nous avons inclus un script pour faciliter l'installation.

1. Double-cliquez sur le fichier `setup.bat`.
   * *Il créera automatiquement le fichier `.env` s'il n'existe pas.*
2. **STOP !** Avant que tout ne démarre vraiment, ouvrez le fichier `.env` créé et **collez vos clés API** (Gemini, Tavily, etc.).
3. Relancez `setup.bat` ou exécutez `docker-compose up -d --build`.

### 3. Téléchargement du modèle de résumé
Le "Memory Worker" utilise une petite IA locale pour résumer vos textes sans frais. Une fois les conteneurs lancés, ouvrez un terminal et tapez :

```bash
docker exec -it ia-ollama ollama pull qwen2.5:3b

### Démarrage Rapide

1.  **Cloner le projet :**
    ```bash
    git clone [https://github.com/votre-pseudo/votre-repo.git](https://github.com/votre-pseudo/votre-repo.git)
    cd votre-repo
    ```

2.  **Initialisation :**
    * **Windows** : Double-cliquez sur `setup.bat` (si disponible) ou copiez `.env.example` en `.env`.
    * **Linux/Mac** :
        ```bash
        cp .env.example .env
        # Ou lancez ./setup.sh si fourni
        ```

3.  **Configuration :**
    Ouvrez le fichier `.env` généré et renseignez vos clés API (Groq, Gemini...) ou laissez vide si vous n'utilisez que du local. D'autres paramètres sont aussi configurable.

4.  **Lancement :**
    ```bash
    docker-compose up -d --build
    ```

5.  **📥 Téléchargement des modèles (Important) :**
    Une fois les conteneurs lancés, vous devez télécharger les modèles pour Ollama (utilisés par le Memory Worker).

    Exécutez cette commande dans votre terminal :
    ```bash
    docker exec -it ia-ollama ollama pull qwen2.5:3b
    docker exec -it ia-ollama ollama pull mistral
    ```
    *Note : Le modèle `qwen2.5:3b` est configuré par défaut pour les résumés dans le `.env`.*

## 🔗 Accès aux Interfaces

| Service | URL | Description |
| :--- | :--- | :--- |
| **AnythingLLM** | http://localhost:23001 | Chat principal avec mémoire vectorielle |
| **Open WebUI** | http://localhost:23002 | Chat secondaire (UI alternative gpt like) |
| **LiteLLM Proxy** | http://localhost:23003 | API compatible OpenAI (Port 4000 interne) |
| **Ollama API** | http://localhost:23004 | API du moteur local |

## 📂 Fonctionnement de la Mémoire

Vos données sont stockées localement :
* Base de données : `./data/memory/anythingllm.db`
* Archives brutes : `./data/memory-worker/archives/`
* Résumés Markdown : `./data/memory-worker/markdowns/`

**Cycle de vie du Memory Worker :**
1.  À intervalle régulier (configuré dans `.env`, ex: 04h00 du matin), le worker se réveille.
2.  Il détecte les nouvelles conversations.
3.  Il génère un résumé concis via le modèle local (Qwen/Phi).
4.  Il upload ce résumé dans AnythingLLM.
5.  **Résultat :** Le lendemain, vous pouvez demander à l'IA : *"De quoi avons-nous parlé hier concernant le projet X ?"* et elle saura vous répondre.

## 🛠️ Personnalisation

Le fichier `.env` contrôle la majorité des paramètres :
* `SUMMARY_TIME` : Heure du résumé automatique.
* `BASE_MODEL` : Modèle utilisé pour résumer (doit être léger, ex: qwen2.5:3b).
* `WORD_LIMIT` : Longueur max des résumés.

⚙️ Configuration AnythingLLM (Tuto)

Une fois l'installation terminée, accédez à http://localhost:23001. Vous devez configurer le logiciel pour qu'il utilise notre architecture.
Étape 1 : Connecter l'IA (LiteLLM)

Au lieu de connecter Gemini directement, nous passons par notre proxy sécurisé LiteLLM.

    Allez dans les Settings (roue dentée) > LLM Preference.

    Dans la liste des fournisseurs, choisissez LiteLLM (ou "Generic OpenAI").

    Base URL : Entrez exactement cette adresse (c'est l'adresse interne du réseau Docker) : http://ia-litellm:4000/v1

    API Key : Mettez n'importe quoi (ex: sk-fake), LiteLLM gère les vraies clés.

    Chat Model ID : Sélectionnez le modèle souhaité (ex: gemini/gemini-1.5-pro ou groq/llama-3).

Étape 2 : Activer la Recherche Web (Indispensable)

Les modèles IA ont une connaissance arrêtée dans le passé (2023/2024). Pour qu'ils puissent répondre sur l'actualité ou des docs récents :

    Allez dans Agent Skills (ou "Tools").

    Activez Web Search.

    Choisissez Tavily comme moteur de recherche.

    Entrez votre clé API Tavily.

Étape 3 : La Mémoire (Vectorisation Manuelle)

Le "Memory Worker" upload automatiquement les résumés de vos conversations précédentes dans votre Workspace, mais il ne lance pas le calcul vectoriel lourd.

    De temps en temps, allez dans les paramètres de votre Workspace.

    Vérifiez la liste des documents : vous verrez des fichiers .md ajoutés par le worker (ex: conversation_summary.md).

    Cliquez sur "Save and Embed" (ou "Re-embed") pour que l'IA "apprenne" ces nouveaux souvenirs.

        Pourquoi manuel ? Cela évite de surcharger votre processeur à chaque petit résumé et vous permet de vérifier ce qui est ajouté à la mémoire.

🔗 Accès Rapides

    Interface Chat : http://localhost:23001

    LiteLLM API : http://localhost:23003

    Dossier des données : Les conversations sont stockées localement dans ./data/.
