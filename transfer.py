from __future__ import annotations
import hashlib
import mimetypes
from pathlib import Path

# Deliberately below the common 2 GB boundary.
DEFAULT_PART_SIZE = 1_900_000_000

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb", buffering=1024 * 1024) as f:
        while True:
            block = f.read(16 * 1024 * 1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest()

def split_file(path: Path, temp_dir: Path, max_part_size: int):
    temp_dir.mkdir(parents=True, exist_ok=True)
    size = path.stat().st_size

    if size <= max_part_size:
        return [(path, size, sha256_file(path))]

    result = []
    part_no = 1

    with path.open("rb", buffering=1024 * 1024) as src:
        while True:
            part_path = temp_dir / f"{path.name}.part{part_no:04d}"
            written = 0

            with part_path.open("wb", buffering=1024 * 1024) as dst:
                while written < max_part_size:
                    block = src.read(min(16 * 1024 * 1024,
                                         max_part_size - written))
                    if not block:
                        break
                    dst.write(block)
                    written += len(block)

            if written == 0:
                part_path.unlink(missing_ok=True)
                break

            result.append((part_path, written, sha256_file(part_path)))
            part_no += 1

            if written < max_part_size:
                break

    return result

def reassemble(part_paths, output: Path):
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("wb", buffering=1024 * 1024) as dst:
        for part in part_paths:
            with Path(part).open("rb", buffering=1024 * 1024) as src:
                while True:
                    block = src.read(16 * 1024 * 1024)
                    if not block:
                        break
                    dst.write(block)

    return output

def mime_for(path: Path):
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"
