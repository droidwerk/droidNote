from __future__ import annotations

from pathlib import Path

UI_LANGUAGES = frozenset({"pt", "en", "es", "it", "de", "fr", "ru"})
CAPTURE_LANGUAGES = UI_LANGUAGES | {"auto"}

INSTALL_LANGIDS = {
    1046: "pt",
    1033: "en",
    1034: "es",
    3082: "es",
    1040: "it",
    1031: "de",
    1036: "fr",
    1049: "ru",
}

HTTP_MESSAGES: dict[str, dict[str, str]] = {
    "pt": {
        "session_missing": "Sessão não encontrada",
        "segment_missing": "Segmento não encontrado",
        "chat_missing": "Conversa não encontrada",
        "audio_missing": "Áudio WAV não encontrado",
        "token_invalid": "Token inválido",
        "asr_not_ready": "Modelo de transcrição ainda não está pronto",
        "llm_not_ready": "O motor de notas ainda não está pronto",
        "whisper_ready": "Modelo de transcrição pronto",
        "openai_key_missing": "Falta a chave da API OpenAI.",
        "whisper_not_downloaded": "Modelo de transcrição ainda não baixado neste PC. O DroidNote vai baixar o Whisper agora.",
    },
    "en": {
        "session_missing": "Session not found",
        "segment_missing": "Segment not found",
        "chat_missing": "Conversation not found",
        "audio_missing": "WAV audio not found",
        "token_invalid": "Invalid token",
        "asr_not_ready": "The transcription model is not ready yet",
        "llm_not_ready": "The notes engine is not ready yet",
        "whisper_ready": "Transcription model ready",
        "openai_key_missing": "The OpenAI API key is missing.",
        "whisper_not_downloaded": "The transcription model is not on this PC yet. DroidNote will download Whisper now.",
    },
    "es": {
        "session_missing": "Sesión no encontrada",
        "segment_missing": "Segmento no encontrado",
        "chat_missing": "Conversación no encontrada",
        "audio_missing": "Audio WAV no encontrado",
        "token_invalid": "Token no válido",
        "asr_not_ready": "El modelo de transcripción aún no está listo",
        "llm_not_ready": "El motor de notas aún no está listo",
        "whisper_ready": "Modelo de transcripción listo",
        "openai_key_missing": "Falta la clave de la API de OpenAI.",
        "whisper_not_downloaded": "El modelo de transcripción aún no está en este PC. DroidNote descargará Whisper ahora.",
    },
    "it": {
        "session_missing": "Sessione non trovata",
        "segment_missing": "Segmento non trovato",
        "chat_missing": "Conversazione non trovata",
        "audio_missing": "Audio WAV non trovato",
        "token_invalid": "Token non valido",
        "asr_not_ready": "Il modello di trascrizione non è ancora pronto",
        "llm_not_ready": "Il motore delle note non è ancora pronto",
        "whisper_ready": "Modello di trascrizione pronto",
        "openai_key_missing": "Manca la chiave API OpenAI.",
        "whisper_not_downloaded": "Il modello di trascrizione non è ancora su questo PC. DroidNote scaricherà Whisper ora.",
    },
    "de": {
        "session_missing": "Sitzung nicht gefunden",
        "segment_missing": "Segment nicht gefunden",
        "chat_missing": "Unterhaltung nicht gefunden",
        "audio_missing": "WAV-Audio nicht gefunden",
        "token_invalid": "Ungültiges Token",
        "asr_not_ready": "Das Transkriptionsmodell ist noch nicht bereit",
        "llm_not_ready": "Die Notizen-Engine ist noch nicht bereit",
        "whisper_ready": "Transkriptionsmodell bereit",
        "openai_key_missing": "Der OpenAI-API-Schlüssel fehlt.",
        "whisper_not_downloaded": "Das Transkriptionsmodell ist noch nicht auf diesem PC. DroidNote lädt Whisper jetzt herunter.",
    },
    "fr": {
        "session_missing": "Session introuvable",
        "segment_missing": "Segment introuvable",
        "chat_missing": "Conversation introuvable",
        "audio_missing": "Audio WAV introuvable",
        "token_invalid": "Jeton invalide",
        "asr_not_ready": "Le modèle de transcription n'est pas encore prêt",
        "llm_not_ready": "Le moteur de notes n'est pas encore prêt",
        "whisper_ready": "Modèle de transcription prêt",
        "openai_key_missing": "La clé API OpenAI est manquante.",
        "whisper_not_downloaded": "Le modèle de transcription n'est pas encore sur ce PC. DroidNote va télécharger Whisper maintenant.",
    },
    "ru": {
        "session_missing": "Сессия не найдена",
        "segment_missing": "Сегмент не найден",
        "chat_missing": "Разговор не найден",
        "audio_missing": "WAV-аудио не найдено",
        "token_invalid": "Недействительный токен",
        "asr_not_ready": "Модель транскрипции ещё не готова",
        "llm_not_ready": "Движок заметок ещё не готов",
        "whisper_ready": "Модель транскрипции готова",
        "openai_key_missing": "Отсутствует ключ API OpenAI.",
        "whisper_not_downloaded": "Модели транскрипции ещё нет на этом ПК. DroidNote сейчас загрузит Whisper.",
    },
}


def normalize_ui_language(value: str | None) -> str:
    code = (value or "pt").strip().lower()
    return code if code in UI_LANGUAGES else "pt"


def normalize_capture_language(value: str | None) -> str:
    code = (value or "pt").strip().lower()
    return code if code in CAPTURE_LANGUAGES else "pt"


def ui_message(locale: str | None, key: str) -> str:
    loc = normalize_ui_language(locale)
    table = HTTP_MESSAGES.get(loc) or HTTP_MESSAGES["pt"]
    return table.get(key) or HTTP_MESSAGES["pt"][key]


def read_install_language(data_dir: Path) -> str | None:
    path = Path(data_dir) / "install-lang.txt"
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    if raw.lower() in UI_LANGUAGES:
        return raw.lower()
    try:
        return INSTALL_LANGIDS.get(int(raw))
    except ValueError:
        return None
