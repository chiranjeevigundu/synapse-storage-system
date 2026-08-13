import os
import json
import time
from loguru import logger
from PIL import Image
from llmkit.parse import ParseError, extract_pdf_text as _extract_pdf_text, parse_json_response
from config import settings

# Every classification says how it was reached. Without this the caller cannot tell a
# real model result from the filename-substring fallback, and `main.py` was counting
# both as AI categorisations — so Prometheus reported healthy AI classification while
# every file was actually being sorted by whether its name contained "receipt".
METHOD_MODEL = "model"
METHOD_HEURISTIC = "heuristic"
METHOD_MOCK = "mock"

DEFAULT_CATEGORY = "03_PERSONAL/Archives"


def _classification(category: str, clean_filename: str, method: str) -> dict:
    """Build a result, defaulting a category that does not look like a taxonomy path.

    The category check was written out three times with the same two conditions; a
    model returning prose instead of a path would otherwise become a directory name.
    """
    if not category or "/" not in category or "_" not in category:
        if method == METHOD_MODEL:
            logger.warning(f"Model returned an unusable category {category!r}; using default")
        category = DEFAULT_CATEGORY
    return {"category": category, "clean_filename": clean_filename, "method": method}


class VisionClassifier:
    def __init__(self):
        self.use_local_llm = settings.USE_LOCAL_LLM
        self.ollama_url = settings.OLLAMA_URL
        self.ollama_model = settings.OLLAMA_MODEL
        self.mock_mode = False

        if self.use_local_llm:
            logger.info(f"VisionClassifier: Local LLM Mode active using {self.ollama_model} at {self.ollama_url}")
            self.ensure_ollama_model()
        else:
            api_key = settings.GEMINI_API_KEY
            self.mock_mode = not api_key
            if self.mock_mode:
                logger.warning("GEMINI_API_KEY not found. VisionClassifier running in MOCK mode.")
            else:
                try:
                    import google.generativeai as genai
                    genai.configure(api_key=api_key)
                    self.model = genai.GenerativeModel('gemini-flash-latest')
                except ImportError:
                    logger.error("google.generativeai module missing. Defaulting to MOCK mode.")
                    self.mock_mode = True

        self.schema_prompt = """
        You are an enterprise data librarian. Analyze this document and classify it into one of these category paths:
        - 01_PROFESSIONAL/Projects
        - 01_PROFESSIONAL/Research
        - 01_PROFESSIONAL/Deployments
        - 01_PROFESSIONAL/Documentation
        - 02_TECHNICAL_HOMELAB/Network_Architecture
        - 02_TECHNICAL_HOMELAB/Hardware_Configs
        - 02_TECHNICAL_HOMELAB/Docker_Stacks
        - 02_TECHNICAL_HOMELAB/MCP_Source_Code
        - 03_PERSONAL/Mobile_Backups
        - 03_PERSONAL/Media_Archives
        - 03_PERSONAL/Archives
        - 04_FINANCIAL/Tax_Records
        - 04_FINANCIAL/Invoices_Receipts
        - 04_FINANCIAL/Legal_Documents

        Also, generate a clean, descriptive, and standardized filename for this document based on its contents.

        Return a JSON object with:
        {
          "category": "string (the selected category path)",
          "clean_filename": "string (the new descriptive filename with the correct extension)"
        }
        """

    def ensure_ollama_model(self):
        """Verify model presence in Ollama; pull it if missing."""
        import httpx
        retries = 15
        connected = False
        for i in range(retries):
            try:
                resp = httpx.get(f"{self.ollama_url}/api/tags", timeout=5.0)
                if resp.status_code == 200:
                    connected = True
                    break
            except Exception as e:
                logger.warning(f"Waiting for Ollama service connection... (attempt {i+1}/{retries}): {e}")
                time.sleep(3)

        if not connected:
            logger.error("Could not connect to Ollama. Curation fallback will be used.")
            return

        try:
            models_list = resp.json().get("models", [])
            models = [m["name"] for m in models_list]
            model_name = self.ollama_model
            target_model = model_name if ":" in model_name else f"{model_name}:latest"
            
            model_exists = False
            for m in models:
                if m == target_model or m.split(":")[0] == target_model.split(":")[0]:
                    model_exists = True
                    break

            if not model_exists:
                logger.info(f"Ollama model '{target_model}' not found. Pulling model (this may take a few minutes)...")
                pull_resp = httpx.post(f"{self.ollama_url}/api/pull", json={"name": target_model}, timeout=None)
                if pull_resp.status_code == 200:
                    logger.success(f"Model '{target_model}' successfully pulled.")
                else:
                    logger.error(f"Failed to pull model: {pull_resp.text}")
            else:
                logger.info(f"Ollama model '{target_model}' is already available.")
        except Exception as e:
            logger.error(f"Error checking/pulling Ollama model: {e}")

    def extract_pdf_text(self, file_path: str) -> str:
        """First three pages of a PDF, or "" if it cannot be read.

        Delegates to llmkit. Callers here treat empty as "fall back to the heuristic",
        so the raising interface is adapted rather than propagated — but the reason it
        raises upstream matters: the other copy of this helper returned
        "[PDF parsing failed: ...]" as the text, which a caller cannot distinguish
        from a document that says that.
        """
        try:
            return _extract_pdf_text(file_path, max_pages=3)
        except ParseError as e:
            logger.error(f"Error extracting PDF text from {file_path}: {e}")
            return ""

    def clean_json_text(self, text: str) -> str:
        """Kept for backwards compatibility; llmkit.parse does the work now.

        This implementation was the correct one of the two that existed — it stripped
        leading whitespace before testing for the fence, which the copy in
        aadyon-assist did not. Centralising it is what stops the two from drifting
        apart again.
        """
        from llmkit.parse import strip_json_fences

        return strip_json_fences(text)

    def classify_local_llm(self, file_path: str) -> dict:
        """Classify documents using local Ollama model (Gemma 4 multimodal-capable)."""
        import httpx
        import base64
        ext = os.path.splitext(file_path)[1].lower()
        image_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

        prompt = f"""
        {self.schema_prompt}

        Response must be JSON format only.
        """

        # --- Image path: pass image directly to the multimodal model ---
        if ext in image_exts:
            logger.info(f"Sending image to multimodal Ollama model: {file_path}")
            try:
                with open(file_path, "rb") as f:
                    image_b64 = base64.b64encode(f.read()).decode("utf-8")
                resp = httpx.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.ollama_model,
                        "prompt": prompt,
                        "images": [image_b64],
                        "format": "json",
                        "stream": False
                    },
                    timeout=60.0
                )
                if resp.status_code == 200:
                    res_json = resp.json()
                    response_text = res_json.get("response", "")
                    res = parse_json_response(response_text)
                    result = _classification(
                        res.get("category", DEFAULT_CATEGORY),
                        res.get("clean_filename", os.path.basename(file_path)),
                        METHOD_MODEL,
                    )
                    logger.success(
                        f"Model image classification: {result['category']} -> {result['clean_filename']}"
                    )
                    return result
                else:
                    logger.error(f"Ollama image API returned status {resp.status_code}: {resp.text}")
            except Exception as e:
                logger.error(f"Error during multimodal image classification: {e}")
            return self.fallback_heuristic(file_path)

        # --- PDF path: extract text and send to model ---
        if ext != ".pdf":
            logger.info(f"Non-PDF/image file: using fallback heuristic for {file_path}")
            return self.fallback_heuristic(file_path)

        text = self.extract_pdf_text(file_path)
        if not text:
            logger.warning(f"No text extracted from PDF {file_path}. Using fallback heuristic.")
            return self.fallback_heuristic(file_path)

        truncated_text = text[:4000]
        
        text_prompt = f"""
        {self.schema_prompt}

        Document Content to Analyze:
        ---
        {truncated_text}
        ---

        Response must be JSON format only.
        """

        try:
            resp = httpx.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": text_prompt,
                    "format": "json",
                    "stream": False
                },
                timeout=60.0
            )
            if resp.status_code == 200:
                res_json = resp.json()
                res = parse_json_response(res_json.get("response", ""))
                return _classification(
                    res.get("category", DEFAULT_CATEGORY),
                    res.get("clean_filename", os.path.basename(file_path)),
                    METHOD_MODEL,
                )
            else:
                logger.error(f"Ollama API returned status {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"Error executing local LLM classification: {e}")

        return self.fallback_heuristic(file_path)

    def fallback_heuristic(self, file_path: str, method: str = METHOD_HEURISTIC) -> dict:
        """Filename substring matching. Not AI, and the result says so.

        Reached whenever the model path fails — an unreachable Ollama, a pull that did
        not complete, a response that will not parse. Those are all silent from the
        outside, which is exactly why the returned `method` matters: it is the only
        thing that distinguishes a working classifier from one that has quietly
        degraded to matching filenames.
        """
        name = os.path.basename(file_path).lower()
        base = os.path.basename(file_path)
        if "receipt" in name or "invoice" in name:
            return _classification("04_FINANCIAL/Invoices_Receipts", base, method)
        elif "w2" in name or "tax" in name or "sodexo" in name:
            return _classification("04_FINANCIAL/Tax_Records", base, method)
        elif "offer_letter" in name or "contract" in name or "employment" in name:
            return _classification("01_PROFESSIONAL/Documentation", base, method)
        return _classification(DEFAULT_CATEGORY, base, method)

    def classify_document(self, file_path: str) -> dict:
        """Classifies any document (PDF or Image) and generates a clean filename."""
        if self.use_local_llm:
            return self.classify_local_llm(file_path)

        if self.mock_mode:
            return self.fallback_heuristic(file_path, method=METHOD_MOCK)
            
        try:
            import google.generativeai as genai
            logger.info(f"Uploading file to Gemini API: {file_path}")
            uploaded_file = genai.upload_file(file_path)
            
            logger.info(f"Generating content for: {file_path}")
            response = self.model.generate_content(
                [self.schema_prompt, uploaded_file],
                generation_config={"response_mime_type": "application/json"}
            )
            
            try:
                uploaded_file.delete()
            except Exception as e:
                logger.error(f"Failed to delete uploaded temp file: {e}")
                
            res = parse_json_response(response.text)
            return _classification(
                res.get("category", DEFAULT_CATEGORY),
                res.get("clean_filename", os.path.basename(file_path)),
                METHOD_MODEL,
            )
            
        except Exception as e:
            logger.error(f"Error calling Gemini API for classification: {e}")
            return self.fallback_heuristic(file_path)

    def classify_image(self, file_path: str) -> str:
        """Backwards compatibility helper."""
        res = self.classify_document(file_path)
        return res["category"]
