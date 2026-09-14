import base64
import binascii
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


TITLE_PREFIX_LIMIT = 64 * 1024


class DocumentError(ValueError):
    pass


@dataclass(frozen=True)
class DocumentSummary:
    id: str
    title: str
    path: str
    modified_at: str
    size: int

    def as_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class MarkdownDocument:
    summary: DocumentSummary
    markdown: str
    etag: str


def document_id(relative_path: str):
    return base64.urlsafe_b64encode(relative_path.encode("utf-8")).decode("ascii").rstrip("=")


def decoded_document_id(encoded: str):
    try:
        padding = "=" * (-len(encoded) % 4)
        decoded = base64.b64decode(
            encoded + padding, altchars=b"-_", validate=True
        ).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError) as error:
        raise DocumentError("Invalid document ID") from error
    relative = PurePosixPath(decoded)
    if (
        not decoded
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
        or relative.suffix.lower() != ".md"
    ):
        raise DocumentError("Invalid document ID")
    return relative


def document_title(path: Path):
    try:
        with path.open("rb") as source:
            prefix = source.read(TITLE_PREFIX_LIMIT).decode("utf-8", errors="replace")
    except OSError as error:
        raise DocumentError(f"Cannot read Markdown document {path}: {error}") from error

    lines = prefix.splitlines()
    fence = None
    for index, line in enumerate(lines):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if marker:
            candidate = marker.group(1)
            if fence is None:
                fence = (candidate[0], len(candidate))
            elif candidate[0] == fence[0] and len(candidate) >= fence[1]:
                fence = None
            continue
        if fence is not None:
            continue
        heading = re.match(r"^ {0,3}#(?:[ \t]+(.*)|[ \t]*)$", line)
        if heading:
            title = re.sub(r"[ \t]+#+[ \t]*$", "", heading.group(1) or "").strip()
            if title:
                return title
        if index + 1 < len(lines) and line.strip() and re.match(
            r"^ {0,3}=+[ \t]*$", lines[index + 1]
        ):
            return line.strip()
    return path.stem.replace("-", " ").replace("_", " ").strip() or path.name


def document_summary(root: Path, path: Path):
    root = root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise DocumentError("Document is outside the configured directory")
    relative = resolved.relative_to(root).as_posix()
    stat = resolved.stat()
    return DocumentSummary(
        id=document_id(relative),
        title=document_title(resolved),
        path=relative,
        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        size=stat.st_size,
    )


def list_documents(root: Path):
    if not root.is_dir():
        raise DocumentError(f"Markdown document directory does not exist: {root}")
    root = root.resolve()
    documents = []
    for candidate in root.rglob("*"):
        if candidate.suffix.lower() != ".md":
            continue
        try:
            documents.append(document_summary(root, candidate))
        except DocumentError:
            # Ignore broken links and links escaping the configured root.
            continue
    return sorted(documents, key=lambda item: item.path.casefold())


def load_document(root: Path, encoded_id: str):
    if not root.is_dir():
        raise DocumentError(f"Markdown document directory does not exist: {root}")
    root = root.resolve()
    relative = decoded_document_id(encoded_id)
    path = (root / Path(*relative.parts)).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise DocumentError("Markdown document does not exist")
    summary = document_summary(root, path)
    try:
        markdown = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise DocumentError(f"Cannot read Markdown document {summary.path}: {error}") from error
    stat = path.stat()
    return MarkdownDocument(
        summary=summary,
        markdown=markdown,
        etag=f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"',
    )
