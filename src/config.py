from __future__ import annotations
class P:
    """Provider 이름 상수"""
    LMSTUDIO = "🖥️ LM Studio (로컬)"
    OLLAMA   = "🦙 Ollama (로컬)"
    WEBLLM   = "🌐 WebLLM (브라우저)"
    OPENAI   = "🤖 OpenAI ChatGPT"
    GEMINI   = "✨ Google Gemini"
    CLAUDE   = "🎭 Anthropic Claude"
    ALL      = [OPENAI, GEMINI, CLAUDE, LMSTUDIO, OLLAMA, WEBLLM]

# --- PDF 분석 관련 설정 ---
LOCAL_PDF_MAX_PAGES = 50
CLOUD_PDF_MAX_PAGES = 100

def get_max_pdf_pages(provider: str) -> int:
    """Provider에 따른 최대 PDF 분석 페이지 수 반환"""
    if provider in [P.LMSTUDIO, P.OLLAMA, P.WEBLLM]:
        return LOCAL_PDF_MAX_PAGES
    return CLOUD_PDF_MAX_PAGES
# ------------------------

PROVIDER_MODELS: dict[str, list[str]] = {
    P.LMSTUDIO: [],
    P.OLLAMA: ["gemma:2b", "gemma2:9b", "llama3.1:8b", "llama3.2:3b", "qwen2.5:7b", "mistral:7b"],
    P.WEBLLM: ["gemma-2b-q4f16_1-MLC", "Llama-3-8B-Instruct-q4f16_1-MLC"],
    P.OPENAI: [
        "gpt-5.4", "gpt-5.4-pro", "gpt-5.4-mini", "gpt-5.4-nano", "gpt-4.1", "o4-mini", "o3",
    ],
    P.GEMINI: [
        "gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash",
    ],
    P.CLAUDE: [
        "claude-opus-4-7", "claude-opus-4-5", "claude-sonnet-4-6", "claude-sonnet-4-5", "claude-haiku-3-5", "claude-3-5-sonnet-20241022",
    ],
}

OPENAI_COMPAT_ENDPOINTS: dict[str, str] = {
    P.LMSTUDIO: "http://localhost:1234/v1/chat/completions",
    P.OLLAMA:   "http://localhost:11434/v1/chat/completions",
    P.OPENAI:   "https://api.openai.com/v1/chat/completions",
    P.GEMINI:   "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
}

PROVIDER_KEY_HINTS: dict[str, tuple[str, str]] = {
    P.OPENAI: ("https://platform.openai.com/api-keys", "sk-..."),
    P.GEMINI: ("https://aistudio.google.com/apikey", "AIza..."),
    P.CLAUDE: ("https://console.anthropic.com/settings/keys", "sk-ant-..."),
}

LMSTUDIO_PREFERRED = [
    "google/gemma-4-e4b",
    "google/gemma-4-31b",
    "qwen3.5-9b-claude-4.6-opus-reasoning-distilled-v2",
]

DEFAULT_SAMPLING = {"temperature": 1.0, "top_p": 0.95}
MAX_IMAGE_SIZE   = 1920

_PDF_TEXT_MIN_CHARS_PER_PAGE = 80
