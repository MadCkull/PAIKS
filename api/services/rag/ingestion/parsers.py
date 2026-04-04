import logging
import pathlib
from typing import List, Optional
from llama_index.core.schema import Document
from api.services.text_extraction import extract_text_from_drive, extract_text_from_local

logger = logging.getLogger(__name__)

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
        if not text or not text.strip():
            return None
            
        doc = Document(
            text=text,
            metadata={
                "file_id": fid,
                "file_name": fname,
                "source": "cloud",
                "mime_type": mime,
                "web_view_link": file_info.get("link", ""),
                "modified_time": file_info.get("modified", ""),
            },
            excluded_llm_metadata_keys=["file_id", "source", "mime_type", "web_view_link"],
            excluded_embed_metadata_keys=["file_id", "web_view_link", "modified_time"],
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
        if not text or not text.strip():
            return None
            
        doc = Document(
            text=text,
            metadata={
                "file_id": fid,
                "file_name": fname,
                "source": "local",
                "local_path": local_path,
                "modified_time": file_info.get("modified", ""),
            },
            excluded_llm_metadata_keys=["file_id", "source", "local_path"],
            excluded_embed_metadata_keys=["file_id", "local_path", "modified_time"],
        )
        return doc
    except Exception as e:
        logger.error(f"Failed to parse local doc {fname}: {e}")
        return None
