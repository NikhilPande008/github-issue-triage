import io
import os
import tarfile
import time
from pathlib import Path


def copy_artifact(container, source_path: str, destination: Path) -> Path:
    stream, _ = container.get_archive(source_path)
    with tarfile.open(fileobj=io.BytesIO(b"".join(stream)), mode="r:") as archive:
        member = archive.next()
        if member is None or not member.isfile():
            raise FileNotFoundError(source_path)
        extracted = archive.extractfile(member)
        if extracted is None:
            raise FileNotFoundError(source_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(extracted.read())
        os.utime(destination, (member.mtime, member.mtime))
    return destination


def write_container_file(container, destination_path: str, content: str) -> None:
    data = content.encode("utf-8")
    name = Path(destination_path).name
    parent = str(Path(destination_path).parent)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        info = tarfile.TarInfo(name)
        info.size = len(data)
        info.mtime = int(time.time())
        archive.addfile(info, io.BytesIO(data))
    container.put_archive(parent, buffer.getvalue())
