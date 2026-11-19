"""Cross-platform one-command setup and launch."""
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
subprocess.check_call([sys.executable,'-m','pip','install','-r',str(ROOT/'requirements.txt')],cwd=ROOT)
subprocess.check_call([sys.executable,'-m','streamlit','run',str(ROOT/'app.py')],cwd=ROOT)
