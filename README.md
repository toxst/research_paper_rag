# Research Paper / Literature Assistant (RAG-Powered)

## Project Overview

A personal, RAG-powered assistant for exploring a collection of academic research papers. Users upload regular, text-based research-paper PDFs and ask questions about their content through a chat interface. The assistant retrieves relevant passages and generates grounded answers with direct quotations and citations identifying the original **filename, section (when available), and PDF page**.

The project prioritises a small, testable **folder-upload MVP**. PDFs, extracted text, metadata, and indexes are stored locally, while embeddings and answer generation use hosted APIs so no large models need to run on the user's laptop. The system is local-first, **not fully offline**.

## In Scope (MVP)

- **PDF uploads:** Upload multiple regular research-paper PDFs through the app; optional ZIP upload to represent a folder. Support digitally generated PDFs, including typical one- and two-column papers. Flag files that cannot be extracted reliably.
- **Document processing:** Extract full text and page boundaries; detect title, authors, year, abstract, and section headings on a best-effort basis.
- **Chunking and indexing:** Create overlapping, preferably section-aware chunks with filename, paper ID, section, and page metadata. Generate hosted embeddings and index them in a persistent local vector database.
- **Persistent library:** Retain uploaded PDFs, extracted text, metadata, and embeddings across app restarts. Detect duplicate files using a content hash to avoid unnecessary embedding calls.
- **Conversational research:** Ask questions across uploaded papers; summarise individual papers or sections; find papers discussing a topic; compare methods, results, and limitations; and offer basic evidence-grounded methodology critiques.
- **Verifiable citations:** Show source filename and page, plus section where detectable. Check generated direct quotations against stored extracted text and clearly state when evidence is missing or insufficient.
- **Retrieval:** Start with dense semantic search; extend to BM25 keyword search and reciprocal rank fusion (RRF) when needed for exact scientific terminology.
- **Basic evaluation:** Use a small set of hand-written questions to check retrieval relevance, answer faithfulness, and citation correctness.

## Possible Enhancements

- arXiv search or ID-based importing, DOI/URL PDF fetching, and automatic paper discovery.
- Zotero integration and Semantic Scholar / OpenAlex metadata enrichment.
- OCR support for scanned PDFs and stronger handling of complex layouts, tables, equations, and figures.
- Hosted reranking, parent/section-level retrieval, and more advanced multi-paper contradiction or claim-evidence analysis.
- Interactive PDF highlighting, editable metadata, and improved source navigation.
- Shared or multi-user libraries, authentication, hosted deployment, and scheduled ingestion.

## Architecture

```text
                       STREAMLIT UI
                 Upload PDFs / ZIP + Chat
                             |
                             v
+----------------------------------------------------------------+
| 1. INGESTION LAYER                                             |
| Validate PDFs -> PyMuPDF extraction -> Metadata                |
| -> Section-aware chunks -> Voyage AI embeddings                |
|                                                                |
| Original PDFs -----------------------> Private Cloudflare R2   |
| Temporary local PDF files (if used) are deleted after ingestion|
+----------------------------------------------------------------+
                              |
                              v
+----------------------------------------------------------------+
| 2. KNOWLEDGE BASE                                              |
| Cloudflare R2: original PDFs (private object storage)          |
| LanceDB (local): extracted chunks, vectors, source metadata    |
| SQLite (local): paper registry, R2 object keys, ingestion state|
+----------------------------------------------------------------+
                              ^
                              |
                              v
+----------------------------------------------------------------+
| 3. RETRIEVAL + Q&A LAYER                                       |
| Question -> Voyage AI query embedding -> LanceDB search        |
| -> (optional BM25 + RRF) -> Evidence selection                 |
| -> Augmented prompt -> OpenRouter / Nemotron 3.5 Super VL      |
| -> Quote + citation checks -> Chat answer                      |
|                                                                |
| Open original source? -> Authorised R2 download / signed URL   |
+----------------------------------------------------------------+
```

**Data flow:** Text extracted from uploaded papers is sent to **Voyage AI** for embedding. Only selected retrieved passages and the user's query are sent to **OpenRouter** for answer generation. The original PDFs, vector index, and metadata remain on the local machine. API usage is subject to provider limits and data-handling policies.

## Updated Technology Stack

| Layer | Technology | Purpose |
| --- | --- | --- |
| Language | **Python 3.11+** | Core application and RAG pipeline |
| User interface | **Streamlit** | Multi-PDF upload and chat |
| PDF extraction | **PyMuPDF** | Fast extraction with page-level provenance |
| Advanced PDF parsing (optional) | **Docling** | Fallback for difficult document layouts |
| Metadata and chunking | **Custom Python** | Best-effort metadata, section-aware chunks, citation tracking |
| Embeddings (hosted) | **Voyage AI `voyage-4`** | Embed document chunks and queries without running a local model |
| Vector store | **LanceDB OSS (local)** | Persistent vector index and chunk metadata |
| Keyword retrieval | **BM25 / LanceDB full-text search** | Exact-match retrieval for technical terms (after baseline) |
| Retrieval fusion | **Reciprocal Rank Fusion (RRF)** | Combine dense and keyword search rankings |
| Answer generation (hosted) | **OpenRouter `nvidia/nemotron-3.5-super-vl:free`** | Produce answers from retrieved evidence |
| Orchestration | **Pure Python** | Keep retrieval and generation steps explicit and replaceable |
| Paper and app metadata | **SQLite** | Store paper records and ingestion/chat state |
| Document storage | **Local filesystem** | Preserve original PDFs and extracted text |
| Evaluation | **pytest + curated QA set** | Test retrieval, groundedness, and citations |

**Cost and hardware:** The core Python libraries and local database options are free, subject to their licences. Voyage AI provides an initial free token allowance rather than unlimited embeddings, and OpenRouter's free model endpoint has usage limits and may change. No powerful local GPU is required. PyMuPDF licensing should be reviewed before redistribution.
