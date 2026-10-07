"""Download the official raw GoEmotions TSV splits required by ``train_improved``."""
from __future__ import annotations

import argparse
from pathlib import Path
from urllib.request import urlretrieve

BASE_URL = "https://raw.githubusercontent.com/google-research/google-research/master/goemotions/data"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/goemotions"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for split in ("train", "dev", "test"):
        destination = args.output_dir / f"{split}.tsv"
        urlretrieve(f"{BASE_URL}/{split}.tsv", destination)
        print(f"Saved {destination}")


if __name__ == "__main__":
    main()
