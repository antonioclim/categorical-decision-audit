"""Acquire the pinned public DL22 inputs without replacing existing files."""

import json
from pathlib import Path
import sys

here = Path(__file__).resolve().parent
sys.path.insert(0, str(here.parents[1] / "paperm_proof"))
from fetch_inputs import fetch

receipt = json.loads((here / "structural_freeze.json").read_text())
for source in (receipt["qrels"], *receipt["sources"].values()):
    fetch(here / source["file"], source)
