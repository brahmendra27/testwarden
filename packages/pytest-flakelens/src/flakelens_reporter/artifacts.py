"""Discover files produced by a test attempt (Playwright screenshots, traces, videos).

Rather than reimplementing pytest-playwright's output-folder naming, we snapshot
the output directory between attempts: any file that is new or modified since the
attempt started is attributed to that attempt. This stays correct across reruns
and works for any tool that drops files in the output dir.
"""
from pathlib import Path

KIND_BY_SUFFIX = {
    ".png": "screenshot",
    ".jpg": "screenshot",
    ".jpeg": "screenshot",
    ".zip": "trace",
    ".webm": "video",
    ".mp4": "video",
    ".txt": "log",
    ".log": "log",
}


def snapshot(output_dir: Path) -> dict[Path, float]:
    if not output_dir.is_dir():
        return {}
    return {
        path: path.stat().st_mtime
        for path in output_dir.rglob("*")
        if path.is_file()
    }


def diff_new_files(before: dict[Path, float], after: dict[Path, float]) -> list[tuple[Path, str]]:
    found = []
    for path, mtime in after.items():
        if path not in before or before[path] < mtime:
            kind = KIND_BY_SUFFIX.get(path.suffix.lower(), "other")
            found.append((path, kind))
    return sorted(found)
