"""Rehydrate the private case sources listed in archived manifests."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from urllib.request import Request, urlopen


def fetch(path, receipt):
    size = receipt["bytes"]
    expected = receipt["sha256"]
    if path.exists():
        raw = path.read_bytes()
    else:
        request = Request(receipt["url"], headers={"User-Agent": "PaperM-private-reproduction/1.0"})
        with urlopen(request, timeout=90) as response:
            raw = response.read(size + 1)
    if len(raw) != size or sha256(raw).hexdigest() != expected:
        raise ValueError(f"Input differs from pinned receipt: {path}")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
    print(path)


def run(history):
    here = Path(__file__).resolve().parent
    work = here.parent
    dl21 = json.loads((here / "intake/frozen/freeze.json").read_text())
    for name, receipt in dl21["inputs"].items():
        fetch(here / "intake/dl21_candidates" / name, receipt)
    dl19_dir = work / "paperm_revision/holdout/inputs"
    dl19 = json.loads((dl19_dir / "dl19_input_eligibility.json").read_text())
    dl20_dir = work / "ipm/literature"
    dl20 = json.loads((work / "dl20_pilot/dl20_input_eligibility.json").read_text())
    fetch(dl19_dir / "2019qrels-pass.txt", dl19["qrels"])
    fetch(dl20_dir / "dl20_qrels.txt", dl20["qrels"])
    if history:
        for model, receipt in dl19["runs"].items():
            fetch(dl19_dir / f"{model}.txt", receipt)
        for model, receipt in dl20["runs"].items():
            fetch(dl20_dir / f"dl20_{model}.txt", receipt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true", help="also acquire the eight historical runs")
    run(parser.parse_args().history)
