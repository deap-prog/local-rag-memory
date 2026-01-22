import re
import logging
from typing import Optional, Literal, Union
from litellm.integrations.custom_logger import CustomLogger
from litellm.proxy._types import UserAPIKeyAuth
from litellm.caching import DualCache
from litellm._logging import verbose_proxy_logger  # Pour logger proprement dans LiteLLM

verbose_proxy_logger.setLevel(logging.INFO)  # Ou DEBUG pour plus de détails

class SensitiveInfoRedactor(CustomLogger):
    async def async_pre_call_hook(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        cache: DualCache,
        data: dict,
        call_type: Literal["completion", "text_completion", "embeddings", "image_generation", "moderation", "audio_transcription"]
    ) -> Optional[Union[dict, str]]:
        try:
            verbose_proxy_logger.info("🔥 SÉCURITÉ : MODE PRE-CALL HOOK ACTIVÉ 🔥")

            # On cible les messages (dans 'messages' ou ailleurs si besoin)
            messages = data.get("messages", [])
            if not messages:
                verbose_proxy_logger.info("Pas de messages à redacter.")
                return data

            redaction_rules = [
                (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), '[REDACTED_EMAIL]'),
                (re.compile(r'\b(sk|pk|rk|ghp)_[a-zA-Z0-9]{20,}\b'), '[REDACTED_API_KEY]'),
                (re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'), '[REDACTED_IPV4]'),
                # Ajoute d'autres règles si besoin (ex: paths sensibles comme /home/...)
                (re.compile(r'/home/\w+/llm/'), '[REDACTED_PATH]'),
            ]

            modified_count = 0
            for message in messages:
                if isinstance(message, dict) and "content" in message and isinstance(message["content"], str):
                    original = message["content"]
                    modified = original
                    for pattern, replacement in redaction_rules:
                        modified = pattern.sub(replacement, modified)

                    if original != modified:
                        verbose_proxy_logger.info(f"--- ✂️ CENSURE APPLIQUÉE ✂️ ---")
                        verbose_proxy_logger.info(f"Avant : {original[:30]}...")
                        verbose_proxy_logger.info(f"Après : {modified[:30]}...")
                        message["content"] = modified
                        modified_count += 1

            if modified_count > 0:
                verbose_proxy_logger.info(f"✅ {modified_count} éléments censurés avant envoi.")

            return data  # Renvoie le data modifié

        except Exception as e:
            verbose_proxy_logger.error(f"❌ ERREUR CRITIQUE CLEANER: {e}")
            raise e  # Ou return "Erreur interne" pour rejeter

# Instance globale (obligatoire pour le config.yaml)
redactor_instance = SensitiveInfoRedactor()
