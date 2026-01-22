#!/bin/bash

echo "🚀 Démarrage de l'installation de ta Stack IA..."

# 1. Création des dossiers nécessaires (pour éviter les erreurs de permissions Docker)
echo "📁 Création de l'arborescence..."
mkdir -p data/chat
mkdir -p data/memory
mkdir -p data/memory-worker/archives
mkdir -p data/ollama
mkdir -p data/debug

# 2. Gestion du fichier .env
if [ ! -f .env ]; then
    echo "⚠️  Aucun fichier .env détecté."
    echo "📄 Copie du modèle .env.example vers .env..."
    cp .env.example .env
    echo "🛑 STOP ! Ouvre le fichier '.env' maintenant et ajoute tes clés API."
    echo "Une fois fait, relance ce script."
    exit 1
else
    echo "✅ Fichier .env trouvé."
fi

# 3. Lancement de Docker
echo "🐳 Construction et démarrage des conteneurs..."
docker compose up -d --build

echo "============================================"
echo "✨ INSTALLATION TERMINÉE !"
echo "📊 AnythingLLM : http://localhost:${ANYTHING_PORT_HOST:-23001}"
echo "💬 Open WebUI  : http://localhost:${OPENWEBUI_PORT_HOST:-23002}"
echo "🤖 LiteLLM : http://localhost:${LITELLM_PORT_HOST:-23003}"
echo "🧠 Ollama (local) : http://localhost:${OLLAMA_PORT_HOST:-23004}"
echo "============================================"
