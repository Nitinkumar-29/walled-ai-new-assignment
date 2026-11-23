from __future__ import annotations

import base64
import binascii
import io
import os
import re
from dataclasses import dataclass
from typing import Any, Callable

MARKER = "WALLED_SENSITIVE"
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_PDF_PAGES = 100
MAX_IMAGE_PIXELS = 40_000_000
MARKER_PATTERN = re.compile(re.escape(MARKER), re.IGNORECASE)
OCR_MARKER_PATTERN = re.compile(r"\bWALLED\s+SENSITIVE\b", re.IGNORECASE)
TEXT_EXTENSIONS = {".txt", ".csv", ".md", ".json", ".log"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


@dataclass(frozen=True)
class ScanResult:
    supported: bool
    matched: bool
    excerpt: str = ""
    error: str = ""


def _match(text: str) -> tuple[bool, str]:
    match = MARKER_PATTERN.search(text)
    if not match:
        return False, ""
    start = max(0, match.start() - 70)
    end = min(len(text), match.end() + 70)
    return True, text[start:end].replace("\x00", "")


def _match_ocr(text: str) -> tuple[bool, str]:
    return _match(OCR_MARKER_PATTERN.sub(MARKER, text))


def scan_text(text: Any) -> ScanResult:
    if not isinstance(text, str):
        return ScanResult(False, False, error="Prompt text was not a string.")
    matched, excerpt = _match(text)
    return ScanResult(True, matched, excerpt)


def _decode_content(content_base64: Any) -> bytes:
    if not isinstance(content_base64, str):
        raise ValueError("File content was missing.")
    if len(content_base64) > ((MAX_FILE_BYTES + 2) // 3) * 4 + 8:
        raise ValueError("File exceeds the 8 MiB inspection limit.")
    try:
        raw = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("File content was not valid base64.") from error
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("File exceeds the 8 MiB inspection limit.")
    return raw


def _scan_pdf(raw: bytes) -> ScanResult:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ScanResult(False, False, error="PDF inspection requires pypdf; install the native-host dependencies.")

    try:
        reader = PdfReader(io.BytesIO(raw), strict=True)
        if len(reader.pages) > MAX_PDF_PAGES:
            return ScanResult(False, False, error=f"PDF exceeds the {MAX_PDF_PAGES}-page inspection limit.")
        page_texts = [page.extract_text() or "" for page in reader.pages]
    except Exception as error:
        return ScanResult(False, False, error=f"Could not read PDF: {error}")

    combined = "\n".join(page_texts)
    matched, excerpt = _match(combined)
    if matched:
        return ScanResult(True, True, excerpt)

    image_pages = [index for index, text in enumerate(page_texts) if not text.strip()]
    if not image_pages:
        return ScanResult(True, False)

    try:
        import fitz
        from PIL import Image, ImageOps
        import pytesseract
    except ImportError:
        return ScanResult(False, False, error="This scanned PDF needs PyMuPDF, Pillow, and Tesseract OCR to be inspected.")

    try:
        document = fitz.open(stream=raw, filetype="pdf")
        for index in image_pages:
            page = document.load_page(index)
            if page.rect.width * page.rect.height * 4 > MAX_IMAGE_PIXELS:
                return ScanResult(False, False, error="A scanned PDF page exceeds the OCR image-size limit.")
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = Image.open(io.BytesIO(pixmap.tobytes("png")))
            text = pytesseract.image_to_string(ImageOps.grayscale(image), timeout=20)
            matched, excerpt = _match_ocr(text)
            if matched:
                return ScanResult(True, True, excerpt)
    except Exception as error:
        return ScanResult(False, False, error=f"Could not OCR scanned PDF: {error}")
    return ScanResult(True, False)


def _scan_image(raw: bytes) -> ScanResult:
    try:
        from PIL import Image, ImageOps
        import pytesseract
    except ImportError:
        return ScanResult(False, False, error="Image inspection requires Pillow and pytesseract.")

    try:
        image = Image.open(io.BytesIO(raw))
        if image.width * image.height > MAX_IMAGE_PIXELS:
            return ScanResult(False, False, error="Image exceeds the 40-megapixel inspection limit.")
        image.load()
        image = ImageOps.grayscale(image)
        if max(image.size) < 1400:
            scale = min(3, 1400 / max(image.size))
            image = image.resize((int(image.width * scale), int(image.height * scale)))
        text = pytesseract.image_to_string(image, timeout=20)
    except Exception as error:
        return ScanResult(False, False, error=f"Could not OCR image (check that Tesseract is installed): {error}")

    matched, excerpt = _match_ocr(text)
    return ScanResult(True, matched, excerpt)


def scan_file(name: Any, mime_type: Any, content_base64: Any) -> ScanResult:
    if not isinstance(name, str) or not name:
        return ScanResult(False, False, error="File name was missing.")

    try:
        raw = _decode_content(content_base64)
    except ValueError as error:
        return ScanResult(False, False, error=str(error))

    extension = os.path.splitext(name)[1].lower()
    mime = mime_type.lower() if isinstance(mime_type, str) else ""
    if raw.startswith(b"%PDF-") or extension == ".pdf" or mime == "application/pdf":
        if not raw.startswith(b"%PDF-"):
            return ScanResult(False, False, error="The selected file is not a valid PDF.")
        return _scan_pdf(raw)
    if extension in IMAGE_EXTENSIONS or mime.startswith("image/"):
        return _scan_image(raw)
    if extension in TEXT_EXTENSIONS or mime.startswith("text/"):
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return ScanResult(False, False, error="Text file is not valid UTF-8 and could not be inspected.")
        matched, excerpt = _match(text)
        return ScanResult(True, matched, excerpt)
    return ScanResult(False, False, error="Unsupported file type. Only text files, PDFs, and images can be inspected.")


def response_for_request(message: Any, confirm: Callable[[str, str, str], bool]) -> dict[str, Any]:
    if not isinstance(message, dict):
        return {"ok": False, "approved": False, "error": "Invalid native-host request."}

    action = message.get("action")
    if action == "scan_text":
        result = scan_text(message.get("text"))
        if not result.supported:
            return {"ok": False, "approved": False, "error": result.error}
        if not result.matched:
            return {"ok": True, "approved": True, "matched": False}
        approved = confirm("Prompt", "WALLED_SENSITIVE was found in the prompt.", result.excerpt)
        return {"ok": True, "approved": approved, "matched": True}

    if action == "scan_file":
        name = message.get("name")
        result = scan_file(name, message.get("mime_type"), message.get("content_base64"))
        if not result.supported:
            return {"ok": False, "approved": False, "error": result.error}
        if not result.matched:
            return {"ok": True, "approved": True, "matched": False}
        approved = confirm("File", f"WALLED_SENSITIVE was found in {name}.", result.excerpt)
        return {"ok": True, "approved": approved, "matched": True}

    return {"ok": False, "approved": False, "error": "Unknown native-host action."}
