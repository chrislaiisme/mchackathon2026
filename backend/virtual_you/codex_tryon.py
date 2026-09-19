"""Codex CLI backed virtual try-on generation."""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)

SUPPORTED_CATEGORIES = {"upper_body", "lower_body", "dress"}
DEFAULT_TIMEOUT_SECONDS = 180
DEFAULT_CONCURRENCY = 1
OUTPUT_NAME = "try-on-result.png"
LOG_TAIL_CHARS = 4000

_try_on_semaphore = asyncio.Semaphore(int(os.environ.get("CODEX_TRY_ON_CONCURRENCY", str(DEFAULT_CONCURRENCY))))


class CodexTryOnError(Exception):
    """Controlled error raised for Codex virtual try-on failures."""

    def __init__(self, code: str, message: str, *, status_code: int = 500):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _category_guidance(category: str) -> str:
    if category == "upper_body":
        return "For upper_body: replace only the relevant upper-body garment and preserve pants/skirt/shoes."
    if category == "lower_body":
        return "For lower_body: replace only the relevant lower-body garment and preserve the upper-body clothing."
    if category == "dress":
        return (
            "For dress: replace the appropriate outfit area with the supplied dress while preserving identity, "
            "pose, shoes, and unrelated accessories when possible."
        )
    raise CodexTryOnError("unsupported_category", f"Unsupported try-on category: {category}", status_code=400)


def _open_image(data: bytes, label: str) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        return image
    except UnidentifiedImageError as exc:
        raise CodexTryOnError("invalid_uploaded_image", f"{label} is not a valid image.", status_code=400) from exc
    except OSError as exc:
        raise CodexTryOnError("invalid_uploaded_image", f"{label} could not be opened as an image.", status_code=400) from exc


def _save_png(data: bytes, output_path: Path, label: str) -> tuple[int, int]:
    image = _open_image(data, label)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")
    return image.size


def _read_output_png(output_path: Path) -> tuple[bytes, tuple[int, int]]:
    try:
        image = Image.open(output_path)
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise CodexTryOnError("invalid_generated_image", "Generated try-on output is not a valid image.") from exc

    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue(), image.size


def _build_prompt(category: str, output_path: Path) -> str:
    guidance = _category_guidance(category)
    return f"""$imagegen

Create a high-quality virtual try-on image using the two provided reference images.

REFERENCE IMAGE 1:
This is the person.

REFERENCE IMAGE 2:
This is the exact garment that the person should wear.

Dress the person from reference image 1 in the garment from reference image 2.

Preserve the person's:
- identity
- facial appearance
- hairstyle
- body shape
- body proportions
- pose
- arms and hands
- lower-body clothing unless the requested garment replaces it
- shoes and accessories unless replacement is required

Preserve the garment's exact visual characteristics as faithfully as possible:
- color
- pattern
- texture
- sleeve length
- neckline
- garment length
- silhouette
- fit
- visible design details

IMPORTANT:
Do not redesign or reinterpret the garment.
Do not change short sleeves into long or three-quarter sleeves.
Do not change the neckline.
Do not invent additional garment details.
The result should look like the same person naturally wearing the supplied garment.

Category: {category}
{guidance}

Generate a clean, realistic fashion virtual try-on image.

After generation, copy the final selected generated image to this exact path:
{output_path}

The copied file must be a PNG image. Do not modify any source images.
"""


def _candidate_paths_from_text(text: str) -> list[Path]:
    candidates: list[Path] = []
    for match in re.finditer(r"(/[^'\"\s<>]+\.(?:png|jpg|jpeg|webp))", text, flags=re.IGNORECASE):
        candidates.append(Path(match.group(1)))
    return candidates


def _find_generated_output(tmpdir: Path, output_path: Path, text: str, started_at: float) -> Path | None:
    if output_path.exists():
        return output_path

    for path in sorted(tmpdir.rglob("*"), key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True):
        if path.name in {"person.png", "garment.png"}:
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} and path.is_file():
            return path

    for path in _candidate_paths_from_text(text):
        if path.exists() and path.is_file():
            return path

    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    generated_root = codex_home / "generated_images"
    if generated_root.exists():
        generated_files = [
            path
            for path in generated_root.rglob("*")
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
            and path.is_file()
            and path.stat().st_mtime >= started_at
        ]
        if generated_files:
            return max(generated_files, key=lambda item: item.stat().st_mtime)

    return None


def _tail(value: str) -> str:
    return value[-LOG_TAIL_CHARS:] if len(value) > LOG_TAIL_CHARS else value


def _resolve_codex_bin() -> str:
    configured = os.environ.get("CODEX_BIN", "codex")
    expanded = Path(configured).expanduser()

    if expanded.parent != Path(".") or os.sep in configured:
        if expanded.exists() and os.access(expanded, os.X_OK):
            return str(expanded)
        raise CodexTryOnError(
            "codex_not_installed",
            f"Codex CLI configured at {expanded} does not exist or is not executable.",
            status_code=503,
        )

    resolved = shutil.which(configured)
    if resolved:
        return resolved

    local_default = Path.home() / ".local" / "bin" / configured
    if local_default.exists() and os.access(local_default, os.X_OK):
        return str(local_default)

    raise CodexTryOnError(
        "codex_not_installed",
        f"Codex CLI executable {configured!r} was not found on PATH.",
        status_code=503,
    )


async def _run_codex(tmpdir: Path, person_path: Path, garment_path: Path, prompt: str, timeout: float) -> tuple[str, str, int]:
    codex_bin = _resolve_codex_bin()
    last_message_path = tmpdir / "codex-last-message.txt"
    cmd = [
        codex_bin,
        "exec",
        "--skip-git-repo-check",
        "-C",
        str(tmpdir),
        "--image",
        str(person_path),
        "--image",
        str(garment_path),
        "--sandbox",
        "workspace-write",
        "--output-last-message",
        str(last_message_path),
        "-",
    ]
    logger.info("Codex try-on subprocess args=%r", cmd)

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise CodexTryOnError("codex_not_installed", "Codex CLI is not installed or not on PATH.", status_code=503) from exc

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(prompt.encode("utf-8")), timeout=timeout)
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.wait()
        raise CodexTryOnError("codex_generation_timeout", "Codex try-on generation timed out.", status_code=504) from exc

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    last_message = last_message_path.read_text(encoding="utf-8", errors="replace") if last_message_path.exists() else ""
    combined_stdout = "\n".join(part for part in (stdout, last_message) if part)

    if process.returncode:
        logger.error(
            "Codex try-on subprocess failed args=%r exit_code=%s stdout_tail=%r stderr_tail=%r",
            cmd,
            process.returncode,
            _tail(combined_stdout),
            _tail(stderr),
        )

    return combined_stdout, stderr, process.returncode or 0


async def generate_try_on(person_bytes: bytes, garment_bytes: bytes, category: str) -> bytes:
    """Generate a virtual try-on PNG using Codex CLI and the imagegen skill."""

    if category not in SUPPORTED_CATEGORIES:
        raise CodexTryOnError("unsupported_category", f"Unsupported try-on category: {category}", status_code=400)

    timeout = float(os.environ.get("CODEX_TRY_ON_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS)))

    async with _try_on_semaphore:
        started_at = time.time()
        with tempfile.TemporaryDirectory(prefix="intentweave-codex-tryon-") as tmp:
            tmpdir = Path(tmp)
            person_path = tmpdir / "person.png"
            garment_path = tmpdir / "garment.png"
            output_path = tmpdir / OUTPUT_NAME

            person_size = _save_png(person_bytes, person_path, "personImage")
            garment_size = _save_png(garment_bytes, garment_path, "garmentImage")
            prompt = _build_prompt(category, output_path)
            (tmpdir / "prompt.txt").write_text(prompt, encoding="utf-8")

            logger.info(
                "Codex try-on started category=%s person_size=%s garment_size=%s timeout=%s",
                category,
                person_size,
                garment_size,
                timeout,
            )

            stdout, stderr, returncode = await _run_codex(tmpdir, person_path, garment_path, prompt, timeout)
            elapsed = time.time() - started_at
            logger.info("Codex try-on finished exit_code=%s elapsed=%.1fs", returncode, elapsed)

            if returncode != 0:
                lowered = f"{stdout}\n{stderr}".lower()
                if "not logged in" in lowered or "login" in lowered or "authentication" in lowered:
                    raise CodexTryOnError("codex_not_authenticated", "Codex CLI is not authenticated.", status_code=503)
                raise CodexTryOnError(
                    "codex_process_failed",
                    f"Codex try-on generation failed with exit code {returncode}.",
                    status_code=502,
                )

            generated_path = _find_generated_output(tmpdir, output_path, f"{stdout}\n{stderr}", started_at)
            if not generated_path:
                raise CodexTryOnError(
                    "generated_output_missing",
                    "Codex completed but no generated try-on image was found.",
                    status_code=502,
                )

            png_bytes, output_size = _read_output_png(generated_path)
            logger.info("Codex try-on output path=%s dimensions=%s", generated_path, output_size)

            if generated_path != output_path:
                try:
                    shutil.copyfile(generated_path, output_path)
                except OSError:
                    logger.debug("Could not copy generated output into temp directory", exc_info=True)

            return png_bytes
