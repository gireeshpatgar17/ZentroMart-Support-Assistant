"""Safely copy a separately obtained course dataset archive into data/raw."""
from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {"README.md", "DATA_DICTIONARY.md", "kb", "data", "practice", "tools"}


def find_dataset_root(folder: Path) -> Path:
    candidates = [folder, *[p for p in folder.iterdir() if p.is_dir()]]
    for candidate in candidates:
        if REQUIRED.issubset({p.name for p in candidate.iterdir()}):
            return candidate
    raise SystemExit("Could not find the course dataset root (expected kb/, data/, practice/, tools/, and README.md).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Path to the separately downloaded course dataset ZIP")
    parser.add_argument("--destination", type=Path, default=ROOT / "data" / "raw", help="Destination (default: data/raw)")
    args = parser.parse_args()
    archive = args.archive.expanduser().resolve()
    destination = args.destination.expanduser().resolve()
    if not archive.is_file():
        raise SystemExit(f"Dataset archive not found: {archive}")
    if destination.exists() and any(p.name != ".gitkeep" for p in destination.iterdir()):
        raise SystemExit(f"Destination is not empty; move or back it up first: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="zentromart-dataset-", dir=destination.parent) as temporary:
        stage = Path(temporary)
        with ZipFile(archive) as zf:
            for member in zf.infolist():
                path = PurePosixPath(member.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise SystemExit(f"Unsafe path in dataset archive: {member.filename}")
            zf.extractall(stage)
        source = find_dataset_root(stage)
        shutil.copytree(source, destination, dirs_exist_ok=True)
    print(f"Dataset copied to {destination}")
    print("The dataset remains local and is excluded from Git by .gitignore.")


if __name__ == "__main__":
    main()

