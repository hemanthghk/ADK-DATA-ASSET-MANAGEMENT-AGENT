
┌─────────────────────────────────────────────────────────────────┐
│            HITL DATA OPTIMIZATION SYSTEM                        │
│                 (Google ADK Architecture)                       │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────────┐
│   Google Drive API v3    │  (20 Sample Documents)
│   OAuth 2.0 Integration  │  - Invoices (with duplicates)
└────────────┬─────────────┘  - Customer records (with PII)
             │                - Sales reports
             │ OAuth Flow     - Internal memos
             ▼                - Corrupted files
┌──────────────────────────────────────────────────────────────┐
│          Data Quality Agent (Google ADK)                     │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ • Duplicate Detection (85% threshold via pgvector)     │ │
│  │ • PII Pattern Matching (email, SSN, phone, CC)         │ │
│  │ • Quality Validation (corruption, size, integrity)     │ │
│  │ • Document Chunking (1KB segments, 200-char overlap)   │ │
│  └────────────────────────────────────────────────────────┘ │
└────────────┬─────────────────────────────────────────────────┘
             │
             │ Detection Results
             ▼
┌──────────────────────────────────────────────────────────────┐
│          Gemini 2.0 Flash (LLM Reasoning)                    │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ • Chunk Summarization (key entities, dates, numbers)   │ │
│  │ • Confidence Scoring (HIGH >90%, MEDIUM 70-90%)        │ │
│  │ • Context Understanding                                │ │
│  └────────────────────────────────────────────────────────┘ │
└────────────┬─────────────────────────────────────────────────┘
             │
             │ Structured Findings + Confidence Scores
             ▼
┌──────────────────────────────────────────────────────────────┐
│              ⚠️  HUMAN APPROVAL GATE  ⚠️                     │
│              (Terminal CLI Interface)                        │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Issue Review:                                         │ │
│  │  • View detected problems with evidence                │ │
│  │  • See confidence scores & business impact             │ │
│  │  • Approve or Reject each action                       │ │
│  │  • Provide feedback for agent improvement              │ │
│  └────────────────────────────────────────────────────────┘ │
└────────────┬─────────────────────────────────────────────────┘
             │
             │ ✅ Approved Actions Only
             │ ❌ Rejected Actions Logged
             ▼
┌──────────────────────────────────────────────────────────────┐
│      PostgreSQL + pgvector (Vector Database)                 │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Documents Table:                                       │ │
│  │  • file_id, filename, content                          │ │
│  │  • embedding (768-dim via Ollama nomic-embed-text)     │ │
│  │  • metadata (classification tags, quality scores)      │ │
│  │                                                         │ │
│  │ Document_Chunks Table:                                 │ │
│  │  • chunk_id, chunk_text, summary                       │ │
│  │  • embedding (summarized chunks for precision search)  │ │
│  │  • metadata (start_pos, end_pos, filename)             │ │
│  └────────────────────────────────────────────────────────┘ │
└────────────┬─────────────────────────────────────────────────┘
             │
             │ IVFFlat Indexes (Cosine Similarity)
             ▼
┌──────────────────────────────────────────────────────────────┐
│            OPTIMIZATION CATALOG & SEARCH                     │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ ✓ Semantic Search (document-level & chunk-level)       │ │
│  │ ✓ Duplicate Tracking (storage savings calculated)      │ │
│  │ ✓ PII Catalog (compliance-ready audit trails)          │ │
│  │ ✓ Quality Metrics (corruption detection, file health)  │ │
│  │ ✓ Human Decisions Log (timestamp, approver, action)    │ │
│  │ ✓ ROM Cache (instant chunk retrieval, no re-compute)   │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     TECHNOLOGY STACK                        │
├─────────────────────────────────────────────────────────────┤
│ Agent Framework:  Google ADK 1.0+ (Multi-agent orchestration)│
│ LLM:              Gemini 2.0 Flash (Free tier, 15 RPM)      │
│ Vector DB:        PostgreSQL 14+ with pgvector extension    │
│ Embeddings:       Ollama nomic-embed-text (768-dim, local)  │
│ Data Source:      Google Drive API v3 (OAuth 2.0)           │
│ Cache:            In-memory ROM cache (Python dict)         │
│ Session:          InMemorySessionService (Google ADK)       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                   KEY WORKFLOWS                             │
├─────────────────────────────────────────────────────────────┤
│ 1. SETUP: Init DB → Auth Drive → List Files                │
│ 2. SCAN: Download → Chunk → Embed → Detect Issues          │
│ 3. HITL: Present Findings → Human Review → Approve/Reject  │
│ 4. ACTION: Execute Approved → Log Decisions → Update DB    │
│ 5. SEARCH: Query → Vector Search → Return Ranked Results   │
└─────────────────────────────────────────────────────────────┘
