import asyncio
from pathlib import Path, PurePosixPath, PureWindowsPath
import tempfile
import threading
from uuid import uuid4
import zipfile

OUTPUT_ROOT = str(Path(__file__).resolve().parent.parent / "data" / "generated")
MAX_FILES = 64
MAX_BYTES = 5 * 1024 * 1024


def _package(project_name, files, cancelled):
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise ValueError("Supply 1–64 files.")
    root = Path(OUTPUT_ROOT).resolve()
    root.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c for c in str(project_name) if c.isalnum() or c in "-_")[:60] or "project"
    archive = root / f"{safe_name}-{uuid4().hex}.zip"
    total = 0
    paths = set()
    try:
        # Only files under this fresh generated directory can be cleaned up.
        with tempfile.TemporaryDirectory(prefix="build-", dir=root) as tmp:
            directory = Path(tmp).resolve()
            directory.relative_to(root)
            for item in files:
                if cancelled.is_set():
                    raise RuntimeError("Packaging cancelled.")
                relative = str(item["path"]).replace("\\", "/")
                path = PurePosixPath(relative)
                if path.is_absolute() or PureWindowsPath(relative).drive or ".." in path.parts or not path.name:
                    raise ValueError("Generated file paths must remain inside the project.")
                destination = (directory / path).resolve()
                destination.relative_to(directory)
                if str(destination).casefold() in paths:
                    raise ValueError("Duplicate generated file path.")
                paths.add(str(destination).casefold())
                data = item["content"].encode("utf-8")
                total += len(data)
                if total > MAX_BYTES:
                    raise ValueError("Generated files exceed the 5 MiB limit.")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
                for path in directory.rglob("*"):
                    if cancelled.is_set():
                        raise RuntimeError("Packaging cancelled.")
                    if path.is_file():
                        zipped.write(path, path.relative_to(directory))
        if cancelled.is_set():
            raise RuntimeError("Packaging cancelled.")
        return str(archive)
    except BaseException:
        archive.unlink(missing_ok=True)
        raise


async def package_files(project_name: str, files: list[dict]) -> str:
    """Keep disk/ZIP work off Discord's loop, clean late artifacts on cancellation."""
    cancelled = threading.Event()
    worker = asyncio.create_task(asyncio.to_thread(_package, project_name, files, cancelled))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        cancelled.set()
        def cleanup(done):
            try:
                artifact = Path(done.result()).resolve()
                artifact.relative_to(Path(OUTPUT_ROOT).resolve())
                artifact.unlink(missing_ok=True)
            except (Exception, asyncio.CancelledError):
                pass
        worker.add_done_callback(cleanup)
        raise


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "package_files",
        "description": (
            "Package one or more generated code/website files into a downloadable "
            "zip. Call this AFTER you have written the full content of each file "
            "yourself. Use this whenever the user asks you to build a website, "
            "script, app, or any multi-file project."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Short project name, used as the zip filename."},
                "files": {
                    "type": "array",
                    "description": "List of files to write.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Relative file path, e.g. index.html or src/app.py"},
                            "content": {"type": "string", "description": "Full file content."},
                        },
                        "required": ["path", "content"],
                    },
                },
            },
            "required": ["project_name", "files"],
        },
    },
}
