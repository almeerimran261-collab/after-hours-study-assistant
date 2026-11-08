"""Test hosted-demo mode locally without saving the API key."""
import os
from pathlib import Path
import subprocess
import sys
import warnings
from getpass import GetPassWarning, getpass


def main():
    env = os.environ.copy()
    env["RAG_MODE"] = "demo"
    key = env.get("GROQ_API_KEY", "").strip()
    if not key:
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)
            try:
                key = getpass("Groq API key for this run (hidden): ").strip()
            except GetPassWarning:
                print("Run this script in your PowerShell terminal for hidden key input.")
                return 1
    if not key:
        print("No API key entered. Demo stopped.")
        return 1
    env["GROQ_API_KEY"] = key
    print("Starting the public sample demo. Ctrl+C stops it.")
    try:
        return subprocess.call(
            [sys.executable, "-m", "streamlit", "run", "app.py"],
            cwd=Path(__file__).resolve().parent, env=env,
        )
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
