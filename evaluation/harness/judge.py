"""Answer-correctness judges.

The default judge is fully offline: it checks whether the expected terms
appear in the answer. When a Groq API key is available, an LLM judge can be
used instead for a more lenient, semantic decision. Both implement the
same :class:`AnswerJudge` protocol.
"""

from typing import Protocol

from app.services.groq_service import GROQ_BASE_URL, GroqChatClient

from evaluation.harness.scores import answer_correct

_JUDGE_SYSTEM = (
    "You are an evaluation judge. Decide whether the ANSWER contains the "
    "facts described by the EXPECTED TERMS in the context of the QUESTION. "
    "The answer may paraphrase. Reply with exactly one word: CORRECT or "
    "INCORRECT."
)


class AnswerJudge(Protocol):
    """Verdict on whether a generated answer captures the expected facts."""

    def verdict(self, question: str, answer: str, expected_terms: list[str]) -> bool: ...


class TermJudge:
    """Offline judge: enough expected terms must appear in the answer."""

    def __init__(self, threshold: float = 0.5) -> None:
        self._threshold = threshold

    def verdict(self, question: str, answer: str, expected_terms: list[str]) -> bool:
        return answer_correct(answer, expected_terms, threshold=self._threshold)


class LLMJudge:
    """Semantic judge powered by Groq's chat-completions API."""

    def __init__(self, client: GroqChatClient) -> None:
        self._client = client

    def verdict(self, question: str, answer: str, expected_terms: list[str]) -> bool:
        if not expected_terms:
            return True
        prompt = (
            f"QUESTION: {question}\n"
            f"EXPECTED TERMS: {', '.join(expected_terms)}\n"
            f"ANSWER: {answer}"
        )
        reply = self._client.complete(
            [
                {"role": "system", "content": _JUDGE_SYSTEM},
                {"role": "user", "content": prompt},
            ]
        )
        return reply.strip().upper().startswith("CORRECT")


def build_judge(settings=None) -> AnswerJudge:
    """Return a semantic Groq judge when a key is set, else the offline one."""
    if settings is None:
        from app.core.config import get_settings

        settings = get_settings()
    if settings.groq_api_key:
        return LLMJudge(
            client=GroqChatClient(
                api_key=settings.groq_api_key,
                model=settings.groq_model,
                base_url=GROQ_BASE_URL,
                timeout=settings.groq_timeout_seconds,
            )
        )
    return TermJudge()