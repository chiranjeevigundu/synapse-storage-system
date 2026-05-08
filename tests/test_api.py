import os
import sys
from pathlib import Path
from fastapi.testclient import TestClient

# Ensure src is in path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Set test environment variables before importing anything
os.environ["API_KEY"] = "test_secret_key"
os.environ["NAS_BASE_PATH"] = str(Path(__file__).parent.parent / "test_nas_data")

from ingest_api import app

client = TestClient(app)

def test_upload_without_api_key():
    response = client.post("/upload", data={"source_device": "TestDevice"})
    # The API correctly returns 401 for unauthorized requests
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API Key"}

def test_upload_with_valid_key():
    # Setup test file
    test_content = b"test file content for api"
    files = {"file": ("testfile.txt", test_content, "text/plain")}
    data = {"source_device": "TestDevice", "category": "00_INGEST/Uncategorized"}
    
    response = client.post(
        "/upload", 
        files=files, 
        data=data,
        headers={"x-api-key": "test_secret_key"}
    )
    
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "success"
    assert "TestDevice_testfile.txt" in res_json["filename"]
    
    # Verify the file was actually created in the dummy ingest path
    ingest_dir = Path(__file__).parent.parent / "test_nas_data" / "00_INGEST"
    uploaded_file = ingest_dir / "TestDevice_testfile.txt"
    assert uploaded_file.exists()
    
    # Validate content
    with open(uploaded_file, "rb") as f:
        assert f.read() == test_content
    
    # Cleanup
    if uploaded_file.exists():
        uploaded_file.unlink()
