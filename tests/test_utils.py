import os
import tempfile
import hashlib
from pathlib import Path
from datetime import datetime
import pytest
import sys

# Ensure src is in path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from utils import calculate_sha256, generate_universe_path
from models import FileMetadata

def test_calculate_sha256():
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"hello world test file")
        temp_path = f.name
        
    try:
        # Calculate expected hash manually
        expected_hash = hashlib.sha256(b"hello world test file").hexdigest()
        
        # Calculate using our high-performance utility
        actual_hash = calculate_sha256(Path(temp_path))
        
        assert actual_hash == expected_hash
    finally:
        os.unlink(temp_path)

def test_generate_universe_path():
    dt = datetime(2026, 5, 7, 12, 0, 0)
    metadata = FileMetadata(
        original_path=Path("/tmp/test_image.jpg"),
        file_hash="dummyhash",
        source_device="iPhone14",
        creation_date=dt,
        category="03_PERSONAL/Mobile_Backups"
    )
    
    # Path should format correctly depending on OS separator
    expected_path_str = f"03_PERSONAL{os.sep}Mobile_Backups{os.sep}2026-05-07_iPhone14_test_image.jpg"
    
    actual_path = generate_universe_path(metadata)
    
    # We check if the dynamically generated expected path segment is in the final absolute path
    assert expected_path_str in str(actual_path)
