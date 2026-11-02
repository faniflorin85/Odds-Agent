"""Backend LLM interschimbabil. Modelul doar EXPLICĂ biletele calculate, nu le alege.

none   - fără LLM (cost zero, fără setup)
ollama - model local în Docker (gratuit; viteza depinde de PC)
openai - orice API compatibil OpenAI (OpenAI, Gemini compat, Groq, OpenRouter...)
"""
from __future__ import annotations

import json

import httpx

from .config import Settings

SYSTEM_PROMPT = (
    "Ești un analist prudent de pariuri sportive. Răspunzi în română, scurt și clar. "
    "Primești biletele deja calculate (JSON). NU modifici cote, probabilități sau meciuri "
    "și NU inventezi statistici, accidentări sau forma echipelor, pentru că nu ai aceste date. "
    "Pentru fiecare bilet explică în 1-2 propoziții de ce arată rezonabil sau riscant "
    "(număr de selecții, probabilitatea combinată estimată, valoarea așteptată). "
    "Încheie cu o avertizare scurtă că rezultatul nu este garantat."
)


class LLMError(RuntimeError):
    pass


def build_user_prompt(payload: dict) -> str:
    return "Biletele calculate:\n" + json.dumps(payload, ensure_ascii=False, indent=2)


class LLM:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self._client = client or httpx.Client(timeout=settings.llm_timeout)

    @property
    def enabled(self) -> bool:
        return self.settings.llm_backend in {"ollama", "openai"}

    def explain(self, payload: dict) -> str | None:
        backend = self.settings.llm_backend
        if backend == "none":
            return None
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(payload)},
        ]
        try:
            if backend == "ollama":
                return self._ollama(messages)
            if backend == "openai":
                return self._openai(messages)
        except httpx.HTTPStatusError as error:
            raise LLMError(f"Modelul a răspuns HTTP {error.response.status_code}.") from None
        except httpx.HTTPError as error:
            raise LLMError(f"Conexiune eșuată către model ({type(error).__name__}).") from None
        except (KeyError, ValueError, IndexError):
            raise LLMError("Răspuns neașteptat de la model.") from None
        raise LLMError(f"LLM_BACKEND necunoscut: {backend}")

    def _ollama(self, messages: list[dict]) -> str:
        response = self._client.post(
            f"{self.settings.ollama_url}/api/chat",
            json={
                "model": self.settings.ollama_model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.2},
            },
        )
        response.raise_for_status()
        return response.json()["message"]["content"].strip()

    def _openai(self, messages: list[dict]) -> str:
        if not self.settings.llm_api_key:
            raise LLMError("LLM_API_KEY lipsește pentru LLM_BACKEND=openai.")
        response = self._client.post(
            f"{self.settings.llm_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.settings.llm_api_key}"},
            json={"model": self.settings.llm_model, "messages": messages},
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
