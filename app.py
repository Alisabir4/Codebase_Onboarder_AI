
"""Codebase Onboarder AI — repository analysis and grounded AI assistance."""

import os

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from core.github_loader import load_github_repository, load_zip_repository
from core.analyzer import analyze_repository
from core.graph_builder import build_interactive_graph
from core.documentation import generate_documentation
from core.rag import retrieve, groq_answer, evidence_is_relevant


# =========================================================
# CONFIGURATION
# =========================================================

load_dotenv()

st.set_page_config(
    page_title="Codebase Onboarder AI",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =========================================================
# THEME
# =========================================================

st.markdown(
    """
    <style>
    :root {
        color-scheme: dark;
        --canvas: #080d19;
        --surface: #101827;
        --surface-raised: #141f32;
        --surface-soft: #0d1524;
        --border: #26354d;
        --border-strong: #354968;
        --text: #f1f5fc;
        --muted: #aab8cc;
        --subtle: #8393aa;
        --blue: #7aa9ff;
        --blue-strong: #4d82e8;
        --purple: #b19aff;
        --radius: 14px;
    }

    .stApp {
        background: var(--canvas);
        color: var(--text);
    }

    [data-testid="stAppViewContainer"] > .main {
        background: var(--canvas);
    }

    [data-testid="stHeader"] {
        background: rgba(8, 13, 25, .92);
    }

    [data-testid="stMainBlockContainer"] {
        max-width: 1500px;
        padding-top: 2rem;
        padding-bottom: 2.5rem;
    }

    [data-testid="stSidebar"] {
        background: #0c1422;
        border-right: 1px solid #1d2a3e;
    }

    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: .85rem;
    }

    [data-testid="stSidebar"] h2 {
        color: var(--text);
        letter-spacing: -.02em;
    }

    .hero {
        padding: clamp(1.25rem, 3vw, 2rem);
        border: 1px solid var(--border);
        border-radius: 20px;
        background: linear-gradient(115deg, #111d31 0%, #121a2b 58%, #19172b 100%);
        margin-bottom: 1.5rem;
        box-shadow: 0 16px 40px rgba(0, 0, 0, .18);
    }

    .hero h1 {
        margin: 0;
        font-size: clamp(1.65rem, 4vw, 2.35rem);
        line-height: 1.2;
        letter-spacing: -.035em;
        color: var(--text);
    }

    .hero p {
        color: #c0cce0;
        max-width: 760px;
        line-height: 1.65;
        margin: .65rem 0 0;
    }

    .metric-card,
    [data-testid="stMetric"],
    [data-testid="stAlert"],
    [data-testid="stExpander"] {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius);
    }

    .metric-card {
        height: 100%;
        padding: 1.2rem;
    }

    .metric-card h3 {
        font-size: 1.05rem;
        margin: 0 0 .65rem;
        color: var(--text);
    }

    .metric-card p { line-height: 1.6; }
    .muted, [data-testid="stCaptionContainer"] { color: var(--muted) !important; }

    h1, h2, h3, h4 {
        color: var(--text);
        letter-spacing: -.02em;
    }

    h2 { margin-top: .4rem; }
    h3 { margin-top: .4rem; }
    p, li, label, [data-testid="stMarkdownContainer"] { color: inherit; }
    strong { color: #f7f9ff; }

    [data-testid="stMetric"] {
        padding: 1rem 1.1rem;
        min-height: 100px;
    }
    [data-testid="stMetricLabel"] { color: var(--muted); }
    [data-testid="stMetricValue"] { color: var(--text); }

    [data-testid="stTabs"] [role="tablist"] {
        gap: .35rem;
        border-bottom: 1px solid var(--border);
    }
    [data-testid="stTabs"] button[role="tab"] {
        color: var(--muted);
        border-radius: 9px 9px 0 0;
        padding: .65rem .9rem;
    }
    [data-testid="stTabs"] button[role="tab"]:hover { color: var(--text); }
    [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
        color: #dce8ff;
        border-bottom-color: var(--blue);
    }

    .stButton > button, [data-testid="stDownloadButton"] button {
        min-height: 2.65rem;
        border-radius: 10px;
        border: 1px solid var(--border-strong);
        background: #17243a;
        color: var(--text);
        font-weight: 600;
        transition: background .15s ease, border-color .15s ease, transform .15s ease;
    }
    .stButton > button:hover, [data-testid="stDownloadButton"] button:hover {
        background: #203251;
        border-color: #5878a7;
        color: #fff;
    }
    .stButton > button:active { transform: translateY(1px); }
    .stButton > button[kind="primary"] {
        background: var(--blue-strong);
        border-color: var(--blue-strong);
        color: #fff;
    }
    .stButton > button[kind="primary"]:hover {
        background: #6395f2;
        border-color: #6395f2;
    }

    [data-baseweb="input"] > div,
    [data-baseweb="textarea"] > div,
    [data-baseweb="select"] > div {
        background: var(--surface-soft);
        border-color: var(--border-strong);
        border-radius: 10px;
    }
    [data-baseweb="input"] input,
    [data-baseweb="textarea"] textarea,
    [data-baseweb="select"] input { color: var(--text); }
    [data-baseweb="input"] input::placeholder,
    [data-baseweb="textarea"] textarea::placeholder { color: var(--subtle); }
    [data-baseweb="input"] > div:focus-within,
    [data-baseweb="textarea"] > div:focus-within,
    [data-baseweb="select"] > div:focus-within {
        border-color: var(--blue) !important;
        box-shadow: 0 0 0 1px var(--blue);
    }
    [data-baseweb="select"] span { color: var(--text); }

    [data-testid="stExpander"] { overflow: hidden; }
    [data-testid="stExpander"] summary { color: var(--text); }
    [data-testid="stExpander"] details { background: var(--surface); }
    [data-testid="stExpander"] [data-testid="stExpanderDetails"] {
        border-top: 1px solid var(--border);
        padding-top: 1rem;
    }

    [data-testid="stCodeBlock"] {
        border: 1px solid #2b3b55;
        border-radius: 11px;
        overflow: hidden;
        background: #0a111e;
    }
    [data-testid="stCodeBlock"] pre,
    [data-testid="stCodeBlock"] code {
        color: #dce6f6;
        font-size: .88rem;
        line-height: 1.65;
    }
    [data-testid="stCodeBlock"] button { color: #b8c8df; }

    [data-testid="stChatMessage"] {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 1rem;
    }
    [data-testid="stChatInput"] textarea {
        background: var(--surface-soft);
        color: var(--text);
    }

    [data-testid="stAlert"] { color: var(--text); }
    [data-testid="stAlert"] p { color: var(--text); }
    hr { border-color: var(--border); }

    @media (max-width: 720px) {
        [data-testid="stMainBlockContainer"] {
            padding: 1.15rem 1rem 2rem;
        }
        .hero { border-radius: 15px; margin-bottom: 1rem; }
        .metric-card { padding: 1rem; }
        [data-testid="stMetric"] { min-height: 88px; padding: .8rem; }
        [data-testid="stTabs"] [role="tablist"] {
            overflow-x: auto;
            flex-wrap: nowrap;
        }
        [data-testid="stTabs"] button[role="tab"] {
            white-space: nowrap;
            padding: .6rem .7rem;
        }
    }
    </style>

    <div class="hero">
        <h1>🧭 Codebase Onboarder AI</h1>
        <p>
            Understand unfamiliar repositories with code analysis,
            architecture mapping, documentation, and evidence-grounded AI.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:
    st.markdown("## Repository")

    source = st.radio(
        "Import source",
        ["Public GitHub repository", "Upload ZIP"],
    )

    github_url = ""
    uploaded_zip = None

    if source == "Public GitHub repository":
        github_url = st.text_input(
            "GitHub URL",
            placeholder="https://github.com/owner/repository",
        )
    else:
        uploaded_zip = st.file_uploader(
            "Repository ZIP",
            type=["zip"],
        )

    max_files = st.slider(
        "Maximum files to analyze",
        min_value=100,
        max_value=3000,
        value=800,
        step=100,
    )

    analyze_clicked = st.button(
        "Analyze repository",
        type="primary",
        use_container_width=True,
    )

    st.divider()
    st.caption(
        "Safety: repository code is inspected as source text. "
        "The repository's code is not executed."
    )


# =========================================================
# LOAD AND ANALYZE REPOSITORY
# =========================================================

if analyze_clicked:
    try:
        if source == "Public GitHub repository" and not github_url.strip():
            st.error("Enter a public GitHub repository URL first.")
            st.stop()

        if source == "Upload ZIP" and uploaded_zip is None:
            st.error("Upload a repository ZIP file first.")
            st.stop()

        with st.spinner("Importing repository safely..."):
            if source == "Public GitHub repository":
                repo_files, repo_label = load_github_repository(
                    github_url.strip(),
                    max_files=max_files,
                )
            else:
                repo_files, repo_label = load_zip_repository(
                    uploaded_zip,
                    max_files=max_files,
                )

        with st.spinner("Analyzing source files and relationships..."):
            results = analyze_repository(
                repo_files,
                max_files=max_files,
            )

        st.session_state["repo_files"] = repo_files
        st.session_state["repo_label"] = repo_label
        st.session_state["analysis"] = results

        # Clear old answers when a new repository is analyzed.
        st.session_state.pop("chat_history", None)

        st.success(f"Analysis complete: {repo_label}")

    except Exception as exc:
        st.error(f"Could not analyze repository: {exc}")


# =========================================================
# EMPTY STATE
# =========================================================

results = st.session_state.get("analysis")

if not results:
    st.info(
        "Import a public GitHub repository or ZIP file, "
        "then select Analyze repository."
    )

    st.markdown("### What you can do")

    cols = st.columns(3)

    cards = [
        (
            "🔎",
            "Repository analysis",
            "Inspect files, languages, functions, classes, and imports.",
        ),
        (
            "🕸️",
            "Architecture mapping",
            "Explore modules and their local dependencies.",
        ),
        (
            "🤖",
            "AI assistance",
            "Ask questions using retrieved repository source excerpts.",
        ),
    ]

    for col, (icon, title, description) in zip(cols, cards):
        with col:
            st.markdown(
                f"""
                <div class="metric-card">
                    <h3>{icon} {title}</h3>
                    <p class="muted">{description}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.stop()


# =========================================================
# REPOSITORY SUMMARY
# =========================================================

repo_files = st.session_state.get("repo_files", {})
repo_label = st.session_state.get("repo_label", "Repository")
summary = results["summary"]

st.markdown(f"## 📦 {repo_label}")

m1, m2, m3, m4 = st.columns(4)

m1.metric("Files analyzed", summary["files_analyzed"])
m2.metric("Python files", summary["python_files"])
m3.metric("Functions", summary["functions"])
m4.metric("Classes", summary["classes"])


# =========================================================
# MAIN TABS
# =========================================================

(
    tab_overview,
    tab_architecture,
    tab_explorer,
    tab_documentation,
    tab_ai,
    tab_findings,
) = st.tabs(
    [
        "Overview",
        "Architecture",
        "Code Explorer",
        "Documentation",
        "AI Assistant",
        "Analysis Findings",
    ]
)


# =========================================================
# OVERVIEW
# =========================================================

with tab_overview:
    left, right = st.columns(2)

    with left:
        st.subheader("Language distribution")

        if results.get("languages"):
            st.bar_chart(results["languages"])
        else:
            st.info("No supported source files were found.")

    with right:
        st.subheader("Repository snapshot")

        st.write(f"**Files discovered:** {summary['files_discovered']}")
        st.write(
            "**Files skipped by limits/filters:** "
            f"{summary['files_skipped']}"
        )
        st.write(f"**Imports detected:** {summary['imports_detected']}")
        st.write(f"**Parse errors:** {summary['parse_errors']}")

        st.caption(
            "The analyzer deeply parses Python. "
            "Other file types may be included in language statistics."
        )


# =========================================================
# ARCHITECTURE
# =========================================================

with tab_architecture:
    st.subheader("Interactive dependency map")

    st.caption(
        "Nodes represent Python modules. Arrows represent detected "
        "local imports. Repository code is not executed."
    )

    try:
        graph_html, graph_stats = build_interactive_graph(
            results["modules"]
        )

        st.write(
            f"{graph_stats['nodes']} modules · "
            f"{graph_stats['edges']} dependency links"
        )

        if graph_stats["nodes"]:
            components.html(
                graph_html,
                height=650,
                scrolling=True,
            )
        else:
            st.warning("No Python modules were available to graph.")

        st.download_button(
            "Download architecture HTML",
            data=graph_html.encode("utf-8"),
            file_name="codebase-architecture.html",
            mime="text/html",
        )

    except Exception as exc:
        st.error(f"Could not build the architecture graph: {exc}")


# =========================================================
# CODE EXPLORER
# =========================================================

with tab_explorer:
    st.subheader("File and symbol explorer")

    all_paths = sorted(results.get("file_details", {}).keys())

    if not all_paths:
        st.info("No file details are available.")
    else:
        selected_path = st.selectbox(
            "Choose a file",
            all_paths,
        )

        detail = results["file_details"][selected_path]

        st.markdown(
            f"**Language:** {detail.get('language', 'Unknown')} "
            f"· **Lines:** {detail.get('lines', 0)}"
        )

        symbols = detail.get("symbols", [])

        if symbols:
            st.markdown("#### Detected symbols")

            for symbol in symbols:
                st.code(
                    f"{symbol['kind']}: {symbol['name']} "
                    f"(line {symbol['line']})",
                    language="text",
                )

        imports = detail.get("imports", [])

        if imports:
            st.markdown("#### Imports")
            st.code("\n".join(imports), language="text")

        content = repo_files.get(selected_path, "")

        with st.expander("View source (read-only)"):
            language = (
                "python"
                if selected_path.endswith(".py")
                else "text"
            )

            st.code(
                content[:30000] if content else "Source unavailable.",
                language=language,
            )

            if len(content) > 30000:
                st.caption("Preview truncated to 30,000 characters.")


# =========================================================
# GENERATED DOCUMENTATION
# =========================================================

with tab_documentation:
    st.subheader("Repository documentation")

    st.caption(
        "Documentation is generated from the imported files "
        "and structural analysis."
    )

    try:
        documentation = generate_documentation(
            repo_files,
            results,
            label=repo_label,
        )

        st.markdown(documentation)

        st.download_button(
            "Download repository documentation",
            data=documentation,
            file_name="repository-guide.md",
            mime="text/markdown",
        )

    except Exception as exc:
        st.error(f"Could not generate documentation: {exc}")


# =========================================================
# GROQ AI ASSISTANT
# =========================================================

with tab_ai:
    st.subheader("Ask your repository")

    st.caption(
        "Groq generates answers from retrieved source excerpts. "
        "Semantic retrieval requires the optional packages in "
        "requirements-rag.txt. The API does not replace repository evidence."
    )

    if not os.getenv("GROQ_API_KEY"):
        st.warning(
            "GROQ_API_KEY is missing. Add your key to the .env file "
            "and restart Streamlit."
        )

    question = st.text_input(
        "Your question",
        placeholder=(
            "How does authentication work in this repository?"
        ),
        key="repository_question",
    )

    ask_clicked = st.button(
        "Ask AI",
        type="primary",
        disabled=not bool(question.strip()),
    )

    if ask_clicked:
        if not os.getenv("GROQ_API_KEY"):
            st.error("Configure GROQ_API_KEY in your .env file first.")

        else:
            try:
                with st.spinner("Retrieving repository evidence..."):
                    excerpts = retrieve(
                        repo_files,
                        question.strip(),
                        top_k=5,
                    )

                if not excerpts:
                    st.warning(
                        "No relevant source excerpts were retrieved. "
                        "Try a more specific question."
                    )

                elif not evidence_is_relevant(
                    excerpts,
                    minimum_score=0.20,
                ):
                    st.warning(
                        "The retrieved excerpts may not be sufficiently "
                        "relevant. Try a more specific question."
                    )

                else:
                    with st.spinner("Generating answer with Groq..."):
                        answer = groq_answer(
                            question.strip(),
                            excerpts,
                        )

                    st.session_state["last_ai_answer"] = answer
                    st.session_state["last_ai_sources"] = excerpts
                    st.session_state["last_ai_question"] = question.strip()

            except Exception as exc:
                st.error(f"AI request failed: {exc}")

    if st.session_state.get("last_ai_answer"):
        st.markdown("### Answer")
        st.markdown(st.session_state["last_ai_answer"])

        with st.expander("Retrieved source excerpts"):
            for chunk in st.session_state.get("last_ai_sources", []):
                st.markdown(
                    f"**{chunk['path']}** "
                    f"(lines {chunk['start_line']}-"
                    f"{chunk['end_line']}, "
                    f"score {chunk.get('score', 0):.3f})"
                )
                st.code(chunk["text"][:5000], language="text")


# =========================================================
# ANALYSIS FINDINGS
# =========================================================

with tab_findings:
    st.subheader("Analysis findings")

    findings = results.get("findings", [])

    if findings:
        for finding in findings:
            st.markdown(f"- {finding}")
    else:
        st.success("No findings from the initial structural checks.")

    st.caption(
        "These are lightweight structural checks, not a full security "
        "audit or proof that the repository is bug-free."
    )


# =========================================================
# FOOTER
# =========================================================

st.divider()

st.caption(
    "Codebase Onboarder AI · Static repository analysis · "
    "Groq-powered, evidence-grounded assistance"
)
