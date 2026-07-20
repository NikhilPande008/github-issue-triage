import io
import tarfile

from triage.sandbox.artifacts import copy_artifact


class FakeContainer:
    def get_archive(self, source):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            info = tarfile.TarInfo("pytest_output.txt")
            info.size = 6
            info.mtime = 123
            archive.addfile(info, io.BytesIO(b"result"))
        return [buffer.getvalue()], {}


def test_copy_artifact_preserves_content_and_timestamp(tmp_path) -> None:
    destination = copy_artifact(FakeContainer(), "/sandbox/pytest_output.txt", tmp_path / "pytest_output.txt")
    assert destination.read_text(encoding="utf-8") == "result"
    assert int(destination.stat().st_mtime) == 123
