# Domain-Specific Research Paper Explorer & Summarizer

## Concept
A RAG-based pipeline that turns a collection of domain-specific **(for this case AI/ML)** PDFs of research papers into an intelligent conversational research assistant that helps reduce the time needed for a literature review.

## The Big Picture Architecture
We'll go for 3 layers:

┌─────────────────────────────────────────────────────┐
│                  INGESTION LAYER                    │
│   (Fetch → Parse → Chunk → Embed → Store)           │
└─────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────┐
│               KNOWLEDGE BASE LAYER                  │
│   (Vector DB + Metadata Store + Document Store)     │
└─────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────┐
│                 RETRIEVAL + QA LAYER                │
│   (Query → Retrieve → Rerank → Generate)            │
└─────────────────────────────────────────────────────┘

### Layer 1: Ingestion Layer
**Main piece -> deciding chunking strategy**
Fetch PDF URL
      ↓
Download PDF
      ↓
Extract text (pymupdf / pdfplumber)
      ↓
Clean & normalize text
      ↓
Chunk text into segments
      ↓
Generate embeddings per chunk
      ↓
Store chunks + embeddings in Vector DB
Store metadata in Metadata DB
Store raw PDF / extracted text in Document Store

### Layer 2: Knowledge Base Layer
Here we have 3 components working together:
- Vector DB: to store the embeddings of the chunks for semantic search
- Metadata Store (SQL/NoSQL): holds paper-level metadata
- Document Store: holds the raw PDF and/or the extracted full text, keyed by a paperID

### Layer 3: Retrieval + QnA
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

## Tech stack
Component             | Service                  | Status
────────────────────────────────────────────────────────────────
Backend API           | Render (free tier)       | ✅ Free forever
Daily cron job        | Render Cron Job          | ✅ Free on all tiers
LLM inference         | Groq (Llama 3)           | ✅ Free, 6K TPM limit
Embeddings            | HF Inference API         | ✅ Free (swap from Jina)
Vector DB             | Pinecone Starter         | ✅ Free, upto 2GB limit
Metadata store        | SQLite on Render         | ✅ Free
PDF + text storage    | HF Datasets (public)     | ✅ Free