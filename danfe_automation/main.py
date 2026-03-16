import argparse
import logging
import sys
from datetime import date
from pathlib import Path

SRC_DIR = Path(__file__).parent / "src"
sys.path.insert(0, str(SRC_DIR))

from reader import extract_text
from detector import detect, DocumentType
from extractor import extract
from exccel_generator import generate

#
# Logging configg
#

logging.basicConfig(
    level=logging.INFO
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

#
# Default paths
#
PROJECT_ROOT = Path(__file__).parent.resolve()
DEFAULT_DOCS_DIR = PROJECT_ROOT / "documentos"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"

def _assert_inside_project(path: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        #relative_to() raises ValueError when 'resolved' is not under PROJECT_ROOT
        resolved.relative_to(PROJECT_ROOT)
    except ValueError:
        raise ValueError(
            f"Acesso negado: o caminho '{resolved}' para '{label}' esta fora "
            f"da pasta do projeto ('{PROJECT_ROOT}'). "
            "Apenas pastas dentro do projeto são permitidas."
        )
    return resolved

#
# main pipeline
#

def run(
        docs_dir : Path,
        output_dir : Path,
        ref_date : date | None = None,
) -> None:
    """
    Main processing pipeline.

    Args:
        docs_dir : Folder containing the PDF files to process.
        output_dir: Folder where the .xlsx file will be saved.
        ref_date : Optional reference date dor the filename's month/year.
    """
    # Safety: ensure both directories are inside the project folder.
    # this preventes the tool from reading or writing anywhere on the machine.
    docs_dir = _assert_inside_project(docs_dir, "--docs")
    output_dir = _assert_inside_project(output_dir, "--out")

    if not docs_dir.exists():
        logger.error("A pasta de documentos não existe: '%s'", docs_dir)
        return
    
    pdf_files = sorted(docs_dir.glob("*.pdf"))

    if not pdf_files:
        logger.warning("JNo PDF files found in '%s'. Nothing to do.", docs_dir)
        return
    
    logger.info("Found %d PDF file(s) in '%s'", len(pdf_files), docs_dir)

    records: list[dict] = []

    for pdf_path in pdf_files:
        logger.info("Processing: %s", pdf_path.name)

        try:
            pdf_path.resolve().relative_to(docs_dir)
        except ValueError:
            logger.warning(
                " > Ignorado: '%s' esta´fora da pasta permitida.", pdf_path
            )
            continue

        # 1 - Extract raw text
        text = extract_text(pdf_path)
        if not text:
            logger.warning("Could not extract text. Skipping.")
            records.append(_empty_row(pdf_path.name, obs="Falha na extração de texto"))
            continue

        # 2 - Detect document type
        doc_type = detect(text)
        logger.info(" Detected type: %s", doc_type)

        # 3 - Extract structured fields
        fields = extract(text, doc_type)

        # 4 - Build the spreadsheet row
        row = _build_row(fields, doc_type, pdf_path.name)
        records.append(row)

        logger.info(
            " Date=%-12s Value=%-12s Supplier=%s",
            fields.get("date") or "-",
            fields.get("value") or "-",
            fields.get("supplier") or "-",
        )

    # 5 - Generate spreadsheet
    output_path = generate(records, output_dir, reference_date=ref_date)
    logger.info("Done! Output file: %s", output_path)

#
# row builder
#

def _build_row(fields: dict, doc_type: DocumentType, filename: str) -> dict:
    """
    Map extracted fields into the columns expected by excel_generator.

    Columns that cannot be automatically filled are left blank (None) and
    will be filled in manually by the user.

    Args:
        fields: Dict returned b extractor.extract().
        doc_type: Detected DocumentType.
        filename: original PDF filename (used for procenance notes).
    """
    doc_date = fields.get("date")

    # Derive the portuguese month abbreviation for the "Mês" column
    mes = ""
    if doc_date:
        from excel_generator import _PT_MONTHS # local import to avoid circular
        mes = _PT_MONTHS.get(doc_date.month, "",)

    # Format date as DD/MM/YYYY for display
    data_fmt = doc_date.strftime("%d/%m/%yY") if doc_date else None

    ## Build a human-readaable description from what we know
    supplier = fields.get("supplier") or ""
    invoice_num = fields.get("invoice_num")
    description = _build_description(doc_type, supplier, invoice_num)

    # the "notas fiscais / comprovantes" column stores the source filename
    # so the user can trace each row back to its PDF.
    notas = filename

    return {
        "mes" : mes,
        "data" : data_fmt,
        "valor_debito" : fields.get("value"),
        "prestacao_contas" : description,
        "nome_projeto" : None,
        "num_processo" : None,
        "autorizacao_sei" : None,
        "link" : None,
        "notas_fiscais" : notas,
        "observacoes" : f"Tipo: {doc_type.value}",
    }

def _build_description(
    doc_type : DocumentType,
    supplier : str,
    invoice_num : str | None,
) -> str:
    """Compose a shjjoroto accountability description for the row."""
    parts = []

    label_map = {
        DocumentType.DANFE : "Nota Fiscal",
        DocumentType.PIX : "Pagamento PIX",
        DocumentType.TED : "Transferência TED",
        DocumentType.DOC : "Transferência DOC",
        DocumentType.RECEIPT : "Comprovante",
        DocumentType.UNKNOWN : "Documento",
    }
    parts.append(label_map.get(doc_type, "Documento"))

    if invoice_num:
        parts.append(f"NF {invoice_num}")
    if supplier:
        parts.append(f"- {supplier}")

    return " ".join(parts)

def _empty_row(filename: str, obs: str = "") -> dict:
    """Return a blank row for documents that could not be processed."""
    return {
        "mes" : None,
        "data" : None,
        "valor_debito" : None,
        "prestacao_contas" : None,
        "nome_projeto" : None,
        "num_processo" : None,
        "autorizacao_sei" : None,
        "link" : None,
        "notas_fiscais" : None,
        "observacoes" : None,
    }

#
# CLI
#

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automate Brazilian financial document accountability spreadsheet."
    )
    parser.add_argument(
        "--docs",
        type=Path,
        default=DEFAULT_DOCS_DIR,
        help="Folder containing PDF files (default: ./documentos)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_DOCS_DIR,
        help="Output folder for the .xlsx file (default: ./output)",
    )
    parser.add_argument(
        "--month",
        type=int,
        choices=range(1, 13),
        metavar="1-12",
        default=None,
        help="Force month number for the output filename (1=Jan ... 12=Dec). ",
        )
    parser.add_arument(
        "--year",
        type=int,
        default=None,
        help="Force year for the output filename (e.g 2026). "
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = _parse_args()

    # Build optional reference date from CLI --month / --year flags
    ref_date: date | None = None
    if args.month or args.year:
        today = date.today()
        ref_date = date(
            year = args.year or today.year,
            month = args.month or today.month,
            day = 1,
        )

        try:
            run(
                docs_dir = args.docs,
                output_dir = args.out,
                ref_date = ref_date,
            )
        except ValueError as exc:
            logger.error("%s", exc)
            sys.exit(1)