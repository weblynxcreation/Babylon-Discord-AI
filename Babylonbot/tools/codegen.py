"""
Code / website generation tool.

The LLM calls this with a list of {path, content} files it has already
written. This tool's only job is to materialize those files to disk and
zip them for Discord delivery — it does NOT generate code itself. That
keeps generation quality in the hands of the main model call (with full
conversation context) rather than a second, context-blind call.
"""
import os
import zipfile
import shutil
import time

OUTPUT_ROOT = "/home/claude/discord-ai-agent/generated"


async def package_files(project_name: str, files: list[dict]) -> str:
    """
    files: list of {"path": "index.html", "content": "..."}
    Returns the path to a zip file containing the project.
    """
    safe_name = "".join(c for c in project_name if c.isalnum() or c in "-_") or "project"
    ts = int(time.time())
    project_dir = os.path.join(OUTPUT_ROOT, f"{safe_name}-{ts}")
    os.makedirs(project_dir, exist_ok=True)

    for f in files:
        rel_path = f["path"].lstrip("/")
        full_path = os.path.join(project_dir, rel_path)
        os.makedirs(os.path.dirname(full_path) or project_dir, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as fh:
            fh.write(f["content"])

    zip_path = f"{project_dir}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, filenames in os.walk(project_dir):
            for filename in filenames:
                file_path = os.path.join(root, filename)
                arcname = os.path.relpath(file_path, project_dir)
                zf.write(file_path, arcname)

    shutil.rmtree(project_dir)
    return zip_path


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
