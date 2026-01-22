#!/bin/bash

echo "🚀 Démarrage de l'installation de ta Stack IA..."

# 1. Vérification de Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker n'est pas installé ou détecté."
    echo "   Veuillez installer Docker Desktop ou Docker Engine."
    exit 1
fi

# 2. Création des dossiers (CRUCIAL pour les permissions Linux/Mac)
# Cela permet à l'utilisateur courant d'être propriétaire des dossiers, pas Root.
echo "📁 Création de l'arborescence..."
mkdir -p data/chat
mkdir -p data/memory
mkdir -p data/memory-worker/archives
mkdir -p data/memory-worker/markdowns
mkdir -p data/ollama
mkdir -p data/debug

# 3. Gestion du fichier .env
if [ ! -f .env ]; then
    echo "⚠️  Aucun fichier .env détecté."
    echo "📄 Copie du modèle .env.example vers .env..."
    cp .env.example .env
    echo "🛑 STOP ! Ouvre le fichier '.env' maintenant et ajoute tes clés API."
    echo "   Une fois fait, relance ce script."
    exit 1
else
    echo "✅ Fichier .env trouvé."
    # On charge les variables pour les afficher à la fin
    source .env
fi

# 4. Lancement de Docker
echo "🐳 Construction et démarrage des conteneurs..."
# Compatibilité docker compose v2 et v1
if docker compose version &> /dev/null; then
    docker compose up -d --build
else
    docker-compose up -d --build
fi

echo ""
echo "============================================"
echo "✨ INSTALLATION TERMINÉE !"
echo "📊 AnythingLLM    : http://localhost:${ANYTHING_PORT_HOST:-23001}"
echo "💬 Open WebUI     : http://localhost:${OPENWEBUI_PORT_HOST:-23002}"
echo "🤖 LiteLLM API    : http://localhost:${LITELLM_PORT_HOST:-23003}"
echo "🧠 Ollama (local) : http://localhost:${OLLAMA_PORT_HOST:-23004}"
echo "============================================"
echo "💡 N'oublie pas de télécharger le modèle de résumé :"
echo "   docker exec -it ia-ollama ollama pull ${BASE_MODEL:-qwen2.5:3b}"
