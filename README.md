# Company Brain — AI Harness & Knowledge Platform (Nexora Technologies)

> **NOTICE: SYNTHETIC DATASET**
> *This platform and all accompanying documents, policies, operational metrics, and names belong to a fictional enterprise: **Nexora Technologies**. All information is purely synthetic and designed for demonstration, benchmarking, and architectural evaluation.*

---

## 1. Architectural Overview

Company Brain is a modular, enterprise-grade AI knowledge platform that empowers employees and autonomous AI clients (via Model Context Protocol - MCP) to search, inspect, and query internal company policies, engineering documentation, and operational procedures securely.

### Core System Architecture

```
                  ┌────────────────────────────────────────┐
                  │       Streamlit Web UI (:8501)         │
                  │   (Chat, Search, Doc Browser, RBAC)    │
                  └──────────────────┬─────────────────────┘
                                     │ HTTP (X-User-Role)
                                     ▼
┌──────────────────────┐   ┌───────────────────────────────┐
│ MCP Client (Agents)  │──►│     FastAPI Backend (:8000)   │
│ (Claude / Cursor)    │   │  (/health, /search, /ask, etc)│
└──────────┬───────────┘   └───────────────┬───────────────┘
           │ stdio (JSON-RPC)              │
           ▼                               │
┌──────────────────────┐                   │
│   MCP Server Tool    │───────────────────┤
│ (search / get_doc)   │                   │
└──────────────────────┘                   ▼
                          ┌────────────────────────────────┐
                          │   Role-Based Authorization     │
                          │ (employee, manager, hr, etc)   │
                          └────────────────┬───────────────┘
                                           │
             ┌─────────────────────────────┴─────────────────────────────┐
             ▼                                                           ▼
┌──────────────────────────────┐                           ┌───────────────────────────────┐
│  Modular Retrieval Engine    │                           │    Grounded LLM Provider      │
│  (SQLite FTS5 + BM25)        │                           │  (Gemini API / Fallback Extr) │
└──────────────┬───────────────┘                           └───────────────────────────────┘
               │
               ▼
┌──────────────────────────────┐
│  SQLite Database + Storage   │
│  - documents (Metadata/Hash) │
│  - document_chunks           │
│  - documents_fts (FTS5)      │
│  - sync_history (Audit)      │
└──────────────┬───────────────┘
               ▲
               │ Incremental Sync (SHA-256 Fingerprinting)
┌──────────────┴───────────────┐
│  data/synthetic_company/     │
│  (16 Markdown Documents)     │
└──────────────────────────────┘
```

---

## 2. Key Capabilities & Technical Features

1. **Incremental Document Ingestion & Change Detection**:
   - Parses Markdown documents with YAML frontmatter.
   - Computes SHA-256 hashes of all source documents.
   - Detects new, modified, unchanged, and deleted documents.
   - Completely avoids duplicate indexing on subsequent sync runs.
   - Chunks documents semantically by Markdown headings (`#`, `##`, `###`) with contextual overlap.
2. **Modular Full-Text Retrieval (SQLite FTS5)**:
   - Full-text search with BM25 ranking and query sanitization (escapes FTS5 syntax, filters noise stopwords).
   - Generates contextual snippets highlighting matched search terms.
   - Decoupled `BaseRetrievalEngine` interface ready for future vector/hybrid embedding search backends.
3. **Role-Based Access Control (RBAC)**:
   - Server-side authorization enforced before queries touch the database.
   - Clear classification hierarchy: `employee`, `manager`, `hr`, `finance`, `executive`, `admin`.
   - Prevents unauthorized document disclosure (returns `403 Forbidden` for restricted documents and strictly excludes them from search results).
4. **Multi-Provider Grounded Answering**:
   - Provider interface with optional Google Gemini integration (`GEMINI_API_KEY`).
   - If no API key is provided, the system gracefully falls back to deterministic **Grounded Retrieval-Only Mode** without external API costs or failures.
   - Enforces strict uncertainty admission: explicitly states when internal evidence is insufficient.
5. **Model Context Protocol (MCP) Integration**:
   - Built on the official Python MCP SDK (`mcp` 2.x).
   - Exposes `search_knowledge` and `get_document` tools over standard I/O (`stdio`).
   - Validates all input schemas and enforces role authorization within the tool handler.
6. **Web Interface (Streamlit)**:
   - Interactive Q&A chat with quick-prompt chips and expandable source citations.
   - Live full-text search with relevance scores and snippet highlighting.
   - Document repository browser showing all permitted files and rendered Markdown.
   - Persona role switcher allowing live testing of security clearances.
   - Incremental sync trigger button and system health monitor.

---

## 3. Synthetic Dataset: Nexora Technologies

The dataset contains 17 realistic Markdown documents stored in `data/synthetic_company/`:

| Document ID | Title | Category | Clearance |
| :--- | :--- | :--- | :--- |
| `NEX-OVR-001` | Company Overview & Mission | Company Overview | `employee` |
| `NEX-HR-001` | New Hire Onboarding & 30-60-90 Day Roadmap | Employee Onboarding | `employee` |
| `NEX-HR-002` | Global Remote Work & Home Office Stipend Policy | Remote Work Policy | `employee` |
| `NEX-HR-003` | Paid Time Off (PTO), Parental & Medical Leave | Leave Policy | `employee` |
| `NEX-PRD-001` | Nexora Pulse Telemetry Engine - Architecture | Product Documentation | `employee` |
| `NEX-SUP-001` | Customer Support Procedures & SLA Escalations | Customer Support | `employee` |
| `NEX-ENG-001` | Engineering Standards & Code Review Rules | Engineering Standards | `employee` |
| `NEX-ENG-002` | Project Titan Status Report (Q1 Mesh Telemetry) | Project Status Reports | `manager` |
| `NEX-EXE-001` | Executive Leadership Minutes - M&A Scenarios | Meeting Notes | `executive` |
| `NEX-SAL-001` | Enterprise Sales Methodology & Discount Matrix | Sales Processes | `manager` |
| `NEX-FIN-001` | Procurement & Expense Auditing Policy | Finance Procedures | `finance` |
| `NEX-HR-004` | Compensation Bands & Grievance Protocols | HR Policies | `hr` |
| `NEX-LDR-001` | 2026-2028 Strategic Vision & IPO Roadmap | Leadership Strategy | `executive` |
| `NEX-SEC-001` | Information Security & Incident Response Policy | Security Policies | `employee` |
| `NEX-FAQ-001` | Company-Wide Frequently Asked Questions (FAQ) | FAQs | `employee` |
| `NEX-ADM-001` | Global IT Admin & Root Key Rotation Runbook | IT Administration | `admin` |
| `NEX-SEC-002` | Enterprise Data Classification & Governance Policy | Security Policies | `manager` |


---

## 4. Role-Based Access Control (RBAC) Matrix

Server-side clearance mappings:

| Persona Role | Permitted Classifications | Cannot Access |
| :--- | :--- | :--- |
| `employee` | `employee` | Manager, HR, Finance, Executive, Admin |
| `manager` | `employee`, `manager` | HR, Finance, Executive, Admin |
| `hr` | `employee`, `hr` | Manager, Finance, Executive, Admin |
| `finance` | `employee`, `finance` | Manager, HR, Executive, Admin |
| `executive` | `employee`, `manager`, `hr`, `finance`, `executive` | Admin-only runbooks |
| `admin` | `employee`, `manager`, `hr`, `finance`, `executive`, `admin` | *(None - Full Clearance)* |

> **Development Identity Notice**: In this development harness, identity is passed via the `X-User-Role` HTTP header or tool parameter. In a production environment, this header must be replaced with cryptographically signed JWT/OIDC bearer tokens issued by an enterprise Identity Provider (e.g., Okta, Entra ID) and verified server-side against tenant claims.

---

## 5. Quickstart Guide (Windows PowerShell)

### Prerequisites
- Python 3.12+ installed
- PowerShell 5.1 or PowerShell 7+

### Step 1: Clone / Navigate to Project & Create Virtual Environment
```powershell
cd d:\company-brain
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Step 2: Install Dependencies
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3: Run the Automated Test Suite
```powershell
pytest -v
```
*(All 34 unit, integration, and security regression tests covering ingestion, FTS5 retrieval, RBAC authorization, FastAPI endpoints, MCP tools, and intent-aware precision will execute).*


### Step 4: Configure Environment (Optional for Gemini)
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
To enable Google Gemini answering, set `GEMINI_API_KEY` in `.env`:
```ini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
LLM_PROVIDER=auto
```
*If left blank, Company Brain operates in grounded retrieval-only mode.*

### Step 5: Start the FastAPI Backend Server
```powershell
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000 --reload
```
- API Documentation (Swagger UI): **http://127.0.0.1:8000/docs**
- Health Endpoint: **http://127.0.0.1:8000/health**

### Step 6: Start the Streamlit Web Application (in a new terminal)
```powershell
.\.venv\Scripts\streamlit.exe run ui/streamlit_app.py --server.port 8501
```
- Streamlit UI: **http://localhost:8501**

---

## 6. Model Context Protocol (MCP) Integration

The platform provides a compliant MCP server over `stdio` transport using the official Python MCP SDK.

### Testing the MCP Server Directly
```powershell
python -m app.mcp_server
```

### Connecting to Claude Desktop / MCP Clients
To connect Claude Desktop to Company Brain, add the server to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "nexora-company-brain": {
      "command": "d:\\company-brain\\.venv\\Scripts\\python.exe",
      "args": [
        "-m",
        "app.mcp_server"
      ],
      "env": {
        "PYTHONPATH": "d:\\company-brain",
        "DATABASE_PATH": "d:\\company-brain\\data\\company_brain.db",
        "KNOWLEDGE_DIR": "d:\\company-brain\\data\\synthetic_company"
      }
    }
  }
}
```

### Available MCP Tools

#### `search_knowledge`
- **Description**: Search Nexora Technologies company policies and engineering docs via BM25 full-text search.
- **Parameters**:
  - `query` (string, required): Search query or question.
  - `role` (string, optional, default `"employee"`): Caller's organizational role.
  - `limit` (integer, optional, default `5`): Max excerpts to return.

#### `get_document`
- **Description**: Retrieve full Markdown content and metadata for a document by ID.
- **Parameters**:
  - `document_id` (string, required): e.g. `NEX-OVR-001`, `NEX-ENG-001`.
  - `role` (string, optional, default `"employee"`): Caller's role for clearance verification.

---

## 7. REST API Endpoints

| Method | Endpoint | Description | Role Clearance |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | System health, version, provider, and document counts | Public |
| `GET` | `/documents` | List all documents permitted for the caller's role | Filtered by `X-User-Role` |
| `GET` | `/documents/{id}` | Fetch full document content | Enforces clearance (403 if unauthorized) |
| `POST` | `/search` | Full-text FTS5 search with BM25 scores and snippets | Filtered by `X-User-Role` |
| `POST` | `/ask` | Grounded question answering with citations | Filtered by `X-User-Role` |
| `POST` | `/sync` | Trigger incremental synchronization | Admin / Internal |
| `GET` | `/sync/status` | Current sync state and audit history | Public |

### Example API Requests

#### Search (Employee Clearance)
```powershell
curl -X POST http://127.0.0.1:8000/search `
  -H "Content-Type: application/json" `
  -H "X-User-Role: employee" `
  -d '{"query": "home office stipend", "limit": 3}'
```

#### Grounded Q&A
```powershell
curl -X POST http://127.0.0.1:8000/ask `
  -H "Content-Type: application/json" `
  -H "X-User-Role: employee" `
  -d '{"question": "What is the initial home office equipment stipend?", "max_sources": 3}'
```

#### Attempting Unauthorized Access (Employee -> Executive Doc)
```powershell
curl -i -X GET http://127.0.0.1:8000/documents/NEX-EXE-001 `
  -H "X-User-Role: employee"
# Returns HTTP 403 Forbidden with detail message
```

---

## 8. Security Considerations & Production Roadmap

- **Identity Verification**: Production systems must terminate TLS and validate signed OAuth2 / JWT access tokens issued by Okta, Azure AD, or Ping Identity.
- **Audit Logging**: Every document access and search query should be logged to a SIEM (e.g. Splunk, Datadog) with user ID, IP address, and clearance level.
- **Vector Search Extension**: The modular `BaseRetrievalEngine` interface can be extended with `pgvector`, Qdrant, or Chroma to support dense embeddings alongside SQLite FTS5 for hybrid search.
- **Data Encryption**: All databases should be encrypted at rest (e.g. SQLCipher or EBS encryption) and in transit via TLS 1.3.
