import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from veloxa.ingestion import ingest_all
if __name__ == '__main__':
    print(ingest_all(force=True))
