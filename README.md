# Domain-Specific Research Paper Explorer & Summarizer

## Concept

A RAG-based pipeline that turns a collection of domain-specific research paper PDFs (AI/ML in this case) into an intelligent conversational assistant, reducing the time needed for literature review.

## Big-Picture Architecture

The system has 3 layers:

```text
┌─────────────────────────────────────────────────────┐
│                  INGESTION LAYER                    │
│          (Fetch → Parse → Chunk → Embed → Store)    │
└─────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────┐
│               KNOWLEDGE BASE LAYER                  │
│      (Vector DB + Metadata Store + Document Store)  │
└─────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────┐
│               RETRIEVAL + QA LAYER                  │
│             (Query → Retrieve → Rerank → Generate)  │
└─────────────────────────────────────────────────────┘
```

### Layer 1: Ingestion Layer

**Key design decision:** chunking strategy.

```text
Fetch PDF URL
      ↓
Download PDF
      ↓
Extract text (PyMuPDF / pdfplumber)
      ↓
Clean and normalize text
      ↓
Chunk text into segments
      ↓
Generate embeddings per chunk
      ↓
Store chunks + embeddings in Vector DB
Store metadata in Metadata DB
Store raw PDF / extracted text in Document Store
```

### Layer 2: Knowledge Base Layer

Three components work together:

- **Vector DB:** stores chunk embeddings for semantic search.
- **Metadata Store (SQL/NoSQL):** stores paper-level metadata.
- **Document Store:** stores raw PDFs and/or full extracted text, keyed by `paper_id`.

### Layer 3: Retrieval + Q&A

```text
User query
    ↓
Embed the query
    ↓
Semantic search in Vector DB (top-k chunks)
    ↓
Optional: filter by metadata (year, venue, topic)
    ↓
Optional: rerank results (cross-encoder reranker)
    ↓
Assemble context from top chunks
    ↓
LLM generates answer with citations
```

## Tech Stack

| Component | Service | Status |
| --- | --- | --- |
| Backend API | Render (free tier) | ✅ Free forever |
| Daily cron job | Render Cron Job | ✅ Free on all tiers |
| LLM inference | Groq (Llama 3) | ✅ Free, 6K TPM limit |
| Embeddings | HF Inference API | ✅ Free (swapped from Jina) |
| Vector DB | Pinecone Starter | ✅ Free, up to 2 GB limit |
| Metadata store | SQLite on Render | ✅ Free |
| PDF + text storage | HF Datasets (public) | ✅ Free |