"""Deterministic, bounded document parsers introduced step by step in M2."""

from app.services.documents.parsers.base import (
    DocumentEncryptedError,
    DocumentEnhancementError,
    DocumentLimitError,
    DocumentParseError,
    ParserWarning,
    SourceLocator,
)
from app.services.documents.parsers.csv import CsvParser, CsvParseResult, CsvRow
from app.services.documents.parsers.docx import (
    DocxBlock,
    DocxParagraphBlock,
    DocxParser,
    DocxParseResult,
    DocxTableBlock,
    DocxTableCell,
    DocxTableRow,
)
from app.services.documents.parsers.pdf import (
    PdfHeadingHint,
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
    "DocxBlock",
    "DocxParagraphBlock",
    "DocxParseResult",
    "DocxParser",
    "DocxTableBlock",
    "DocxTableCell",
    "DocxTableRow",
    "ParserWarning",
    "PdfHeadingHint",
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
