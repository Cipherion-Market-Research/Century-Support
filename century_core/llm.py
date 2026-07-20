"""Pluggable guarded-LLM provider for the Q&A path.

The LLM's job is narrow: phrase a natural-language answer using ONLY the
supplied context (retrieved facts/KPIs/RAG chunks) — never invent numbers,
never solicit a purchase. guardrails.py enforces this structurally on the
output regardless of what the model actually does, so nothing here has to
be trusted blindly. Same pluggable-provider pattern as
pubs_rag/embeddings.py: "openai" (modern SDK) in production, "stub" for
tests — selected by CENTURY_CORE_LLM_PROVIDER.
"""
from abc import ABC, abstractmethod

from century_core.config import Config

SYSTEM_PROMPT = (
    "You are Century, the official Ciphex (CPX) support assistant. Answer ONLY using "
    "the CONTEXT block below — it contains verified facts, live KPIs, and publication "
    "excerpts with their sources. Rules:\n"
    "- Never state a number, date, or figure that does not appear verbatim in CONTEXT.\n"
    "- Never tell the user to buy, invest, or that now is a good time to buy CPX.\n"
    "- Never state or imply an APY, yield, or guaranteed return.\n"
    "- If CONTEXT does not answer the question, say you don't know and point to the "
    "official site rather than guessing.\n"
    "- Keep the answer concise (2-4 sentences)."
)


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, question: str, context: str) -> str:
        ...


class OpenAILLMProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        from openai import AsyncOpenAI

        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for the openai LLM provider")
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def generate(self, question: str, context: str) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}"},
            ],
            temperature=0.2,
            max_tokens=300,
        )
        return response.choices[0].message.content or ""


class StubLLMProvider(LLMProvider):
    """Deterministic, network-free provider for tests: returns a scripted
    string, a scripted callable's result, or a benign templated echo of the
    context when nothing is scripted."""

    def __init__(self, response=None):
        self._response = response

    async def generate(self, question: str, context: str) -> str:
        if callable(self._response):
            return self._response(question, context)
        if self._response is not None:
            return self._response
        return f"Based on the available information: {context[:200]}"


def get_llm_provider(config: type = Config) -> LLMProvider:
    provider = config.LLM_PROVIDER.lower()
    if provider == "openai":
        return OpenAILLMProvider(config.OPENAI_API_KEY, config.LLM_MODEL)
    if provider == "stub":
        return StubLLMProvider()
    raise ValueError(f"unknown CENTURY_CORE_LLM_PROVIDER: {provider!r}")
