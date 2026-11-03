import io
import pytest
from fastapi import HTTPException

from app.security import read_upload_limited


class Upload:
    def __init__(self, payload):
        self.file = io.BytesIO(payload)


def test_upload_reader_accepts_payload_at_limit():
    assert read_upload_limited(Upload(b"12345"), 5) == b"12345"


def test_upload_reader_rejects_payload_over_limit():
    with pytest.raises(HTTPException) as exc:
        read_upload_limited(Upload(b"123456"), 5)
    assert exc.value.status_code == 413


def test_upload_reader_does_not_read_entire_oversized_file():
    upload = Upload(b"x" * 100_000)
    with pytest.raises(HTTPException):
        read_upload_limited(upload, 10)
    assert upload.file.tell() == 11
