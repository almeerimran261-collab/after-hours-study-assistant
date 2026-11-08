import os
from pathlib import Path

# Project root is the parent folder of src/.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"


def setting(name, default=""):
    """Read process settings or Streamlit's server-side secrets."""
    if name in os.environ:
        return os.environ[name]
    import streamlit as st
    try:
        return str(st.secrets.get(name, default))
    except FileNotFoundError:
        return default


RAG_MODE = setting("RAG_MODE", "local").strip().lower()
if RAG_MODE not in {"local", "demo"}:
    raise ValueError("RAG_MODE must be local or demo.")
DEMO_MODE = RAG_MODE == "demo"
DATABASE_DIR = PROJECT_ROOT / ("demo_chroma_db" if DEMO_MODE else "chroma_db")

# Local, free models. Both run on CPU; the first model download is one-time.
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL_NAME = "qwen3:4b-instruct"


COLLECTION_NAME = "public_demo" if DEMO_MODE else "course_notes"
CHUNK_SIZE = 900
CHUNK_OVERLAP = 120
TOP_K = 5
