"""Deterministic, bounded document parsers introduced step by step in M2."""

from app.services.documents.parsers.base import (
    DocumentEncryptedError,
    DocumentEnhancementError,
    DocumentLimitError,
    DocumentParseError,
    DocumentQualityRejected,
    ParserWarning,
    SourceLocator,
)
from app.services.documents.parsers.csv import CsvParser, CsvParseResult, CsvRow
from app.services.documents.parsers.docx import (
    DocxBlock,
    DocxImageOcrSegment,
    DocxParagraphBlock,
    DocxParagraphSegment,
    DocxParser,
    DocxParseResult,
    DocxRegionTextBlock,
    DocxTableBlock,
    DocxTableCell,
    DocxTableRow,
    DocxTextSegment,
)
from app.services.documents.parsers.docx_ocr import (
    DocxImageOcrOutput,
    DocxImageOcrProvider,
    LocalRapidOcrProvider,
)
from app.services.documents.parsers.pdf import (
    PdfBoundingBox,
    PdfHeadingHint,
    PdfLayoutLine,
    PdfPageText,
    PdfParser,
    PdfParseResult,
)
from app.services.documents.parsers.xlsx import (
    XlsxCell,
    XlsxParser,
    XlsxParseResult,
    XlsxRow,
    XlsxSheet,
)

__all__ = [
    "CsvParseResult",
    "CsvParser",
    "CsvRow",
    "DocumentEncryptedError",
    "DocumentEnhancementError",
    "DocumentLimitError",
    "DocumentParseError",
    "DocumentQualityRejected",
    "DocxBlock",
    "DocxImageOcrOutput",
    "DocxImageOcrProvider",
    "DocxImageOcrSegment",
    "DocxParagraphBlock",
    "DocxParagraphSegment",
    "DocxParseResult",
    "DocxParser",
    "DocxRegionTextBlock",
    "DocxTableBlock",
    "DocxTableCell",
    "DocxTableRow",
    "DocxTextSegment",
    "LocalRapidOcrProvider",
    "ParserWarning",
    "PdfBoundingBox",
    "PdfHeadingHint",
    "PdfLayoutLine",
    "PdfPageText",
    "PdfParseResult",
    "PdfParser",
    "SourceLocator",
    "XlsxCell",
    "XlsxParseResult",
    "XlsxParser",
    "XlsxRow",
    "XlsxSheet",
]
