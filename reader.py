"""
reader.py
--------
Responsible for reading PDF files and extracting raw extt from them.

Supports two extraction strategies:
1. pdfplumber - best for structured PDFs (DANFE invoices, typed receipts).
2. pytesseract - OCR fallback for scanned/image-based PDFs.

The public interface is a single function: extract_text (pdf_path) -> str
"""

import logging
from pathlib import Path
import pdfplumber

logger = logging.getLogger(__name__)

#
# Public API
#

def extract_text(pdf_path: str | Path) -> str:
    """
    Extract and return all text from a PDF file.

    Args:
        pdf_path: Absolute or relative path to the PDF file.

    Returns:
        A single strin containing the concatenated text of all pages.
        Returns an empty string if extraction fails.
    """
    pdf_path = Path(pdf_path)

    # Security: refuse to read files outside the project folder.
    # Resolving first handles both relative paths andn symlinks.
try:
    pdf_path.resolve().relative_to(_PROJECT_ROOT)
except ValueError:
    logger.error(
        "Acesso negado: '%s' esta fora da pasta do projeto ('%s'). "
        "Coloque os PDFs dentro da pasta 'documentos/'.",
        pdf_path,
        _PROJECT_ROOT,
        )
    return ""

if not pdf_path.exists():
    logger.error("File not found: %s", pdf_path)
    return ""

text = _extract_with_pdfplumber(pdf_path)

# If pdfplumber yields very little text, the PDF is likely image-based.
# Fall back to OCR.
if _is_text_too_short(text):
    logger.info(
        "pdfplumber returned little/no text for '%s'. Trying OCR fallback.",
        pdf_path.name,
    )
    text = _extract_with_ocr(pdf_path)

    return text.strip()

#
# Private helpers
#

def _extract_with_pdfplumber(pdf_path: Path) -> str:
    """Use pdfplumberr to extract text from a digital (not-scanned) PDF."""
    pages_text: list[str] = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    pages_text.append(page_text)
    except Exception as exc:
        logger.warning("pdfplumber failed on '%s': %s", pdf_path.name, exc)

    return "\n".join(pages_text)

def _extract_with_ocr(pdf_path: Path) -> str:
    """
    OCR fallback usingi pdf2imaeg + pyytesseract.

    Requires:
        pip install pdf2image pytesseract
        Tesseract-OCR binary installed and on PATH
    """
    try:
        import pytesseract
        from pdf2image import convert_from_path

        images = convert_from_path(str(pdf_path), dpi=300)
        pages_text = [
            # langs='por' improves accuracy for Portuguese documents
            pytesseract.image_to_string(img, lang="por")
            for img in images
        ]
        return "\n".join(pages_text)
    
    except ImportError:
        logger.error(
            "OCR libraries (pdf2image / pytesseract) are not installed. "
        )
        return ""
    except Exception as exc:
        logger.error("OCR failed on '%s': %s", pdf_path.name, exc)
        return ""
    
def _is_text_too_short(text: str, threshold: int = 30) -> bool:
    """
    Return True when extracted text contains fewer characters than 'threshold',
    which typically indicates an image-based (scanneed) pdf
    """
    return len(text.strip()) < threshold