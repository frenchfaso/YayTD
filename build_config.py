import os
import re
import subprocess
from pathlib import Path


def _run_git(args):
    try:
        return subprocess.check_output(["git", *args], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def _normalize_display_version(value):
    value = (value or "").strip()
    if value.startswith("refs/tags/"):
        value = value.rsplit("/", 1)[-1]
    if re.match(r"^v\d", value):
        value = value[1:]

    match = re.fullmatch(r"(\d+(?:\.\d+){0,2})(?:-(\d+)-g([0-9a-f]+))?(-dirty)?", value)
    if not match:
        return re.sub(r"[^0-9A-Za-z.+-]", ".", value).strip(".") or "development"

    base, commits, sha, dirty = match.groups()
    if commits and sha:
        return f"{base}+{commits}.g{sha}{'.dirty' if dirty else ''}"
    return f"{base}{'+dirty' if dirty else ''}"


def resolve_app_version():
    for key in ("YAYTD_VERSION", "GITHUB_REF_NAME", "GITHUB_REF"):
        version = _normalize_display_version(os.environ.get(key))
        if version != "development":
            return version

    exact_tag = _run_git(["describe", "--tags", "--exact-match", "--match", "v[0-9]*"])
    if exact_tag:
        return _normalize_display_version(exact_tag)

    described = _run_git(["describe", "--tags", "--match", "v[0-9]*", "--dirty", "--always"])
    return _normalize_display_version(described)


def resolve_bundle_version(display_version):
    match = re.match(r"^\d+(?:\.\d+){0,2}", display_version)
    return match.group(0) if match else "0.0.0"


def write_version_file(path, display_version):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{display_version}\n", encoding="utf-8")
    return path.as_posix()
