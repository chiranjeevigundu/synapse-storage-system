import os
import json
import shutil
from pathlib import Path
from fastapi import FastAPI, UploadFile, Form, File, HTTPException, Depends, Header
from fastapi.responses import Response
from pydantic import BaseModel
from loguru import logger
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter
from config import settings

app = FastAPI(title="Universe Ingest API")

BASE_INGEST_PATH = Path(settings.NAS_BASE_PATH) / "00_INGEST"
EXPECTED_API_KEY = settings.API_KEY

# Metrics
INGEST_COUNTER = Counter('total_files_ingested', 'Total number of files ingested via API')
SOURCE_DEVICE_COUNTER = Counter('files_by_source_device', 'Files ingested by source device', ['device'])

def verify_api_key(x_api_key: str = Header(None)):
    if x_api_key != EXPECTED_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

LEDGER_PATH = Path(__file__).parent / "ledger.json"

@app.get("/review", dependencies=[Depends(verify_api_key)])
async def get_review_ledger():
    if not LEDGER_PATH.exists():
        return {"entries": []}
    try:
        with open(LEDGER_PATH, "r") as f:
            data = json.load(f)
            entries = data.get("entries", {})
            sorted_entries = sorted(entries.values(), key=lambda x: x.get("timestamp", ""), reverse=True)[:20]
            return {"entries": sorted_entries}
    except Exception as e:
        logger.error(f"Failed to read ledger: {e}")
        raise HTTPException(status_code=500, detail="Ledger read error")

@app.post("/upload", dependencies=[Depends(verify_api_key)])
async def upload_file(
    file: UploadFile = File(...),
    source_device: str = Form(...),
    category: str = Form("00_INGEST/Uncategorized")
):
    if not BASE_INGEST_PATH.exists():
        BASE_INGEST_PATH.mkdir(parents=True, exist_ok=True)
        
    safe_device = source_device.replace(" ", "_")
    safe_name = file.filename.replace(" ", "_")
    
    final_filename = f"{safe_device}_{safe_name}"
    file_path = BASE_INGEST_PATH / final_filename
    
    logger.info(f"Receiving file from {source_device}: {file_path}")
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        raise HTTPException(status_code=500, detail="File save error")
        
    INGEST_COUNTER.inc()
    SOURCE_DEVICE_COUNTER.labels(device=safe_device).inc()
        
    logger.success(f"File {final_filename} successfully ingested via API.")
    return {"status": "success", "filename": final_filename, "path": str(file_path)}
