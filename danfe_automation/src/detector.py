"""
detector.py
-
Classifies a PDF document as one of the known document types based on keyword
analysis of its raw text content.
"""

import re
import logging
from enum import Enum

logger = logging.getLogger(__name__)

# ------------------------------
# doc type enum
# ------------------------------

class DocumentType(str, Enum):
    DANFE = 'DANFE'
    PIX = 'PIX'
    TED = 'TED'
    DOC = 'DOC'
    RECEIPT = 'COMPROVANTE'
    UNkNOWN = 'DESCONHECIDO'

# ------------------------------
# Keyword fingerprints for each document type
# ------------------------------
# each entry is a list of regex patterns.
# the document type whose patterns score the most matches wins.

_FINGERPRINTS: dict[DocumentType, list[str]] = {
    DocumentType.DANFE: [
        r"DANFE",
        r"Documento auxiliar da Nota Fiscal",
        r"NF-?e",
        r"Chave de acesso",
        r"CFOP",
        r"ICMS",
        r"Série\s*\d+",
        r"Protocolo de Autorização",
    ],
    DocumentType.PIX: [
        r"\bPIX\b",
        r"Chave\s*PIX",
        r"Pagamento\s+PIX",
        r"Transferência\s+PIX",
        r"Comprovante\s+de\s+PIX",
        r"E\d{32}", (formato banco central)
    ],
    DocumentType.TED: [
        r"\bTED\b",
        r"Transferência\s+Eletrônica\s+Disponível",
        r"Comprovante\s+de\s+TED",
        r"ISPB",
    ],
    DocumentType.DOC: [
        r"\bDOC\b",
        r"Documento\s+de\s+Crédito",
        r"Comprovante\s+de\s+DOC",
    ],
    DocumentType.RECEIPT: [
        r"Comprovante\s+de\s+Pagamento",
        r"Boleto\s+Banc[aá]rio",
        r"Linha\s+Digit[aá]vel",
        r"Código\s+de\s+Barras",
        r"Beneficiário",
        r"Sacado",
    ],
}

# ------------------------------
# Public API
# ------------------------------

def detect(text: str) -> DocumentType:
    """
    Classify a document on its raw text

    Args:
        text: Full text extracted from the PDF (all pages joined)

    Returns:
        A DocumentType enum value
    """
    if not text:
        logger.warning("detect() received empty text - returning UNKNOWN")
        return DocumentType.UNkNOWN

    normalized = _normalize(text)
    scores = _score(normalized)

    logger.debug("Document type scores: %s", scores)

    best_type, best_score = max(scores.items(), key=lambda kv: kv[1])

    if best_score == 0:
        logger.info("No fingerprint matched - document classified asUNKNOWN")
        return DocumentType.UNkNOWN
    
    logger.info("Document classified as %s with score %d", best_type, best_score)
    return best_type

# ------------------------------
# Private helpers
# ------------------------------

def _normalize(text: str) -> str:
    """
    Normalize text for matching:
    - Convert to uppercase
    - Collpase multiple whitespace into single space
    """
    text = text.upper()
    text = re.sub(r'\s+', ' ', text)
    return text

def _score(nomalized_text: str) -> dict[DocumentType, int]:
    """
    Count how many fingerprint patterns match the text for each document type.
    Returns a dict mapping DocumentType -> match count.
    """
    scores: dict[DocumentType, int] = {dtype: 0 for dtype in DocumentType}

    for dtype, patterns in _FINGERPRINTS.items():
        for pattern in patterns:
            if re.search(pattern, nomalized_text, re.IGNORECASE):
                scores[dtype] += 1
    return scores