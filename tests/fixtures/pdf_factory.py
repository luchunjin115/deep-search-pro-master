"""Small synthetic PDFs for parser tests; no production or external data."""

from __future__ import annotations

import io

import pymupdf
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.lib.utils import ImageReader  # type: ignore[import-untyped]
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]


def make_text_pdf(*, include_empty_page: bool = True) -> bytes:
    """Create two text pages with font hierarchy and one optional blank page."""

    output = io.BytesIO()
    canvas = Canvas(output, pagesize=A4, pageCompression=1)
    _width, height = A4
    canvas.setTitle("M2-07 Synthetic Product Manual")
    canvas.setAuthor("Deep Search Pro synthetic test fixture")

    canvas.setFont("Helvetica-Bold", 20)
    canvas.drawString(54, height - 70, "Synthetic Product Manual")
    canvas.setFont("Helvetica", 11)
    canvas.drawString(54, height - 110, "Model: SYNTH-LAMP-01")
    canvas.drawString(
        54, height - 130, "This page contains embedded text for parser verification."
    )
    canvas.drawString(
        54, height - 150, "All names and values are synthetic demonstration data."
    )
    canvas.showPage()

    canvas.setFont("Helvetica-Bold", 16)
    canvas.drawString(54, height - 70, "Safety Requirements")
    canvas.setFont("Helvetica", 11)
    canvas.drawString(54, height - 110, "Disconnect power before maintenance.")
    canvas.drawString(54, height - 130, "Keep the product away from standing water.")
    canvas.drawString(54, height - 150, "Retain this manual for future reference.")
    canvas.showPage()

    if include_empty_page:
        canvas.showPage()
    canvas.save()
    return output.getvalue()


def make_scanned_image_pdf() -> bytes:
    """Create one image-only PDF page with no embedded text layer."""

    image = Image.new("RGB", (800, 1000), "white")
    drawing = ImageDraw.Draw(image)
    drawing.rectangle((60, 60, 740, 940), outline="black", width=4)
    drawing.text((120, 180), "SCANNED SYNTHETIC PAGE", fill="black")
    drawing.text((120, 240), "No embedded OCR text layer", fill="black")
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    image_bytes.seek(0)

    output = io.BytesIO()
    canvas = Canvas(output, pagesize=A4, pageCompression=1)
    width, height = A4
    canvas.drawImage(
        ImageReader(image_bytes),
        36,
        48,
        width=width - 72,
        height=height - 96,
        preserveAspectRatio=True,
        anchor="c",
    )
    canvas.save()
    return output.getvalue()


def make_low_text_pdf() -> bytes:
    """Create one text-layer page below the configured low-text threshold."""

    output = io.BytesIO()
    canvas = Canvas(output, pagesize=A4, pageCompression=1)
    canvas.setFont("Helvetica", 11)
    canvas.drawString(54, A4[1] - 70, "OK")
    canvas.save()
    return output.getvalue()


def make_encrypted_pdf() -> bytes:
    """Encrypt the synthetic text PDF without exposing a usable parser password."""

    plain = make_text_pdf(include_empty_page=False)
    output = io.BytesIO()
    document = pymupdf.open(  # type: ignore[no-untyped-call]
        stream=plain,
        filetype="pdf",
    )
    try:
        document.save(  # type: ignore[no-untyped-call]
            output,
            encryption=pymupdf.PDF_ENCRYPT_AES_256,  # type: ignore[attr-defined]
            owner_pw="synthetic-owner-only",
            user_pw="synthetic-user-only",
        )
    finally:
        document.close()  # type: ignore[no-untyped-call]
    return output.getvalue()
