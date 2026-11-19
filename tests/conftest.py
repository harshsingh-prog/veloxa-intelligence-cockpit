import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["VELOXA_LLM_POLISH"] = "0"   # tests are deterministic; the LLM path is tested with injected fake generators
import pytest
from veloxa.ingestion import ingest_all


@pytest.fixture(scope="session", autouse=True)
def ingested():
    return ingest_all(force=True)
