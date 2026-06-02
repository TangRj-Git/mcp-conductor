"""Rule-based first-pass capability selection."""

from __future__ import annotations

import math
import re
from collections import Counter

from mcp_conductor.models import CapabilityCard

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[\u3400-\u9fff]+")
_CJK_PATTERN = re.compile(r"^[\u3400-\u9fff]+$")
_BM25_K1 = 1.2
_BM25_B = 0.75


def select_candidate_cards(
        cards: list[CapabilityCard],
        *,
        user_task: str,
        limit: int,
) -> list[CapabilityCard]:
    """Select the capability cards that best match the user task text."""
    query_terms = [
        term
        for term in _tokenize(user_task)
        if len(term) >= 2
    ]
    if not query_terms:
        return cards[:limit]

    documents = [_card_tokens(card) for card in cards]
    average_length = sum(len(document) for document in documents) / max(len(documents), 1)
    document_frequencies = _document_frequencies(documents)

    def score(document: list[str]) -> float:
        frequencies = Counter(document)
        document_length = max(len(document), 1)
        score_value = 0.0
        for term in query_terms:
            term_frequency = frequencies[term]
            if term_frequency == 0:
                continue
            document_frequency = document_frequencies[term]
            inverse_document_frequency = math.log(
                1 + (len(documents) - document_frequency + 0.5)
                / (document_frequency + 0.5)
            )
            denominator = term_frequency + _BM25_K1 * (
                1 - _BM25_B + _BM25_B * document_length / max(average_length, 1)
            )
            score_value += (
                inverse_document_frequency
                * term_frequency
                * (_BM25_K1 + 1)
                / denominator
            )
        return score_value

    # Preserve the input order for equal scores so recommendations stay stable.
    scored = [
        (score(document), index, card)
        for index, (card, document) in enumerate(zip(cards, documents, strict=True))
    ]
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [card for _, _, card in scored[:limit]]


def _card_tokens(card: CapabilityCard) -> list[str]:
    tokens: list[str] = []
    tokens.extend(_tokenize(card.name) * 3)
    tokens.extend(_tokenize(card.description or ""))
    tokens.extend(_tokenize(" ".join(card.tags)) * 2)
    tokens.extend(_tokenize(card.input_summary or ""))
    tokens.extend(_tokenize(card.output_summary or ""))
    return tokens


def _tokenize(text: str) -> list[str]:
    normalized = text.replace("_", " ").replace("-", " ").lower()
    tokens: list[str] = []
    for raw_token in _TOKEN_PATTERN.findall(normalized):
        if _CJK_PATTERN.fullmatch(raw_token):
            tokens.extend(_cjk_ngrams(raw_token))
        else:
            tokens.append(raw_token)
    return tokens


def _cjk_ngrams(text: str) -> list[str]:
    tokens: list[str] = []
    max_width = min(4, len(text))
    for width in range(1, max_width + 1):
        for index in range(0, len(text) - width + 1):
            tokens.append(text[index:index + width])
    return tokens


def _document_frequencies(documents: list[list[str]]) -> Counter[str]:
    frequencies: Counter[str] = Counter()
    for document in documents:
        frequencies.update(set(document))
    return frequencies
