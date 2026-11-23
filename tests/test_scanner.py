import base64
import io

import fitz
import pytesseract
from PIL import Image

import native_host.scanner as scanner
from native_host.scanner import response_for_request, scan_file, scan_text


def test_prompt_marker_match_is_case_insensitive():
    result = scan_text("Please check walled_sensitive before sending")

    assert result.supported
    assert result.matched
    assert "walled_sensitive" in result.excerpt


def test_plain_text_file_detects_marker():
    content = base64.b64encode(b"ordinary text WALLED_SENSITIVE more text").decode("ascii")

    result = scan_file("notes.txt", "text/plain", content)

    assert result.supported
    assert result.matched


def test_text_pdf_detects_marker():
    document = fitz.open()
    document.new_page().insert_text((72, 72), "WALLED_SENSITIVE")
    content = base64.b64encode(document.tobytes()).decode("ascii")
    document.close()

    result = scan_file("notes.pdf", "application/pdf", content)

    assert result.supported
    assert result.matched


def test_image_ocr_detects_marker_when_underscore_is_read_as_space(monkeypatch):
    image = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(image, format="PNG")
    monkeypatch.setattr(pytesseract, "image_to_string", lambda *_args, **_kwargs: "WALLED SENSITIVE")
    content = base64.b64encode(image.getvalue()).decode("ascii")

    result = scan_file("test.png", "image/png", content)

    assert result.supported
    assert result.matched


def test_scanned_pdf_ocr_detects_marker_when_underscore_is_read_as_space(monkeypatch):
    image = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(image, format="PNG")
    document = fitz.open()
    page = document.new_page()
    page.insert_image(page.rect, stream=image.getvalue())
    content = base64.b64encode(document.tobytes()).decode("ascii")
    document.close()
    monkeypatch.setattr(pytesseract, "image_to_string", lambda *_args, **_kwargs: "WALLED SENSITIVE")

    result = scan_file("scanned.pdf", "application/pdf", content)

    assert result.supported
    assert result.matched


def test_unknown_file_type_fails_closed():
    content = base64.b64encode(b"some content").decode("ascii")

    result = scan_file("archive.bin", "application/octet-stream", content)

    assert not result.supported
    assert "Unsupported" in result.error


def test_invalid_base64_fails_closed():
    result = scan_file("notes.txt", "text/plain", "not base64!")

    assert not result.supported
    assert "base64" in result.error


def test_oversized_file_fails_closed(monkeypatch):
    monkeypatch.setattr(scanner, "MAX_FILE_BYTES", 8)
    content = base64.b64encode(b"123456789").decode("ascii")

    result = scan_file("notes.txt", "text/plain", content)

    assert not result.supported
    assert "inspection limit" in result.error


def test_continue_prompt_happens_only_when_marker_matches():
    decisions = []
    confirm = lambda *args: decisions.append(args) or True

    ordinary = response_for_request({"action": "scan_text", "text": "hello"}, confirm)
    sensitive = response_for_request({"action": "scan_text", "text": "WALLED_SENSITIVE"}, confirm)

    assert ordinary == {"ok": True, "approved": True, "matched": False}
    assert sensitive == {"ok": True, "approved": True, "matched": True}
    assert len(decisions) == 1


def test_cancel_blocks_matching_prompt():
    response = response_for_request(
        {"action": "scan_text", "text": "WALLED_SENSITIVE"},
        lambda *_args: False
    )

    assert response == {"ok": True, "approved": False, "matched": True}


def test_matching_file_shows_confirmation_and_continue_approves():
    content = base64.b64encode(b"WALLED_SENSITIVE").decode("ascii")
    decisions = []
    response = response_for_request(
        {
            "action": "scan_file",
            "name": "notes.txt",
            "mime_type": "text/plain",
            "content_base64": content,
        },
        lambda *args: decisions.append(args) or True,
    )

    assert response == {"ok": True, "approved": True, "matched": True}
    assert len(decisions) == 1
    assert decisions[0][0] == "File"
    assert "notes.txt" in decisions[0][1]


def test_file_without_marker_does_not_show_confirmation():
    content = base64.b64encode(b"ordinary text").decode("ascii")
    decisions = []
    response = response_for_request(
        {
            "action": "scan_file",
            "name": "notes.txt",
            "mime_type": "text/plain",
            "content_base64": content,
        },
        lambda *args: decisions.append(args) or True,
    )

    assert response == {"ok": True, "approved": True, "matched": False}
    assert decisions == []


def test_cancel_blocks_matching_file():
    content = base64.b64encode(b"WALLED_SENSITIVE").decode("ascii")
    response = response_for_request(
        {
            "action": "scan_file",
            "name": "notes.txt",
            "mime_type": "text/plain",
            "content_base64": content,
        },
        lambda *_args: False,
    )

    assert response == {"ok": True, "approved": False, "matched": True}
