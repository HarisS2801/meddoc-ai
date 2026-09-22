"""Hybrid retrieval for RAG: keyword-first, vector-boosted.

Groq — the only AI provider in MedDoc AI — has no embedding API, so the
vector store uses deterministic local lexical vectors. Those pure-hash
vectors are too coarse to match real patient phrasings ("sugar" vs the
report's "glucose", "HbA1c" vs "Glycated Haemoglobin"), and chunk noise
pushes every cosine distance near 1.0, so a lexical gate on distance alone
silently drops relevant chunks.

Retrieval therefore combines two signals, both strictly scoped to the
selected ``document_ids`` (cross-document leakage is impossible):

1. **Keyword overlap** against the authoritative chunk text in SQLite.
   The query terms are expanded through a general medical synonym lexicon
   (retrieval-time rewriting only — never the answer itself), so test
   names and everyday phrasings (`sugar`, `blood sugar`, `HbA1c`,
   `diabetes`) can reach the chunk that holds the exact value.
2. **Lexical-vector cosine** from ChromaDB, used as a ranking boost and
   tie-breaker rather than a hard gate.

Medical values travel byte-for-byte: the chunk text handed to Groq is the
exact stored document text, so ``6.4 mmol/L`` stays ``6.4 mmol/L``.
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import DocumentChunk
from app.services import vector_store as vector_store_module
from app.services.embedding_service import build_embedding_service

logger = get_logger("retrieval")

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Closed-class / empty filler tokens that add no evidence of relevance.
_STOPWORDS = frozenset(
    (
        "a", "an", "and", "are", "as", "at", "be", "been", "being", "but",
        "by", "can", "could", "did", "do", "does", "for", "from", "had",
        "has", "have", "he", "her", "his", "how", "i", "if", "in", "into",
        "is", "it", "its", "of", "on", "or", "she", "should", "so", "than",
        "that", "the", "their", "them", "then", "there", "these", "they",
        "this", "to", "was", "we", "were", "what", "when", "where", "which",
        "who", "will", "with", "would", "you", "your",
        "not", "no", "my", "me", "am", "our", "us", "ok", "okay",
        "please", "please", "kindly", "thanks", "sir", "madam",
    )
)

# Single letters and fully generic words carry no retrieval evidence on
# their own. They are matched but never counted as a hit.
_GENERIC_TERMS = frozenset(
    {
        "level", "levels", "value", "values", "result", "results",
        "report", "test", "tests", "normal", "range", "reference",
        "unit", "interval", "flag", "date", "number", "status",
    }
)

# Medical synonym lexicon used for retrieval-time query expansion.
# Adding a term here widens *which chunks may be considered*, never what
# the LLM says — the answer always comes from the retrieved document text.
_TERM_EXPANSIONS: dict[str, set[str]] = {
    # glucose / sugar family
    "glucose": {"glucose", "sugar", "glycaemia", "glycemia", "glycaemic", "glycemic", "fpg", "fbs"},
    "sugar": {"sugar", "glucose", "glycaemia", "glycemia", "glycaemic", "glycemic"},
    "sugars": {"sugar", "glucose", "glycaemia", "glycemia"},
    "blood": {"blood", "glucose", "sugar", "serum", "plasma"},
    "glycaemia": {"glycaemia", "glycemia", "glucose", "sugar"},
    "glycemia": {"glycemia", "glycaemia", "glucose", "sugar"},
    "glycaemic": {"glycaemic", "glycemic", "glucose", "sugar"},
    "glycemic": {"glycemic", "glycaemic", "glucose", "sugar"},
    # HbA1c family
    "hba1c": {"hba1c", "a1c", "glycated", "glycosylated", "haemoglobin", "hemoglobin", "glycohemoglobin", "glycohaemoglobin"},
    "a1c": {"a1c", "hba1c", "glycated", "haemoglobin", "hemoglobin"},
    "glycated": {"glycated", "glycosylated", "hba1c", "a1c", "haemoglobin", "hemoglobin"},
    "glycosylated": {"glycosylated", "glycated", "hba1c", "a1c", "haemoglobin", "hemoglobin"},
    # haemoglobin: keep Hb/HGB/Haemoglobin connected to the FBC family so
    # a glucose-style question about blood cells still finds the count.
    "haemoglobin": {"haemoglobin", "hemoglobin", "hba1c", "a1c", "glycated", "hb", "hgb", "fbc", "cbc", "full"},
    "hemoglobin": {"hemoglobin", "haemoglobin", "hba1c", "a1c", "glycated", "hb", "hgb", "fbc", "cbc", "full"},
    # diabetes family
    "diabetes": {"diabetes", "diabetic", "glucose", "sugar", "hba1c", "glycated", "glycaemia", "glycemia", "glycaemic", "glycemic"},
    "diabetic": {"diabetic", "diabetes", "glucose", "sugar", "hba1c"},
    # lipid panel
    "cholesterol": {"cholesterol", "lipids", "lipid", "ldl", "hdl", "triglyceride", "triglycerides"},
    "lipid": {"lipid", "lipids", "cholesterol", "ldl", "hdl", "triglyceride"},
    "ldl": {"ldl", "cholesterol", "lipid", "lipids"},
    "hdl": {"hdl", "cholesterol", "lipid", "lipids"},
    "triglyceride": {"triglyceride", "triglycerides", "lipids", "lipid", "cholesterol"},
    "triglycerides": {"triglycerides", "triglyceride", "lipids", "lipid", "cholesterol"},
    # renal
    "creatinine": {"creatinine", "kidney", "renal", "egfr", "gfr"},
    "kidney": {"kidney", "renal", "creatinine", "egfr", "gfr"},
    "renal": {"renal", "kidney", "creatinine", "egfr", "gfr"},
    "egfr": {"egfr", "gfr", "creatinine", "kidney", "renal"},
    "gfr": {"gfr", "egfr", "creatinine", "kidney", "renal"},
    # liver panel
    "alt": {"alt", "alanine", "transaminase", "sgot", "sgpt"},
    "ast": {"ast", "aspartate", "transaminase", "sgot"},
    "sgpt": {"sgpt", "alt", "alanine", "transaminase"},
    "sgot": {"sgot", "ast", "aspartate", "transaminase"},
    "transaminase": {"transaminase", "alt", "ast", "alanine", "aspartate"},
    # blood pressure
    "pressure": {"pressure", "bp", "systolic", "diastolic"},
    "bp": {"bp", "blood", "pressure", "systolic", "diastolic"},
    # body composition
    "bmi": {"bmi", "weight", "body", "obesity"},
    "weight": {"weight", "bmi", "body", "obesity"},
    # Full Blood Count (FBC) / Complete Blood Count (CBC) family. The report
    # spells the full name; users may ask with the acronym or a near synonym.
    "fbc": {"fbc", "full", "blood", "count"},
    "cbc": {"cbc", "complete", "blood", "count"},
    "full": {"full", "fbc", "cbc", "blood", "count", "complete"},
    "complete": {"complete", "cbc", "fbc", "blood", "count", "full"},
    "count": {"count", "fbc", "cbc", "blood"},
    # white blood cells
    "wbc": {"wbc", "white", "blood", "cell", "cells", "leucocyte", "leucocytes", "leukocyte", "leukocytes"},
    "wcc": {"wcc", "wbc", "white", "blood", "cell", "cells", "leucocyte", "leukocyte"},
    "white": {"white", "wbc", "wcc", "blood", "cell", "cells", "leucocyte", "leukocyte"},
    "leucocyte": {"leucocyte", "leucocytes", "leukocyte", "leukocytes", "wbc", "wcc", "white", "blood", "cell"},
    "leukocyte": {"leukocyte", "leukocytes", "leucocyte", "leucocytes", "wbc", "wcc", "white", "blood", "cell"},
    # red blood cells
    "rbc": {"rbc", "red", "blood", "cell", "cells", "erythrocyte", "erythrocytes"},
    "red": {"red", "rbc", "blood", "cell", "cells", "erythrocyte"},
    "erythrocyte": {"erythrocyte", "erythrocytes", "rbc", "red", "blood", "cell"},
    # platelets
    "platelet": {"platelet", "platelets", "plt", "thrombocyte", "thrombocytes"},
    "platelets": {"platelets", "platelet", "plt", "thrombocyte", "thrombocytes"},
    "plt": {"plt", "platelet", "platelets", "thrombocyte", "thrombocytes"},
    "thrombocyte": {"thrombocyte", "thrombocytes", "platelet", "platelets", "plt"},
}


def termize(text: str) -> set[str]:
    """Return the lowercase alphanumeric terms of ``text``."""
    return set(_TOKEN_RE.findall(text.lower()))


def expand_query_terms(question: str) -> set[str]:
    """Return the content terms of the question plus medical synonyms.

    Stopwords and generic words are removed; synonyms from the medical
    lexicon are added so everyday phrasing hits the matching report terms.
    """
    base = {t for t in termize(question) if t not in _STOPWORDS and len(t) > 1}
    if not base:
        return set()
    expanded: set[str] = set(base)
    for term in base:
        expanded |= _TERM_EXPANSIONS.get(term, set())
    # Generic terms never carry evidence by themselves, but keep them around
    # only when they are the sole signal (pure synonym of a test name etc.).
    evidence = expanded - _GENERIC_TERMS
    return evidence or expanded


def keyword_score(
    query_terms: set[str], chunk_text: str
) -> tuple[float, set[str], int]:
    """Score a chunk by literal term overlap with the expanded query.

    Returns ``(score, matched_terms, matched_count)``. ``score`` is capped
    at 1.0 with two matched terms already reaching full relevance, so a
    single strong medical term match is still convincingly relevant (and
    ``1 - score`` feeds the review-confidence distance).
    """
    chunk_terms = termize(chunk_text)
    matched = query_terms & chunk_terms
    if not matched:
        return 0.0, set(), 0
    count = len(matched)
    return min(1.0, count / 2.0), matched, count


def hybrid_retrieve(
    db: Session,
    question: str,
    document_ids: list[int],
    settings,
) -> list[dict]:
    """Retrieve relevant chunks scoped to ``document_ids``.

    Keyword overlap over the authoritative SQLite chunk text is the
    relevance gate; the lexical-vector cosine acts as a ranking boost and
    tie-breaker. Each hit carries ``chunk_id``, ``document_id``,
    ``page_number``, ``text``, ``matched_terms``, ``keyword_matches``,
    ``vector_similarity``, ``score``, and a ``distance`` (for the
    confidence gate) of ``1 - score``.
    """
    if not document_ids:
        return []

    query_terms = expand_query_terms(question)
    if not query_terms:
        return []

    vector_similarity: dict[str, float] = {}
    try:
        service = build_embedding_service()
        query_embedding = service.embed_text(question)
        vector_hits = vector_store_module.get_vector_store().search(
            query_embedding=query_embedding,
            document_ids=document_ids,
            top_k=settings.top_k,
        )
        vector_similarity = {
            hit["chunk_id"]: 1.0 - hit["distance"] for hit in vector_hits
        }
    except Exception:
        logger.warning(
            "Vector search failed for docs %s; keyword retrieval still runs.",
            document_ids,
            exc_info=True,
        )

    chunks = list(
        db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id.in_(document_ids))
            .order_by(DocumentChunk.chunk_index)
        ).all()
    )
    if not chunks:
        logger.info("No chunks found for document_ids=%s", document_ids)
        return []

    hits: list[dict] = []
    for chunk in chunks:
        score, matched, count = keyword_score(query_terms, chunk.content)
        if not matched:
            continue
        hits.append(
            {
                "chunk_id": str(chunk.id),
                "document_id": chunk.document_id,
                "page_number": chunk.page_number,
                "text": chunk.content,
                "matched_terms": sorted(matched),
                "keyword_matches": count,
                "vector_similarity": vector_similarity.get(str(chunk.id), 0.0),
                "score": score,
                "distance": 1.0 - score,
            }
        )

    hits.sort(
        key=lambda h: (
            -h["keyword_matches"],
            -h["vector_similarity"],
            int(h["chunk_id"]),
        )
    )
    return hits[: settings.top_k] if settings.top_k else hits