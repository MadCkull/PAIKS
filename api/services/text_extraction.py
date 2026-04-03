import io
import pathlib
import logging

logger = logging.getLogger(__name__)

def extract_text_from_drive(service, file_id, mime_type):
    """Download a Drive file and return its plain-text content, or None on failure."""
    try:
        if mime_type == "application/vnd.google-apps.document":
            raw = service.files().export(fileId=file_id, mimeType="text/plain").execute()
            return raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else str(raw)

        if mime_type in ("text/plain", "text/csv"):
            from googleapiclient.http import MediaIoBaseDownload
            buf = io.BytesIO()
            dl = MediaIoBaseDownload(buf, service.files().get_media(fileId=file_id))
            done = False
            while not done:
                _, done = dl.next_chunk()
            return buf.getvalue().decode("utf-8", errors="ignore")

        if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            from googleapiclient.http import MediaIoBaseDownload
            import docx as docx_lib
            from lxml import etree
            import zipfile
            buf = io.BytesIO()
            dl = MediaIoBaseDownload(buf, service.files().get_media(fileId=file_id))
            done = False
            while not done:
                _, done = dl.next_chunk()
            buf.seek(0)
            try:
                doc = docx_lib.Document(buf)
                parts = []
                for p in doc.paragraphs:
                    if p.text.strip():
                        parts.append(p.text)
                for table in doc.tables:
                    for row in table.rows:
                        row_text = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                        if row_text:
                            parts.append(" | ".join(row_text))
                for section in doc.sections:
                    for header_p in section.header.paragraphs:
                        if header_p.text.strip():
                            parts.append(header_p.text)
                    for footer_p in section.footer.paragraphs:
                        if footer_p.text.strip():
                            parts.append(footer_p.text)
                if not parts:
                    logger.info("python-docx API found no text for %s, trying raw XML extraction", file_id)
                    buf.seek(0)
                    with zipfile.ZipFile(buf) as zf:
                        for name in zf.namelist():
                            if name.endswith('.xml'):
                                tree = etree.parse(zf.open(name))
                                for t_elem in tree.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'):
                                    if t_elem.text and t_elem.text.strip():
                                        parts.append(t_elem.text)
                return "\n".join(parts) if parts else None
            except Exception as exc:
                logger.warning("python-docx failed for %s: %s", file_id, exc)
                try:
                    buf.seek(0)
                    import zipfile
                    from lxml import etree
                    parts = []
                    with zipfile.ZipFile(buf) as zf:
                        for name in zf.namelist():
                            if name.endswith('.xml'):
                                tree = etree.parse(zf.open(name))
                                for t_elem in tree.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'):
                                    if t_elem.text and t_elem.text.strip():
                                        parts.append(t_elem.text)
                    if parts:
                        return "\n".join(parts)
                except Exception:
                    pass
                return None

        if mime_type == "application/msword":
            try:
                raw = service.files().export(fileId=file_id, mimeType="text/plain").execute()
                return raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else str(raw)
            except Exception:
                logger.warning("Legacy .doc export failed for %s, skipping", file_id)
                return None

    except Exception as exc:
        logger.warning("extract_text failed for %s (%s): %s", file_id, mime_type, exc)
    return None

def extract_text_from_local(filepath: pathlib.Path) -> str | None:
    """Extract plain text from a local file by extension."""
    ext = filepath.suffix.lower()
    try:
        if ext in (".txt", ".md", ".csv"):
            return filepath.read_text(encoding="utf-8", errors="ignore")

        if ext == ".docx":
            import docx as docx_lib
            doc = docx_lib.Document(str(filepath))
            parts = [p.text for p in doc.paragraphs if p.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    row_text = [c.text.strip() for c in row.cells if c.text.strip()]
                    if row_text:
                        parts.append(" | ".join(row_text))
            return "\n".join(parts) if parts else None

        if ext == ".pdf":
            try:
                import pdfplumber
                with pdfplumber.open(str(filepath)) as pdf:
                    pages = [p.extract_text() or "" for p in pdf.pages]
                return "\n".join(pages).strip() or None
            except ImportError:
                pass
            raw = filepath.read_bytes()
            text = raw.decode("latin-1", errors="ignore")
            printable = "".join(c if c.isprintable() or c in "\n\r\t" else " " for c in text)
            return printable.strip() or None

    except Exception as exc:
        logger.warning("local extract failed for %s: %s", filepath.name, exc)
    return None
