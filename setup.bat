@echo off
echo ==================================================
echo 🚀 INITIALISATION DE L'IA LOCALE (Windows)
echo ==================================================

:: 1. Vérification et création du .env
if exist .env (
    echo [INFO] Le fichier .env existe deja. On ne l'ecrase pas.
) else (
    echo [ACTION] Creation du fichier .env a partir de .env.example...
    copy .env.example .env
    echo [OK] Fichier .env cree !
    echo ⚠️  IMPORTANT : Pensez a editer le fichier .env avec vos cles API avant de continuer.
    echo.
)

:: 2. Vérification de Docker
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERREUR] Docker n'est pas detecte !
    echo Veuillez installer Docker Desktop pour Windows.
    pause
    exit /b
)

:: 3. Lancement des conteneurs
echo [ACTION] Lancement de Docker Compose...
docker-compose up -d --build

echo.
echo ==================================================
echo ✅ INSTALLATION TERMINEE !
echo ==================================================
echo.
echo Accès a AnythingLLM : http://localhost:23001
echo Accès a OpenWebUI   : http://localhost:23002
echo.
echo N'oubliez pas de configurer AnythingLLM (voir README).
echo.
pause
