"""Streamlit Web Interface for Company Brain — Nexora Technologies Knowledge Platform."""

import os
from typing import Any, Dict, Optional

import httpx
import streamlit as st


st.set_page_config(
    page_title="Nexora Company Brain",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

# Local-demo credentials must match app/permissions.py.
# These tokens are for local development only, never production.
DEV_TOKENS = {
    "employee": "dev-tok-employee-01",
    "manager": "dev-tok-manager-02",
    "hr": "dev-tok-hr-03",
    "finance": "dev-tok-finance-04",
    "executive": "dev-tok-executive-05",
    "admin": "dev-tok-admin-06",
}

st.markdown(
    """
    <style>
    .main-header {font-size: 2.2rem; font-weight: 700; color: #1E293B; margin-bottom: .2rem;}
    .sub-header {font-size: 1.05rem; color: #64748B; margin-bottom: 1.2rem;}
    .synthetic-badge {background:#FEF3C7;color:#92400E;padding:.35rem .75rem;border-radius:9999px;font-size:.8rem;font-weight:600;display:inline-block;border:1px solid #FCD34D;margin-bottom:1rem;}
    .role-badge {background:#EEF2FF;color:#3730A3;padding:.25rem .6rem;border-radius:6px;font-size:.85rem;font-weight:600;border:1px solid #C7D2FE;}
    .grounded-badge {background:#ECFDF5;color:#065F46;padding:.3rem .7rem;border-radius:6px;font-size:.85rem;font-weight:600;border:1px solid #A7F3D0;}
    .insufficient-badge {background:#FEF2F2;color:#991B1B;padding:.3rem .7rem;border-radius:6px;font-size:.85rem;font-weight:600;border:1px solid #FECACA;}
    .source-card {background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;padding:.9rem;margin-bottom:.75rem;}
    .search-hit-title {font-size:1.1rem;font-weight:600;color:#0F172A;}
    .search-hit-meta {font-size:.85rem;color:#64748B;margin-bottom:.4rem;}
    .search-hit-excerpt {font-size:.92rem;color:#334155;line-height:1.5;background:#FFFFFF;padding:.6rem;border-radius:6px;border-left:3px solid #6366F1;}
    </style>
    """,
    unsafe_allow_html=True,
)


def _response_detail(response: httpx.Response, fallback: str) -> str:
    """Return a safe, readable detail from an API error response."""
    try:
        body = response.json()
        detail = body.get("detail", fallback) if isinstance(body, dict) else fallback
        return str(detail)
    except (ValueError, TypeError):
        return fallback


def call_api(
    endpoint: str,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    role: str = "employee",
) -> Optional[Any]:
    """Call FastAPI using a role-specific local development bearer token.

    This function deliberately does not fall back to in-process services.
    If the API is unavailable, the operation fails instead of bypassing
    API authentication and authorization checks.
    """
    url = f"{API_BASE_URL.rstrip('/')}{endpoint}"
    token = DEV_TOKENS.get(role.lower())

    if token is None:
        st.error("Invalid demo role selected.")
        return None

    headers = {"Authorization": f"Bearer {token}"}

    try:
        with httpx.Client(timeout=15.0) as client:
            if method == "GET":
                response = client.get(url, params=params, headers=headers)
            elif method == "POST":
                response = client.post(
                    url,
                    params=params,
                    json=json_data,
                    headers=headers,
                )
            else:
                st.error(f"Unsupported HTTP method: {method}")
                return None

        if response.status_code == 200:
            try:
                return response.json()
            except ValueError:
                st.error("The API returned an invalid JSON response.")
                return None

        if response.status_code == 401:
            st.error(
                "Authentication failed (401). Check the local development "
                "token configuration in app/permissions.py."
            )
        elif response.status_code == 403:
            st.error(
                "Access denied (403). This role is not authorized to perform "
                "the requested operation."
            )
        elif response.status_code == 404:
            st.warning(f"Resource not found (404): {_response_detail(response, 'Not found')}")
        elif response.status_code == 409:
            st.info(f"Operation conflict (409): {_response_detail(response, 'A sync may already be running.')}")
        else:
            st.error(f"API error ({response.status_code}).")
        return None

    except httpx.TimeoutException:
        st.error("The API request timed out. Check that FastAPI is running.")
        return None
    except httpx.RequestError:
        st.error(
            f"Cannot connect to the Company Brain API at {API_BASE_URL}. "
            "Start the FastAPI backend and try again."
        )
        return None


# Sidebar: Role Simulation & System Status
with st.sidebar:
    st.image(
        "https://api.iconify.design/lucide:brain-circuit.svg?color=%234F46E5&width=50&height=50",
        width=50,
    )
    st.title("Company Brain")
    st.markdown("**Nexora Technologies**  \n*Observability & Telemetry Intelligence*")
    st.markdown("---")
    st.subheader("👤 Role-Based Demo Mode")
    st.caption(
        "Simulate enterprise security clearances. Access decisions are enforced "
        "by the FastAPI backend."
    )

    role_options = {
        "employee": "Regular Employee (General policies, engineering, onboarding)",
        "manager": "Engineering / Sales Manager (+ Project Titan reports, sales playbook)",
        "hr": "People Operations (+ Compensation bands, grievances)",
        "finance": "Finance Team (+ Procurement limits, treasury plans)",
        "executive": "Executive Leadership (+ Strategic vision, board minutes, M&A)",
        "admin": "System Administrator (Administrative operations)",
    }
    selected_role = st.selectbox(
        "Active Persona:",
        options=list(role_options.keys()),
        index=0,
        format_func=lambda role: f"{role.upper()} — {role_options[role]}",
    )
    st.markdown(f"**Current Clearance**: `<{selected_role}>`")
    st.caption("Local development demo only; the role selector is not a production login.")

    st.markdown("---")
    st.subheader("⚡ Knowledge Sync")
    if st.button("🔄 Trigger Incremental Sync", use_container_width=True):
        with st.spinner("Scanning knowledge directory and computing SHA-256 hashes..."):
            sync_result = call_api("/sync", method="POST", role=selected_role)
        if sync_result:
            st.success(
                f"Sync complete! Added: {sync_result.get('added', 0)}, "
                f"Modified: {sync_result.get('modified', 0)}, "
                f"Deleted: {sync_result.get('deleted', 0)}, "
                f"Unchanged: {sync_result.get('unchanged', 0)}"
            )

    sync_status = call_api("/sync/status", role=selected_role)
    if sync_status:
        last_sync = sync_status.get("last_sync")
        if last_sync:
            st.caption(
                f"Last sync status: **{last_sync.get('status')}** "
                f"({last_sync.get('total_documents')} documents)"
            )

    st.markdown("---")
    st.subheader("⚙️ System Health")
    health = call_api("/health", role=selected_role)
    if health:
        st.caption(f"**Status**: {health.get('status', 'unknown').upper()}")
        st.caption(f"**Indexed Docs**: {health.get('documents_indexed', 0)}")
        st.caption(f"**Indexed Chunks**: {health.get('chunks_indexed', 0)}")
        provider = health.get("llm_provider", "retrieval_only")
        if health.get("gemini_configured"):
            st.success(f"🤖 LLM Active: {provider}")
        else:
            st.info(f"📄 Grounded Mode: {provider} (Extractive)")


# Main header
st.markdown(
    '<div class="synthetic-badge">⚠️ SYNTHETIC DATASET — NEXORA TECHNOLOGIES DEMO SYSTEM</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="main-header">Company Brain: AI Harness & Knowledge Platform</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="sub-header">Grounded semantic search, verified document retrieval, '
    'and enterprise role-based access control.</div>',
    unsafe_allow_html=True,
)

tab_chat, tab_search, tab_docs = st.tabs(
    ["💬 Knowledge Assistant", "🔍 Full-Text Search", "📚 Document Repository"]
)


# TAB 1: Knowledge Assistant
with tab_chat:
    st.markdown("#### Ask a Question Grounded in Company Policies")
    st.write(
        "Answers are generated from indexed company documentation. If evidence is "
        "insufficient or inaccessible under the active role, the system should say so."
    )
    st.markdown("**Quick Example Questions:**")
    col1, col2, col3, col4 = st.columns(4)
    sample_question = None
    if col1.button("🏠 Home Office Stipend"):
        sample_question = "What is the home office setup stipend and internet allowance?"
    if col2.button("⏱️ SLA Response Times"):
        sample_question = "What are our customer support SLA response times for Sev-1 and Sev-2 incidents?"
    if col3.button("📊 Project Titan Status"):
        sample_question = "What is the current status of Project Titan and what are the main blockers?"
    if col4.button("💼 M&A Target Strategy"):
        sample_question = "What is our confidential M&A acquisition target discussed in the executive minutes?"

    user_query = st.text_input(
        "Enter your question:",
        value=sample_question or "",
        placeholder="e.g. How does parental leave work at Nexora?",
        key="chat_input",
    )

    if st.button("🚀 Ask Company Brain", type="primary"):
        if not user_query.strip():
            st.warning("Please type a question.")
        else:
            with st.spinner("Searching the knowledge base and preparing a grounded response..."):
                answer_data = call_api(
                    "/ask",
                    method="POST",
                    json_data={"question": user_query.strip(), "max_sources": 4},
                    role=selected_role,
                )
            if answer_data:
                answer = answer_data.get("answer", "")
                provider = answer_data.get("provider", "retrieval_only")
                confidence = answer_data.get("confidence", "grounded")
                sources = answer_data.get("sources", [])
                role_applied = answer_data.get("role_applied", selected_role)

                st.markdown("---")
                status_col, role_col, provider_col = st.columns([2, 2, 3])
                with status_col:
                    if confidence == "grounded":
                        st.markdown(
                            '<span class="grounded-badge">✓ Grounded in Verified Sources</span>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            '<span class="insufficient-badge">⚠️ Insufficient Evidence</span>',
                            unsafe_allow_html=True,
                        )
                with role_col:
                    st.markdown(
                        f'<span class="role-badge">Role Applied: {role_applied.upper()}</span>',
                        unsafe_allow_html=True,
                    )
                with provider_col:
                    provider_label = "Gemini API" if provider == "gemini" else "Extractive Retrieval"
                    st.caption(f"Provider: **{provider}** ({provider_label})")

                st.markdown("### Answer")
                st.markdown(answer)

                if sources:
                    st.markdown("### 📑 Verified Sources Cited")
                    for index, source in enumerate(sources, 1):
                        title = source.get("title", "Untitled")
                        document_id = source.get("document_id", "unknown")
                        with st.expander(f"Source {index}: {title} (`{document_id}`)"):
                            st.markdown(
                                f"**Category**: {source.get('category')} | "
                                f"**Classification**: `{source.get('access_classification')}`"
                            )
                            if source.get("heading"):
                                st.markdown(f"**Section**: {source['heading']}")
                            snippet = source.get("excerpt", "").replace("[[", "**").replace("]]", "**")
                            st.markdown(f"> {snippet}")
                else:
                    st.info("No sources were accessible or matched for this question.")


# TAB 2: Full-Text Search
with tab_search:
    st.markdown("#### Keyword & Full-Text Search (SQLite FTS5)")
    st.write("Search the indexed knowledge base with server-side role-based access control.")
    search_col, limit_col = st.columns([4, 1])
    with search_col:
        search_query = st.text_input(
            "Search keywords:",
            placeholder="e.g. YubiKey, parental leave, eBPF collector, Radford, WireGuard",
            key="search_input",
        )
    with limit_col:
        search_limit = st.slider("Max results:", min_value=1, max_value=15, value=5)

    if st.button("🔍 Search Knowledge Base"):
        if not search_query.strip():
            st.warning("Please enter search terms.")
        else:
            with st.spinner("Searching the FTS5 index..."):
                search_data = call_api(
                    "/search",
                    method="POST",
                    json_data={"query": search_query.strip(), "limit": search_limit},
                    role=selected_role,
                )
            if search_data:
                results = search_data.get("results", [])
                total = search_data.get("total_results", len(results))
                st.markdown(
                    f'Found **{total}** matching excerpts for *"{search_query}"* '
                    f'under role **{selected_role.upper()}**:'
                )
                if not results:
                    st.info("No matching documents found within your clearance level.")

                for item in results:
                    st.markdown('<div class="source-card">', unsafe_allow_html=True)
                    st.markdown(
                        f'<div class="search-hit-title">{item.get("title", "Untitled")} '
                        f'<span class="role-badge">{item.get("access_classification", "")}</span></div>',
                        unsafe_allow_html=True,
                    )
                    heading = f" • Section: {item.get('heading')}" if item.get("heading") else ""
                    st.markdown(
                        f'<div class="search-hit-meta">Doc ID: <code>{item.get("document_id", "")}</code> '
                        f'• Category: {item.get("category", "")} • Score: {item.get("score", "")}{heading}</div>',
                        unsafe_allow_html=True,
                    )
                    excerpt = item.get("excerpt", "").replace(
                        "[[", "<mark style='background:#FEF08A;'>"
                    ).replace("]]", "</mark>")
                    st.markdown(
                        f'<div class="search-hit-excerpt">{excerpt}</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown("</div>", unsafe_allow_html=True)


# TAB 3: Document Repository
with tab_docs:
    st.markdown("#### Document Repository & Metadata Browser")
    st.write(
        f"Displaying documents accessible to **{selected_role.upper()}** clearance."
    )
    documents = call_api("/documents", role=selected_role)

    if documents:
        categories = sorted({doc.get("category", "Uncategorized") for doc in documents})
        selected_category = st.selectbox(
            "Filter by Category:",
            options=["All Categories"] + categories,
        )
        filtered_documents = [
            doc for doc in documents
            if selected_category == "All Categories"
            or doc.get("category") == selected_category
        ]
        st.caption(f"Showing {len(filtered_documents)} permitted documents:")

        header_cols = st.columns([2, 4, 2, 2, 2])
        for col, label in zip(
            header_cols, ["ID", "Title", "Category", "Classification", "Action"]
        ):
            col.markdown(f"**{label}**")
        st.markdown("---")

        selected_document_id = None
        for doc in filtered_documents:
            col_id, col_title, col_category, col_class, col_action = st.columns(
                [2, 4, 2, 2, 2]
            )
            col_id.code(doc.get("id", ""))
            col_title.write(doc.get("title", "Untitled"))
            col_category.write(doc.get("category", ""))
            col_class.markdown(
                f'<span class="role-badge">{doc.get("access_classification", "")}</span>',
                unsafe_allow_html=True,
            )
            if col_action.button("View", key=f"view_{doc.get('id')}"):
                selected_document_id = doc.get("id")

        if selected_document_id:
            st.markdown("---")
            with st.spinner(f"Loading document {selected_document_id}..."):
                detail = call_api(
                    f"/documents/{selected_document_id}",
                    role=selected_role,
                )
            if detail:
                st.markdown(f"## {detail.get('title', 'Untitled')}")
                meta_cols = st.columns(4)
                meta_cols[0].metric("Doc ID", detail.get("id", ""))
                meta_cols[1].metric("Version", detail.get("version", ""))
                meta_cols[2].metric(
                    "Classification",
                    str(detail.get("access_classification", "")).upper(),
                )
                meta_cols[3].metric("Author", detail.get("author", ""))
                st.markdown("### Content")
                st.markdown(detail.get("raw_content", ""))
    else:
        st.info("No documents are available for this clearance, or the API is unavailable.")
