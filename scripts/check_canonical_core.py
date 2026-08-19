"""Fail CI if the vendored Grounding Kernel core drifts from the recorded upstream core.

When ARC-IHB-Engine intentionally changes its canonical core, update both the
vendored file and EXPECTED_GIT_BLOB_SHA in this script in the same reviewed PR.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "ihb" / "core.py"
EXPECTED_GIT_BLOB_SHA = "eccd4a3028144702b53bf2096602591c3075f5df"


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def main() -> None:
    data = CORE.read_bytes()
    actual = git_blob_sha(data)
    if actual != EXPECTED_GIT_BLOB_SHA:
        raise SystemExit(
            "Canonical IHB core parity failure: "
            f"expected upstream blob {EXPECTED_GIT_BLOB_SHA}, got {actual}. "
            "Do not silently accept drift; sync from ARC-IHB-Engine and review the change."
        )
    print(f"canonical core parity OK: {actual}")


if __name__ == "__main__":
    main()
