from __future__ import annotations

import zipfile
from pathlib import Path

from app.application.diagnostics import write_diagnostic_zip
from app.core.config import Settings


def test_diagnostic_zip_omits_secrets_and_media(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "backend.log").write_text("ready token=super-secret-token\n", encoding="utf-8")
    (tmp_path / "runtime.json").write_text('{"token":"nope"}', encoding="utf-8")
    settings = Settings(data_dir=tmp_path, token="unused")
    archive = write_diagnostic_zip(settings)
    assert archive.is_file()
    with zipfile.ZipFile(archive) as zipped:
        names = set(zipped.namelist())
        assert "summary.json" in names
        assert "backend.log" in names
        assert "runtime.json" not in names
        log_text = zipped.read("backend.log").decode("utf-8")
        assert "super-secret-token" not in log_text
        assert "[redacted]" in log_text
