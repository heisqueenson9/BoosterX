import os
import secrets
import hashlib
from io import BytesIO
from PIL import Image
from flask import current_app
from backend.app.models import Payment

ALLOWED_MAGIC_BYTES = {
    b"\x89PNG\r\n\x1a\n": "png",
    b"\xff\xd8\xff": "jpeg",
    b"RIFF": "webp"
}

MAX_PIXELS = 25 * 1024 * 1024  # 25 Megapixels limit to prevent decompression bombs

class UploadError(ValueError):
    """Uploaded image validation error."""

def validate_and_save_screenshot(payment: Payment, file_storage) -> str:
    """
    Validates magic bytes, file size, pixel limit, re-encodes image to WEBP using Pillow,
    strips EXIF and payloads, calculates SHA256 file_hash, and saves to UPLOAD_FOLDER.
    """
    if payment.attempt_count >= 5:
        raise UploadError("Maximum upload attempts reached for this payment.")

    file_bytes = file_storage.read()
    if not file_bytes:
        raise UploadError("File is empty.")

    if len(file_bytes) > current_app.config["MAX_CONTENT_LENGTH"]:
        raise UploadError("File size exceeds 10 MB limit.")

    # Reject PDF magic bytes explicitly
    if file_bytes.startswith(b"%PDF"):
        raise UploadError("PDF files are not accepted. Please upload a PNG, JPEG, or WEBP screenshot.")

    # Validate Magic Bytes
    valid_format = False
    for magic, fmt in ALLOWED_MAGIC_BYTES.items():
        if file_bytes.startswith(magic):
            valid_format = True
            break
        # WEBP check RIFF ... WEBP
        if file_bytes.startswith(b"RIFF") and b"WEBP" in file_bytes[:16]:
            valid_format = True
            break

    if not valid_format:
        raise UploadError("Unsupported image format. Allowed formats: PNG, JPEG, WEBP.")

    try:
        img = Image.open(BytesIO(file_bytes))
        img.verify()  # Verify image integrity
        img = Image.open(BytesIO(file_bytes))  # Re-open after verify
    except Exception as exc:
        raise UploadError("Corrupted or invalid image file.") from exc

    # Check pixel count limit
    width, height = img.size
    if width * height > MAX_PIXELS:
        raise UploadError("Image resolution exceeds maximum allowed limit.")

    # Calculate file hash for duplicate screenshot detection
    payment.file_hash = hashlib.sha256(file_bytes).hexdigest()

    # Convert to RGB/RGBA and re-encode to WEBP to strip EXIF and hidden payloads
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    random_name = f"{secrets.token_hex(16)}.webp"
    target_path = os.path.join(current_app.config["UPLOAD_FOLDER"], random_name)

    img.save(target_path, "WEBP", quality=85)
    return random_name
