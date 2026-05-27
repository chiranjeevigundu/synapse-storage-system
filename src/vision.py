import os
import json
from loguru import logger
from PIL import Image
from config import settings

class VisionClassifier:
    def __init__(self):
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
        You are an enterprise data librarian. Analyze this document (image or PDF) and classify it into one of these category paths:
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

        Also, generate a clean, descriptive, and standardized filename for this document based on its contents (e.g. "Sodexo_W2_2026.pdf", "Techsara_Offer_Letter.pdf", "Insurance_Form_8821.pdf"). Use camel case or snake case, capitalize proper nouns, keep the original file extension, and remove arbitrary prefixes like "CHIRU_" or random numbers unless relevant.

        Return a JSON object with:
        {
          "category": "string (the selected category path)",
          "clean_filename": "string (the new descriptive filename with the correct extension)"
        }
        """

    def clean_json_text(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    def classify_document(self, file_path: str) -> dict:
        """Classifies any document (PDF or Image) and generates a clean filename."""
        if self.mock_mode:
            name = os.path.basename(file_path).lower()
            if "receipt" in name or "invoice" in name:
                return {"category": "04_FINANCIAL/Invoices_Receipts", "clean_filename": f"Receipt_{os.path.basename(file_path)}"}
            elif "w2" in name or "tax" in name or "sodexo" in name:
                return {"category": "04_FINANCIAL/Tax_Records", "clean_filename": f"Tax_Record_{os.path.basename(file_path)}"}
            elif "offer_letter" in name or "contract" in name or "employment" in name:
                return {"category": "01_PROFESSIONAL/Documentation", "clean_filename": f"Employment_Document_{os.path.basename(file_path)}"}
            return {"category": "03_PERSONAL/Archives", "clean_filename": os.path.basename(file_path)}
            
        try:
            import google.generativeai as genai
            logger.info(f"Uploading file to Gemini API: {file_path}")
            uploaded_file = genai.upload_file(file_path)
            
            logger.info(f"Generating content for: {file_path}")
            response = self.model.generate_content(
                [self.schema_prompt, uploaded_file],
                generation_config={"response_mime_type": "application/json"}
            )
            
            # Clean up immediately
            try:
                uploaded_file.delete()
            except Exception as e:
                logger.error(f"Failed to delete uploaded temp file: {e}")
                
            json_text = self.clean_json_text(response.text)
            res = json.loads(json_text)
            category = res.get("category", "03_PERSONAL/Archives")
            clean_filename = res.get("clean_filename", os.path.basename(file_path))
            
            # Basic validation
            if "/" not in category or "_" not in category:
                logger.warning(f"Unexpected category path from Gemini: {category}, using default.")
                category = "03_PERSONAL/Archives"
                
            return {"category": category, "clean_filename": clean_filename}
            
        except Exception as e:
            logger.error(f"Error calling Gemini API for classification: {e}")
            name = os.path.basename(file_path).lower()
            if "receipt" in name or "invoice" in name:
                return {"category": "04_FINANCIAL/Invoices_Receipts", "clean_filename": os.path.basename(file_path)}
            elif "w2" in name or "tax" in name or "sodexo" in name:
                return {"category": "04_FINANCIAL/Tax_Records", "clean_filename": os.path.basename(file_path)}
            return {"category": "03_PERSONAL/Archives", "clean_filename": os.path.basename(file_path)}

    def classify_image(self, file_path: str) -> str:
        """Backwards compatibility helper."""
        res = self.classify_document(file_path)
        return res["category"]
