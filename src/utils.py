import hashlib
from pathlib import Path

def calculate_sha256(file_path: Path | str, chunk_size: int = 8192 * 1024) -> str:
    """
    Calculate SHA-256 hash of a file using a buffered approach.
    chunk_size defaults to 8MB for efficient reading of large files
    without exhausting RAM.
    """
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(chunk_size), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def generate_universe_path(metadata) -> Path:
    """
    Resolves the final destination on the NAS using the 
    YYYY-MM-DD_SourceDevice_CleanName standard.
    """
    original_path = Path(metadata.original_path)
    date_str = metadata.creation_date.strftime("%Y-%m-%d")
    
    # Replace spaces with underscores
    safe_device = metadata.source_device.replace(" ", "_")
    
    # Use clean_name if available, otherwise original_path.name
    display_name = getattr(metadata, "clean_name", None) or original_path.name
    
    # Strip leading device name if it is prepended (e.g. CHIRU_receipt.pdf -> receipt.pdf)
    if display_name.startswith(f"{safe_device}_"):
        display_name = display_name[len(safe_device)+1:]
        
    safe_name = display_name.replace(" ", "_")
    
    new_filename = f"{date_str}_{safe_device}_{safe_name}"
    
    # Base path on the NAS
    base_nas = Path("/mnt/nas_data")
    
    # Target directory based on category
    target_dir = base_nas / metadata.category
    
    return target_dir / new_filename
