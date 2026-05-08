from datetime import datetime
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

class FileMetadata(BaseModel):
    original_path: Path
    file_hash: str = Field(..., description="SHA-256 hash of the file")
    source_device: str
    creation_date: datetime
    category: str
    target_path: Optional[Path] = None
