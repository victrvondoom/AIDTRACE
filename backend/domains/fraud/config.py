"""Fraud-investigation settings (migrated from track1-agent; read from the environment)."""
import os
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

# Same FalkorDB the rest of Kairos uses. Per-tenant graphs are named `fraud_<site>`; GRAPH_NAME is the CLI default.
FALKORDB_URL = os.getenv("FALKORDB_URL", "redis://localhost:6380")
GRAPH_NAME = os.getenv("FRAUD_GRAPH_NAME", "fraud_default")

# Max relationships walked when looking for a ring (2 relationships = one shared device/card).
MAX_RING_RELS = int(os.getenv("MAX_RING_RELS", "6"))
# Minimum accounts (including the flagged one) before a freeze can be proposed.
MIN_RING_SIZE = int(os.getenv("MIN_RING_SIZE", "3"))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
