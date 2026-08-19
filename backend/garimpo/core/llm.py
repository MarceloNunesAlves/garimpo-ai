"""Construção do chat model a partir da configuração salva no banco."""

from __future__ import annotations

from typing import Any

PROVIDERS = ("openai", "anthropic", "ollama")

DEFAULT_MODELS = {
    "anthropic": "claude-opus-5",
    "openai": "gpt-4.1-mini",
    "ollama": "llama3.1",
}

# Modelos Claude atuais não aceitam `temperature`; enviar o parâmetro quebra a
# chamada. A lista abaixo é usada para decidir o que repassar ao provider.
MODEL_CHOICES = {
    "anthropic": [
        "claude-opus-5",
        "claude-sonnet-5",
        "claude-opus-4-8",
        "claude-haiku-4-5",
    ],
    "openai": ["gpt-4.1-mini", "gpt-4.1", "gpt-4o", "gpt-4o-mini"],
    "ollama": ["llama3.1", "qwen2.5", "mistral"],
}


def build_llm(config: Any):
    """Recebe um `AIConfig` (ou objeto com os mesmos campos) e devolve o chat model."""
    provider = (config.provider or "").lower().strip()
    model = config.model or DEFAULT_MODELS.get(provider)
    extra = dict(getattr(config, "extra", None) or {})

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        kwargs: dict[str, Any] = {
            "model": model,
            # O padrão de 1024 tokens trunca o código e o JSON dos agentes.
            "max_tokens": config.max_tokens or 16000,
        }
        if config.api_key:
            kwargs["api_key"] = config.api_key
        if config.base_url:
            kwargs["base_url"] = config.base_url
        return ChatAnthropic(**kwargs, **extra)

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        kwargs = {"model": model}
        if config.api_key:
            kwargs["api_key"] = config.api_key
        if config.base_url:
            kwargs["base_url"] = config.base_url
        if config.temperature is not None:
            kwargs["temperature"] = config.temperature
        if config.max_tokens:
            kwargs["max_tokens"] = config.max_tokens
        return ChatOpenAI(**kwargs, **extra)

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        kwargs = {"model": model}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        if config.temperature is not None:
            kwargs["temperature"] = config.temperature
        return ChatOllama(**kwargs, **extra)

    raise ValueError(f"Provider desconhecido: {config.provider!r}")


def check_llm(config: Any) -> dict[str, Any]:
    """Testa a configuração com um prompt mínimo. Usado pelo botão 'Testar'."""
    try:
        llm = build_llm(config)
        resp = llm.invoke("Responda apenas: ok")
        text = getattr(resp, "content", str(resp))
        if isinstance(text, list):  # blocos de conteúdo (Anthropic)
            text = " ".join(
                b.get("text", "") for b in text if isinstance(b, dict)
            ).strip()
        return {"ok": True, "reply": str(text)[:200]}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
