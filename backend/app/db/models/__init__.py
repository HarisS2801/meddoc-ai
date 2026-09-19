"""Public ORM model surface.

Importing this package ensures every model is registered on
``Base.metadata`` before any ``metadata.create_all()`` call.
"""

from app.db.models.document import Document, DocumentChunk
from app.db.models.conversation import Conversation, Message
from app.db.models.review import ReviewItem
from app.db.models.evaluation import EvaluationResult
from app.db.models.summary import Summary

__all__ = [
    "Conversation",
    "Document",
    "DocumentChunk",
    "EvaluationResult",
    "Message",
    "ReviewItem",
    "Summary",
]