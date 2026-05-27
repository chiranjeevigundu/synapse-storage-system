import os
import json
import time
from loguru import logger
from PIL import Image
from config import settings

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
        retries = 5
        connected = False
        for i in range(retries):
            try:
                resp = httpx.get(f"{self.ollama_url}/api/tags", timeout=5.0)
                if resp.status_code == 200:
                    connected = True
                    break
            except Exception as e:
                logger.warning(f"Waiting for Ollama service connection... (attempt {i+1}/{retries}): {e}")
                time.sleep(2)

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
        """Extract up to first 3 pages of text from PDF using pypdf."""
        try:
            import pypdf
            reader = pypdf.PdfReader(file_path)
            text_parts = []
            max_pages = min(len(reader.pages), 3)
            for i in range(max_pages):
                page_text = reader.pages[i].extract_text()
                if page_text:
                    text_parts.append(page_text)
            return "\n".join(text_parts).strip()
        except Exception as e:
            logger.error(f"Error extracting PDF text from {file_path}: {e}")
            return ""

    def clean_json_text(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    def classify_local_llm(self, file_path: str) -> dict:
        """Classify PDF using local Ollama model."""
        import httpx
        ext = os.path.splitext(file_path)[1].lower()
        if ext != ".pdf":
            logger.info(f"Local LLM text-only: Fallback heuristic for non-PDF: {file_path}")
            return self.fallback_heuristic(file_path)

        text = self.extract_pdf_text(file_path)
        if not text:
            logger.warning(f"No text extracted from PDF {file_path}. Using fallback heuristic.")
            return self.fallback_heuristic(file_path)

        truncated_text = text[:4000]
        
        prompt = f"""
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
                    "prompt": prompt,
                    "format": "json",
                    "stream": False
                },
                timeout=30.0
            )
            if resp.status_code == 200:
                res_json = resp.json()
                response_text = res_json.get("response", "")
                cleaned = self.clean_json_text(response_text)
                res = json.loads(cleaned)
                category = res.get("category", "03_PERSONAL/Archives")
                clean_filename = res.get("clean_filename", os.path.basename(file_path))
                
                if "/" not in category or "_" not in category:
                    category = "03_PERSONAL/Archives"
                return {"category": category, "clean_filename": clean_filename}
            else:
                logger.error(f"Ollama API returned status {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"Error executing local LLM classification: {e}")

        return self.fallback_heuristic(file_path)

    def fallback_heuristic(self, file_path: str) -> dict:
        name = os.path.basename(file_path).lower()
        if "receipt" in name or "invoice" in name:
            return {"category": "04_FINANCIAL/Invoices_Receipts", "clean_filename": os.path.basename(file_path)}
        elif "w2" in name or "tax" in name or "sodexo" in name:
            return {"category": "04_FINANCIAL/Tax_Records", "clean_filename": os.path.basename(file_path)}
        elif "offer_letter" in name or "contract" in name or "employment" in name:
            return {"category": "01_PROFESSIONAL/Documentation", "clean_filename": os.path.basename(file_path)}
        return {"category": "03_PERSONAL/Archives", "clean_filename": os.path.basename(file_path)}

    def classify_document(self, file_path: str) -> dict:
        """Classifies any document (PDF or Image) and generates a clean filename."""
        if self.use_local_llm:
            return self.classify_local_llm(file_path)

        if self.mock_mode:
            return self.fallback_heuristic(file_path)
            
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
                
            json_text = self.clean_json_text(response.text)
            res = json.loads(json_text)
            category = res.get("category", "03_PERSONAL/Archives")
            clean_filename = res.get("clean_filename", os.path.basename(file_path))
            
            if "/" not in category or "_" not in category:
                logger.warning(f"Unexpected category path from Gemini: {category}, using default.")
                category = "03_PERSONAL/Archives"
                
            return {"category": category, "clean_filename": clean_filename}
            
        except Exception as e:
            logger.error(f"Error calling Gemini API for classification: {e}")
            return self.fallback_heuristic(file_path)

    def classify_image(self, file_path: str) -> str:
        """Backwards compatibility helper."""
        res = self.classify_document(file_path)
        return res["category"]
