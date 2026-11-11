from pathlib import Path
from html import escape
from src.branding import render_brand

import streamlit as st
from src.cosmos import mount_cosmos
from src.config import COLLECTION_NAME, DEMO_MODE, PROJECT_ROOT
from src.course_collections import get_client, open_collection
from src.embeddings import load_embedding_model
from src.generator import CITATION_PATTERN, generate_answer
from src.memory import ConversationMemory
from src.retriever import retrieve_chunks


ICON_PATH = (
    Path(__file__).resolve().parent
    / "assets"
    / "saturn.svg"
)

st.set_page_config(
    page_title="Course Notes · Study workspace",
    page_icon=ICON_PATH.read_text(
        encoding="utf-8-sig"
    ).lstrip(),
    layout="wide",
)
st.markdown("""
<style>
.block-container {
    max-width:1120px;
    padding-top:2rem;
    padding-bottom:7rem;
}
[data-testid="stSidebar"] {
    border-right:1px solid #22314a;
}
.brand {
    display:flex;align-items:center;gap:12px;margin:0 0 24px;
}
.brand-mark {
    background:#70e1c2;color:#102a27;padding:10px;
    border-radius:13px;font-weight:800;
}
.brand small,.eyebrow {
    color:#91a9c4;font-size:.7rem;letter-spacing:.14em;
}
.brand strong {display:block;font-size:1.15rem;}
.hero {
    background:linear-gradient(120deg,#14263d,#102e32);
    border:1px solid #2c4659;border-radius:22px;padding:26px 30px;
}
.hero .eyebrow {color:#86e6ce;}
.hero h1 {
    color:#f1f6fc;font-size:2.65rem;line-height:1.15;
    margin:10px 0;padding:0;letter-spacing:-.035em;
}
.hero p {color:#b6c9dc;margin:0;line-height:1.7;}
.hero.compact h1 {font-size:2rem;}
.stats {
    display:grid;grid-template-columns:repeat(3,1fr);
    gap:12px;margin:16px 0 26px;
}
.stat {
    background:#111d30;border:1px solid #22314a;
    border-radius:15px;padding:14px 18px;
}
.stat strong {display:block;font-size:1.45rem;color:#eef3fa;}
.stat span {color:#9db0c9;font-size:.8rem;}
.section-label {
    color:#9db0c9;font-size:.73rem;
    letter-spacing:.12em;margin:18px 0 10px;
}
.doc {
    display:flex;align-items:center;gap:10px;
    border:1px solid #28384e;border-radius:12px;
    padding:11px;margin:9px 0;
}
.doc span {
    color:#70e1c2;font-size:.65rem;letter-spacing:.04em;
}
.doc strong {
    color:#d9e4f3;font-size:.83rem;
    font-weight:500;overflow-wrap:anywhere;
}
[data-testid="stButton"] button {
    border-radius:12px;min-height:46px;
    transition:border-color .15s,transform .15s;
}
[data-testid="stButton"] button:hover {
    border-color:#70e1c2;transform:translateY(-1px);
}
[data-testid="stChatMessage"] {
    background:#111d30;border:1px solid #23334a;
    border-radius:18px;padding:18px 22px;margin-bottom:16px;
}
[data-testid="stChatMessage"]:has(
    [data-testid="stChatMessageAvatarUser"]
) {
    background:#172a3b;margin-left:28px;
}
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"] {
    display:none;
}
[data-testid="stChatInput"] {
    border:1px solid #3a536d;border-radius:16px;
    box-shadow:0 8px 30px #0003;
}
[data-testid="stToolbar"] {visibility:hidden;}
.source-name {
    font-weight:650;color:#eef3fa;overflow-wrap:anywhere;
}
.source-badge {
    display:inline-block;font-size:.72rem;color:#8ce8cf;
    background:#153a36;border:1px solid #2b6055;
    border-radius:20px;padding:3px 10px;margin:6px 0 12px;
}
@media(max-width:640px) {
    .block-container {padding:1rem 1rem 6rem;}
    .hero {padding:20px;}
    .hero h1 {font-size:2rem;}
    .stat {padding:12px;}
    .stat span {font-size:.7rem;}
    [data-testid="stChatMessage"] {padding:14px;}
    [data-testid="stChatMessage"]:has(
        [data-testid="stChatMessageAvatarUser"]
    ) {margin-left:0;}
}
@media(prefers-reduced-motion:reduce) {
    [data-testid="stButton"] button {
        transition:none;transform:none!important;
    }
}
</style>
""", unsafe_allow_html=True)


@st.cache_resource(show_spinner=False)
def embedding_model():
    return load_embedding_model()


def friendly(name):
    if workspace is not None and workspace.collection is not None and name == workspace.collection.name:
        return "Uploaded documents · this session"
    if DEMO_MODE and name == COLLECTION_NAME:
        return "Public study notes"
    if name == COLLECTION_NAME:
        return "All course notes"
    return name.removeprefix("course_").replace("_", " ").title()


def reset_chat(name):
    st.session_state.active_collection = name
    st.session_state.messages = []
    st.session_state.question_memory = ConversationMemory()


def starters(sources):
    if DEMO_MODE:
        return [
            ("Explain LIFO", "What does LIFO mean?"),
            ("Trace an insertion", "What does insertAtEnd do when head is NULL?"),
            ("Explore overflow", "What does push do when the array stack is full?"),
        ]
    if "Week-04-Lec-01.pptx" in sources:
        return [
            (
                "Explore traversal",
                "According to the lecture, in which two directions "
                "can we travel in a doubly linked list?",
            ),
            (
                "Trace an insertion",
                "What does insertAtEnd do when head is NULL?",
            ),
            (
                "Understand a node",
                "What three components does a doubly linked list "
                "node contain?",
            ),
        ]
    if "Stack Lab Manual.pdf" in sources:
        return [
            (
                "Explain LIFO",
                "According to the lab manual, what does LIFO mean?",
            ),
            (
                "Explore operations",
                "What are the basic stack operations listed "
                "in the lab manual?",
            ),
            (
                "Understand underflow",
                "According to the lab manual, what causes "
                "stack underflow?",
            ),
        ]
    return []


def show_message(message, diagnostics):
    with st.chat_message(message["role"]):
        st.caption(
            "YOU" if message["role"] == "user" else "COURSE NOTES"
        )

        if message.get("failed"):
            st.error(message["content"])
        else:
            st.markdown(message["content"])

        if message["role"] != "assistant":
            return

        if diagnostics:
            st.caption(f"Result: {message.get('reason', '')}")
            st.text(
                f"Retrieval question: {message.get('query', '')}"
            )

        citations = {
            (
                match.group(1).strip(),
                "slide"
                if match.group(2).lower() == "slide"
                else "page",
                int(match.group(3)),
            )
            for match in CITATION_PATTERN.finditer(
                message["content"]
            )
        }

        hits = message.get("hits", [])
        if hits:
            labels = []
            for index, hit in enumerate(hits, 1):
                location = (
                    f"Slide {hit['slide']}"
                    if hit.get("location_type") == "slide"
                    else f"Page {hit['page']}"
                )
                labels.append(f"{index} · {location}")

            with st.expander(
                f"Explore {len(hits)} source passages"
            ):
                for tab, hit in zip(st.tabs(labels), hits):
                    with tab:
                        kind = (
                            "slide"
                            if hit.get("location_type") == "slide"
                            else "page"
                        )
                        number = (
                            hit["slide"]
                            if kind == "slide"
                            else hit["page"]
                        )
                        badge = (
                            "Cited location"
                            if (hit["source"], kind, number)
                            in citations
                            else "Retrieved context"
                        )
                        st.markdown(
                            '<div class="source-name">'
                            f'{escape(hit["source"])}</div>'
                            '<span class="source-badge">'
                            f"{badge} · {kind.title()} {number}"
                            "</span>",
                            unsafe_allow_html=True,
                        )
                        st.text(hit["text"])


@st.cache_resource(show_spinner="Preparing the public sample notes…")
def prepare_public_demo():
    from src.public_demo import ensure_public_demo
    return ensure_public_demo(embedding_model())


render_brand()

if DEMO_MODE:
    st.sidebar.caption(
        "Public demo · Groq. Your question and retrieved sample passages "
        "are sent to Groq to generate an answer."
    )
    try:
        prepare_public_demo()
    except Exception as exc:
        st.error(f"Could not prepare the public sample: {exc}")
        st.stop()

workspace = None
collection_controls = st.sidebar.container()
if not DEMO_MODE:
    from src.local_upload_ui import render_local_uploads
    workspace = render_local_uploads(embedding_model)

names = []
try:
    names = sorted(
        item if isinstance(item, str) else item.name
        for item in get_client().list_collections()
    )
    if DEMO_MODE:
        names = [COLLECTION_NAME]
except FileNotFoundError as exc:
    if DEMO_MODE:
        st.error(f"Could not open the document database: {exc}")
        st.stop()
except Exception as exc:
    st.warning(f"Could not open saved collections: {exc}")
    if DEMO_MODE:
        st.stop()

if workspace is not None and workspace.collection is not None:
    names.append(workspace.collection.name)
if not names:
    mount_cosmos()
    st.title("Bring your notes into orbit.")
    st.write("Open **Upload documents** in the sidebar, choose PDFs or lecture slides, "
             "then click **Index selected files** to start studying.")
    st.caption("Your files are processed locally. Keep this browser session open while studying.")
    st.stop()

# A cleared upload index must never leave a stale selectbox value behind.
if st.session_state.get("collection_choice") not in names:
    st.session_state.collection_choice = COLLECTION_NAME if COLLECTION_NAME in names else names[0]

selected = collection_controls.selectbox(
    "Your collection",
    names,
    format_func=friendly,
    key="collection_choice",
)

if st.session_state.get("active_collection") != selected:
    reset_chat(selected)

if collection_controls.button(
    "New conversation",
    key="new_chat",
    use_container_width=True,
):
    reset_chat(selected)

collection_controls.caption(
    "Switching collections starts a fresh conversation."
)

try:
    collection = (
        workspace.collection
        if workspace is not None and workspace.collection is not None
        and selected == workspace.collection.name
        else open_collection(selected)
    )
    if collection.count() == 0:
        st.warning("This collection is empty. Choose another collection.")
        st.stop()

    sources = sorted({
        metadata["source"]
        for metadata in collection.get(
            include=["metadatas"]
        )["metadatas"]
    })
except Exception as exc:
    st.error(f"Could not open this collection: {exc}")
    st.stop()

with st.sidebar.expander(
    f"Your documents · {len(sources)}",
    expanded=True,
):
    for source in sources:
        kind = (
            "PPTX"
            if source.lower().endswith(".pptx")
            else "PDF"
        )
        st.markdown(
            '<div class="doc">'
            f"<span>{kind}</span>"
            f"<strong>{escape(source)}</strong></div>",
            unsafe_allow_html=True,
        )

if DEMO_MODE:
    from src.public_demo import SOURCE
    st.sidebar.download_button(
        "Download sample notes",
        (PROJECT_ROOT / "demo_data" / SOURCE).read_bytes(),
        file_name=SOURCE, mime="application/pdf", key="sample_pdf",
        use_container_width=True,
    )

transcript = (
    f"# Course Notes — {friendly(selected)}\n\n"
    + "\n\n".join(
        f"## {message['role'].title()}\n{message['content']}"
        for message in st.session_state.messages
    )
)

st.sidebar.download_button(
    "Save conversation",
    transcript,
    file_name=f"{selected}_chat.md",
    mime="text/markdown",
    disabled=not st.session_state.messages,
    use_container_width=True,
    key="save_chat",
)

with st.sidebar.expander("Session details"):
    diagnostics = st.checkbox(
        "Show diagnostics",
        value=False,
        key="diagnostics",
    )
    st.caption(
        ("Runs with Groq using public sample notes. " if DEMO_MODE
         else "Runs locally with Ollama. ")
        + "Memory supports basic "
        "conditional follow-ups; check the source passages "
        "when studying."
    )
mount_cosmos()

messages = st.session_state.messages
title = (
    friendly(selected)
    if messages
    else "Learn from your notes."
)
subtitle = (
    "Continue your conversation and explore the supporting passages."
    if messages
    else "Ask a focused question. Follow the explanation. Check the sources."
)
hero_class = "hero compact" if messages else "hero"

st.markdown(
    f'<div class="{hero_class}">'
    f'<div class="eyebrow">{"PUBLIC DEMO" if DEMO_MODE else "LOCAL STUDY WORKSPACE"} · '
    f"{escape(friendly(selected))}</div>"
    f"<h1>{escape(title)}</h1><p>{subtitle}</p></div>",
    unsafe_allow_html=True,
)

question_count = sum(
    message["role"] == "user" for message in messages
)

st.markdown(
    '<div class="stats">'
    f'<div class="stat"><strong>{len(sources)}</strong>'
    "<span>Documents</span></div>"
    f'<div class="stat"><strong>{collection.count()}</strong>'
    "<span>Indexed passages</span></div>"
    f'<div class="stat"><strong>{question_count}</strong>'
    "<span>Questions this session</span></div></div>",
    unsafe_allow_html=True,
)

suggestion = None
if not messages:
    choices = starters(sources)
    if choices:
        st.markdown(
            '<div class="section-label">'
            "START WITH A QUESTION</div>",
            unsafe_allow_html=True,
        )
        columns = st.columns(len(choices))
        for index, ((label, prompt), column) in enumerate(
            zip(choices, columns)
        ):
            with column:
                if st.button(
                    label + " ↗",
                    key=f"starter_{index}",
                    help=prompt,
                    use_container_width=True,
                ):
                    suggestion = prompt

for message in messages:
    show_message(message, diagnostics)

question = (
    st.chat_input(
        "Ask a question, or follow up on your last one…"
    )
    or suggestion
)

if question and question.strip():
    question = question.strip()
    if DEMO_MODE and len(question) > 1000:
        st.warning("Please keep demo questions under 1,000 characters.")
        st.stop()
    user_message = {
        "role": "user",
        "content": question,
    }
    messages.append(user_message)
    show_message(user_message, diagnostics)

    hits, query, reason, failed = [], question, "", False

    try:
        with st.spinner(
            "Reading the relevant passages and preparing your answer…"
        ):
            query, clarify = (
                st.session_state.question_memory.rewrite(question)
            )

            if clarify:
                answer = (
                    f"Please restate your full question: {query}"
                )
                reason = "clarification_needed"
            else:
                hits = retrieve_chunks(
                    query,
                    embedding_model(),
                    collection,
                )

                if any(
                    hit.get("source") not in sources
                    for hit in hits
                ):
                    raise RuntimeError(
                        "Retrieved sources do not match "
                        "the selected collection."
                    )

                answer, reason, _ = generate_answer(
                    query,
                    hits,
                    return_diagnostics=True,
                )
                st.session_state.question_memory.remember(
                    question
                )

    except Exception as exc:
        answer = f"Could not complete this question: {exc}"
        reason, failed, hits = "error", True, []

    messages.append({
        "role": "assistant",
        "content": answer,
        "hits": hits,
        "query": query,
        "reason": reason,
        "failed": failed,
    })
    st.rerun()
