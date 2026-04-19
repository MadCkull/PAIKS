import logging
import pathlib
from typing import List, Optional
from llama_index.core.schema import Document
from api.services.text_extraction import extract_text_from_drive, extract_text_from_local

logger = logging.getLogger(__name__)

def is_text_junk(text: str) -> bool:
    """
    Heuristic check to identify useless/garbage text (binary noise, failed extraction).
    Returns True if text is looks like junk, False otherwise.
    """
    if not text or len(text.strip()) < 10:
        return True
    
    # 1. Alphanumeric Ratio: 
    # Garbage binary data converted to text usually has a very low ratio of normal chars.
    alnum_count = sum(1 for c in text if c.isalnum() or c.isspace())
    ratio = alnum_count / len(text)
    
    if ratio < 0.4:  # Less than 40% readable? Likely junk.
        return True
    
    # 2. Extreme Repetition: 
    # Corrupted extractions often produce strings of the same character.
    # Check if a single character makes up more than 70% of a large sample.
    sample = text[:500]
    if len(sample) > 50:
        most_common_freq = max([sample.count(c) for c in set(sample)]) / len(sample)
        if most_common_freq > 0.7:
            return True
            
    return False

def parse_cloud_file(service, file_info: dict) -> Optional[Document]:
    """
    Parses a single cloud file into a LlamaIndex Document with strict metadata for citations.
    file_info must contain 'id', 'name', 'mime', 'link', 'modified'
    """
    fid = file_info.get("id")
    fname = file_info.get("name", "Unknown Cloud Document")
    mime = file_info.get("mime", "")
    try:
        text = extract_text_from_drive(service, fid, mime)
        if not text or is_text_junk(text):
            if text: logger.warning(f"Skipping cloud document {fname}: Detected as junk data.")
            return None
            
        doc = Document(
            text=text,
            metadata={
                "file_id": fid,
                "file_name": fname,
                "source": "cloud",
                "mime_type": mime,
                "web_view_link": file_info.get("link", ""),
                "modified_time": file_info.get("modified", ""), # Should already be ISO from Drive API or str(doc.last_modified)
                "is_summary": False,
                "chunk_index": 0,
                "total_chunks": 0,
                "section_header": "",
            },
            excluded_llm_metadata_keys=["file_id", "source", "mime_type", "web_view_link", "is_summary", "chunk_index", "total_chunks"],
            excluded_embed_metadata_keys=["file_id", "web_view_link", "modified_time", "is_summary", "chunk_index", "total_chunks"],
        )
        return doc
    except Exception as e:
        logger.error(f"Failed to parse cloud doc {fname}: {e}")
        return None

def parse_local_file(file_info: dict) -> Optional[Document]:
    """
    Parses a single local file into a LlamaIndex Document with strict metadata for citations.
    file_info must contain 'id', 'name', 'mime', 'local_path', 'modified'
    """
    fid = file_info.get("id")
    fname = file_info.get("name", "Unknown Local Document")
    local_path = file_info.get("local_path", "")
    
    try:
        path_obj = pathlib.Path(local_path)
        if not path_obj.exists():
            return None
            
        text = extract_text_from_local(path_obj)
        if not text or is_text_junk(text):
            if text: logger.warning(f"Skipping local document {fname}: Detected as junk data.")
            return None
            
        doc = Document(
            text=text,
            metadata={
                "file_id": fid,
                "file_name": fname,
                "source": "local",
                "local_path": local_path,
                "modified_time": file_info.get("modified", ""),
                "is_summary": False,
                "chunk_index": 0,
                "total_chunks": 0,
                "section_header": "",
            },
            excluded_llm_metadata_keys=["file_id", "source", "local_path", "is_summary", "chunk_index", "total_chunks"],
            excluded_embed_metadata_keys=["file_id", "local_path", "modified_time", "is_summary", "chunk_index", "total_chunks"],
        )
        return doc
    except Exception as e:
        logger.error(f"Failed to parse local doc {fname}: {e}")
        return None
