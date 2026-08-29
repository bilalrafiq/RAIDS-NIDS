from pathlib import Path
import subprocess

import pytest

from scripts import verify_repository


def run_git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_hygiene_uses_tracked_files_in_a_working_checkout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    run_git(tmp_path, "init", "-q")
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("public\n", encoding="utf-8")
    run_git(tmp_path, "add", "tracked.txt")

    generated = tmp_path / "package.egg-info"
    generated.mkdir()
    (generated / "PKG-INFO").write_text("local build\n", encoding="utf-8")

    monkeypatch.setattr(verify_repository, "ROOT", tmp_path)
    file_count, largest_size, maximum_path = (
        verify_repository.verify_public_repository_hygiene()
    )

    assert file_count == 1
    assert largest_size == tracked.stat().st_size
    assert maximum_path == len("tracked.txt")

    run_git(tmp_path, "add", "-f", "package.egg-info/PKG-INFO")

    with pytest.raises(AssertionError, match="Generated directories present"):
        verify_repository.verify_public_repository_hygiene()
