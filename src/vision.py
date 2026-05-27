import os
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
        You are an enterprise data librarian. Based on the provided file structure, output ONLY the most relevant category path for this image. 
        Do not include any other text, quotes, or markdown. Output exactly one of these paths:
        01_PROFESSIONAL/Projects
        01_PROFESSIONAL/Research
        01_PROFESSIONAL/Deployments
        01_PROFESSIONAL/Documentation
        02_TECHNICAL_HOMELAB/Network_Architecture
        02_TECHNICAL_HOMELAB/Hardware_Configs
        02_TECHNICAL_HOMELAB/Docker_Stacks
        02_TECHNICAL_HOMELAB/MCP_Source_Code
        03_PERSONAL/Mobile_Backups
        03_PERSONAL/Media_Archives
        03_PERSONAL/Archives
        04_FINANCIAL/Tax_Records
        04_FINANCIAL/Invoices_Receipts
        04_FINANCIAL/Legal_Documents
        """

    def classify_image(self, file_path: str) -> str:
        if self.mock_mode:
            # Simple mock logic for testing purposes when no API key is provided
            name = file_path.lower()
            if "receipt" in name or "invoice" in name:
                return "04_FINANCIAL/Invoices_Receipts"
            elif "hardware" in name or "rack" in name:
                return "02_TECHNICAL_HOMELAB/Hardware_Configs"
            return "03_PERSONAL/Media_Archives"
            
        try:
            img = Image.open(file_path)
            response = self.model.generate_content([self.schema_prompt, img])
            category = response.text.strip()
            
            # Basic validation
            if "/" in category and "_" in category:
                return category
            else:
                logger.warning(f"Unexpected vision output format: {category}")
                return "00_INGEST/Uncategorized"
        except Exception as e:
            logger.error(f"Vision API error: {e}")
            return "00_INGEST/Uncategorized"
