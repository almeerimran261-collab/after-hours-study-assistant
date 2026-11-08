"""Cloud entrypoint using the public sample collection."""
import os
from pathlib import Path
import runpy

os.environ["RAG_MODE"] = "demo"
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
runpy.run_path(str(Path(__file__).resolve().parent / "app.py"), run_name="__main__")
