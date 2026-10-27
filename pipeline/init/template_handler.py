"""Step 2 — Download template.zip from GitHub and extract into target."""

import sys
import urllib.request
import zipfile
from pathlib import Path

# ---------------------------------------------------------------------------
# URL used to download the template.
# ---------------------------------------------------------------------------
TEMPLATE_URL = (
    "https://github.com/synapse-ai-hub/synapseForge/raw/main/pipeline/template.zip"
)


def extract_template(target: Path) -> None:
    """Download the template zip from GitHub and extract into *target*.

    If the download fails, the process exits with an error.

    Args:
        target: Project directory.
    """
    zip_path = _download_template(target)
    if zip_path is None:
        print("  ERROR: could not obtain template.zip")
        sys.exit(1)

    _safe_extract(zip_path, target)

    # Delete the downloaded zip.
    zip_path.unlink(missing_ok=True)

    print(f"  Extracted to: {target}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _download_template(target: Path) -> Path | None:
    """Download template.zip from GitHub into *target*.

    Args:
        target: Directory where the zip is saved.

    Returns:
        The path of the zip, or None when the download fails.
    """
    try:
        dest = target / "template.zip"
        print("  Downloading template from GitHub …")
        urllib.request.urlretrieve(TEMPLATE_URL, dest)
        print(f"  Downloaded: {dest}")
        return dest
    except Exception as exc:
        print(f"  Download failed: {exc}")
        return None


def _safe_extract(zip_path: Path, target: Path) -> None:
    """Extract zip, overwriting existing files silently.

    Args:
        zip_path: Zip file to extract.
        target: Directory to extract into.
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(path=target)
    except zipfile.BadZipFile:
        print(f"  ERROR: corrupted zip file: {zip_path}")
        sys.exit(1)
    except Exception as exc:
        print(f"  ERROR extracting zip: {exc}")
        sys.exit(1)
