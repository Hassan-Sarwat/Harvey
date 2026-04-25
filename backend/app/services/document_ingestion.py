from __future__ import annotations

import re
import zipfile
from html import unescape
from io import BytesIO
from pathlib import PurePosixPath
from xml.etree import ElementTree


SUPPORTED_DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".csv",
    ".txt",
    ".md",
    ".json",
}


def safe_upload_path(filename: str) -> PurePosixPath:
    """Keep browser folder uploads, but prevent absolute paths and traversal."""
    parts = []
    for raw_part in PurePosixPath(filename.replace("\\", "/")).parts:
        if raw_part in {"", ".", ".."}:
            continue
        cleaned = re.sub(r"[^A-Za-z0-9._ -]", "_", raw_part).strip()
        if cleaned:
            parts.append(cleaned)
    return PurePosixPath(*parts) if parts else PurePosixPath("uploaded-document")


def extract_document_text(filename: str, content: bytes) -> str:
    extension = PurePosixPath(filename.lower()).suffix
    if extension not in SUPPORTED_DOCUMENT_EXTENSIONS:
        raise ValueError(f"Unsupported document type: {extension or 'unknown'}")

    if extension in {".txt", ".md", ".json", ".csv"}:
        return _decode_text(content)
    if extension == ".pdf":
        return _extract_pdf_text(content)
    if extension == ".docx":
        try:
            return _extract_docx_text(content)
        except (KeyError, zipfile.BadZipFile, ElementTree.ParseError):
            return _decode_text(content)
    if extension == ".xlsx":
        try:
            return _extract_xlsx_text(content)
        except (KeyError, zipfile.BadZipFile, ElementTree.ParseError):
            return _decode_text(content)

    return _decode_text(content)


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")


def _extract_pdf_text(content: bytes) -> str:
    if not content.lstrip().startswith(b"%PDF"):
        return _decode_text(content)

    try:
        from pypdf import PdfReader
    except ModuleNotFoundError:
        return _decode_text(content)

    try:
        reader = PdfReader(BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except Exception:
        return _decode_text(content)


def _extract_docx_text(content: bytes) -> str:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        xml = archive.read("word/document.xml")

    root = ElementTree.fromstring(xml)
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{namespace}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t"))
        if text.strip():
            paragraphs.append(text.strip())
    return "\n".join(paragraphs)


def _extract_xlsx_text(content: bytes) -> str:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        shared_strings = _read_xlsx_shared_strings(archive)
        sheet_names = sorted(name for name in archive.namelist() if name.startswith("xl/worksheets/sheet"))
        rows: list[str] = []
        for sheet_name in sheet_names:
            root = ElementTree.fromstring(archive.read(sheet_name))
            for row in root.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row"):
                values = [_xlsx_cell_text(cell, shared_strings) for cell in row]
                compact_values = [value for value in values if value]
                if compact_values:
                    rows.append(" | ".join(compact_values))
        return "\n".join(rows)


def _read_xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []

    strings: list[str] = []
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    for item in root.iter(f"{namespace}si"):
        strings.append(unescape("".join(text.text or "" for text in item.iter(f"{namespace}t"))))
    return strings


def _xlsx_cell_text(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    value = cell.find(f"{namespace}v")
    if value is None or value.text is None:
        inline = "".join(text.text or "" for text in cell.iter(f"{namespace}t"))
        return inline.strip()
    if cell.attrib.get("t") == "s":
        try:
            return shared_strings[int(value.text)].strip()
        except (IndexError, ValueError):
            return ""
    return value.text.strip()
