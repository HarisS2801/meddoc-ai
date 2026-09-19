import type {
  ChatResponse,
  Conversation,
  ConversationDetail,
  DocumentItem,
  ExtractionResponse,
  ReviewItem,
  ReviewStats,
  SummaryResponse,
} from "../types";

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let message = messageForStatus(response.status);
    try {
      const body = (await response.json()) as { error?: { message?: string } };
      if (body.error?.message) {
        message = body.error.message;
      }
    } catch {
      // response body was not JSON; keep the status-based message
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

function messageForStatus(status: number): string {
  if (status === 401 || status === 403) {
    return "You are not authorized to perform this action.";
  }
  if (status === 404) {
    return "The requested item was not found.";
  }
  if (status === 409) {
    return "This action conflicts with the current state of the item.";
  }
  if (status === 413) {
    return "The file is too large to upload.";
  }
  if (status === 422) {
    return "The file type is not supported. Upload a PDF or .txt file.";
  }
  if (status === 503) {
    return "Groq AI is currently unavailable. Please try again later.";
  }
  if (status === 429) {
    return "The AI service is rate limited right now. Please wait a moment and try again.";
  }
  if (status >= 500) {
    return "Something went wrong while processing your request. Please try again.";
  }
  return `Request failed with status ${status}`;
}

export const api = {
  listDocuments(): Promise<DocumentItem[]> {
    return request<DocumentItem[]>("/documents");
  },

  getDocument(documentId: number): Promise<DocumentItem> {
    return request<DocumentItem>(`/documents/${documentId}`);
  },

  uploadDocument(file: File): Promise<DocumentItem> {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentItem>("/documents/upload", {
      method: "POST",
      body: form,
    });
  },

  deleteDocument(documentId: number): Promise<void> {
    return request<void>(`/documents/${documentId}`, { method: "DELETE" });
  },

  summarize(documentId: number, force: boolean = false): Promise<SummaryResponse> {
    const query = force ? "?force=true" : "";
    return request<SummaryResponse>(`/documents/${documentId}/summarize${query}`, {
      method: "POST",
    });
  },

  extractFollowUp(documentId: number): Promise<ExtractionResponse> {
    return request<ExtractionResponse>(`/documents/${documentId}/extract`, {
      method: "POST",
      body: JSON.stringify({ document_id: documentId, schema: "follow_up" }),
    });
  },

  ask(
    question: string,
    conversationId: number | null,
    documentIds: number[] | null,
  ): Promise<ChatResponse> {
    return request<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify({
        question,
        conversation_id: conversationId,
        document_ids: documentIds,
      }),
    });
  },

  listConversations(): Promise<Conversation[]> {
    return request<Conversation[]>("/chat/conversations");
  },

  getConversation(conversationId: number): Promise<ConversationDetail> {
    return request<ConversationDetail>(`/chat/conversations/${conversationId}`);
  },

  clearConversation(conversationId: number): Promise<void> {
    return request<void>(`/chat/conversations/${conversationId}`, {
      method: "DELETE",
    });
  },

  listReviews(status?: string): Promise<ReviewItem[]> {
    const query = status ? `?status=${status}` : "";
    return request<ReviewItem[]>(`/review${query}`);
  },

  reviewStats(): Promise<ReviewStats> {
    return request<ReviewStats>("/review/stats");
  },

  decideReview(
    reviewId: number,
    decision: "approve" | "reject",
    comment: string | null,
  ): Promise<ReviewItem> {
    return request<ReviewItem>(`/review/${reviewId}/${decision}`, {
      method: "POST",
      body: JSON.stringify({ comment }),
    });
  },
};