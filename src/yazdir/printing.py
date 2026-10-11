"""CUPS access: pycups when available (and inside Flatpak), otherwise the lp/lpstat command line tools."""

from __future__ import annotations

import re
import shutil
import subprocess

try:
    import cups
except ImportError:  # pycups is optional on native installs
    cups = None


class PrintError(RuntimeError):
    pass


def _connection():
    try:
        return cups.Connection()
    except RuntimeError as e:
        raise PrintError(str(e)) from e


def available() -> bool:
    return cups is not None or shutil.which("lp") is not None


def printers():
    """Return (names, default name or None)."""
    if cups is not None:
        try:
            conn = _connection()
            return sorted(conn.getPrinters()), conn.getDefault()
        except (PrintError, cups.IPPError):
            return [], None
    try:
        names = subprocess.run(["lpstat", "-e"], capture_output=True, text=True, check=False).stdout.split()
        default = subprocess.run(["lpstat", "-d"], capture_output=True, text=True, check=False).stdout
    except OSError:
        return [], None
    m = re.search(r":\s*(\S+)", default)
    return names, (m[1] if m else None)


def submit(printer: str, pdf: str, title: str, options: dict[str, str]) -> str:
    """Send a PDF to a CUPS queue and return the job id."""
    if cups is not None:
        try:
            return str(_connection().printFile(printer, pdf, title, options))
        except cups.IPPError as e:
            raise PrintError(e.args[-1] if e.args else str(e)) from e
    cmd = ["lp", "-d", printer, "-t", title]
    for key, value in options.items():
        cmd += ["-o", f"{key}={value}"]
    result = subprocess.run([*cmd, pdf], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise PrintError(result.stderr.strip())
    m = re.search(r"request id is (\S+)", result.stdout)
    return m[1] if m else "?"


def job_pending(job_id: str) -> bool:
    """True while the job is still queued or printing."""
    if cups is not None:
        try:
            return int(job_id) in _connection().getJobs(which_jobs="not-completed")
        except (PrintError, cups.IPPError, ValueError):
            return False
    out = subprocess.run(["lpstat", "-o"], capture_output=True, text=True, check=False).stdout
    return any(line.split()[0] == job_id for line in out.splitlines() if line.strip())


def job_options(paper: str, quality: str, copies: int = 1, collate: bool = True, reverse: bool = False) -> dict[str, str]:
    """Options common to every job. Sides are already paper-sized, so CUPS must not scale them."""
    options = {
        "media": paper,
        "print-scaling": "none",
        "scaling": "100",
        "print-quality": "3" if quality == "Draft" else "4",
        "OutputMode": quality,  # some drivers (e.g. hpcups) use this PPD option instead of print-quality
    }
    if copies > 1:
        options["copies"] = str(copies)
        options["collate"] = "true" if collate else "false"
    if reverse:
        options["outputorder"] = "reverse"
    return options
