"""
Qwen2.5-VL OCR Processor with optimized VDU (Visual Document Understanding) capabilities.
"""
import os
import json
import base64
import requests
import cv2
import numpy as np
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
import re
from dataclasses import dataclass
from enum import Enum

class DocumentType(Enum):
    """Types of documents"""
    SERVICE_ACT = "service_act"
    INVOICE = "invoice"
    CONTRACT = "contract"
    UNKNOWN = "unknown"

@dataclass
class OCRConfig:
    """OCR Configuration"""
    preprocess_image: bool = True  # Less aggressive than for Tesseract
    confidence_threshold: float = 0.6
    
class QwenOCRProcessor:
    def __init__(self, 
                 ollama_url: str = "http://localhost:11434",
                 model: str = "qwen2.5-vl:7b",
                 config: Optional[OCRConfig] = None):
        """
        Initialize Qwen2.5-VL Processor
        """
        self.ollama_url = ollama_url
        self.model = model
        self.config = config or OCRConfig()
        
        # Check connection
        self.check_ollama_connection()
        
        # Regex patterns for validation and fallback
        self.extraction_patterns = {
            "claim_number": [
                r"заявк\w*\s*(?:№|N|No|#)?\s*(\d{5,})",
                r"(?:№|N|No|#)\s*(\d{6,})",
                r"Номер заявки[:\s]+(\d+)",
                r"АКТ.*?(\d{6,})",
                r"(\d{6,7})"  # Fallback just searching for 6-7 digits
            ],
            "equipment_model": [
                r"(HP|Canon|Xerox|Brother|Samsung|Kyocera)[\s\w]+\d+",
                r"модель[:\s]+([\w\s\d]+)",
            ],
            "customer_name": [
                r"ООО\s+[\"«]([^\"»]+)[\"»]",
                r"Заказчик[:\s]+([^\n]+)",
            ]
        }

    def check_ollama_connection(self):
        """Check availability of Ollama server"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags")
            if response.status_code == 200:
                print(f"✅ Ollama connected at {self.ollama_url}")
                models = [m['name'] for m in response.json().get('models', [])]
                if not any(self.model in m for m in models):
                    print(f"⚠️ Warning: Model {self.model} not found in Ollama list. Please pull it.")
            else:
                print(f"❌ Ollama returned status {response.status_code}")
        except Exception as e:
            print(f"❌ Failed to connect to Ollama: {e}")

    def encode_image_to_base64(self, image_path: str) -> str:
        """Read and encode image to base64"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
            
    def preprocess_for_vlm(self, image_path: str) -> str:
        """
        Lightweight preprocessing for Vision Language Model.
        Mainly focuses on orientation and basic quality, without aggressive binarization.
        """
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Failed to load image: {image_path}")
            
        # 1. Perspective correction (reusing logic if straightforward, but let's keep it simple first)
        # For VLM, the context is important, so we avoid cropping too aggressively unless confident.
        # We will apply mild denoising.
        
        # Denoising
        denoised = cv2.fastNlMeansDenoisingColored(img, None, 10, 10, 7, 21)
        
        # Save temp file
        temp_path = f"temp_qwen_{os.path.basename(image_path)}"
        cv2.imwrite(temp_path, denoised)
        
        return temp_path

    def extract_text_with_qwen(self, image_path: str) -> Dict[str, Any]:
        """
        Extract structured data using Qwen2.5-VL
        """
        try:
            # Use processed image if configured
            proc_path = image_path
            if self.config.preprocess_image:
                try:
                    proc_path = self.preprocess_for_vlm(image_path)
                except Exception as e:
                    print(f"Preprocessing failed, using original: {e}")
            
            image_base64 = self.encode_image_to_base64(proc_path)
            
            # Remove temp file
            if proc_path != image_path and os.path.exists(proc_path):
                os.remove(proc_path)
                
            prompt = """Analyze this Russian service act document and extract data into JSON.
            
REQUIRED FIELDS:
1. "claim_number": The application/claim number (Usually after "Заявка №" or "Акт №"). Look for 5-7 digits.
2. "date": Service date.
3. "customer": Customer organization name.
4. "equipment": Equipment model (e.g. HP LaserJet 1010).
5. "serial_number": Device serial number.
6. "page_counts": {"bw": number, "color": number} - Page counters if present.
7. "works": List of performed works/items (description and quantity).
8. "signatures": {"engineer": boolean, "customer": boolean} - Visual check if signatures are present.
9. "stamps": {"customer": boolean} - Visual check if stamp is present.

Output **ONLY** valid JSON.
"""
            
            payload = {
                "model": self.model,
                "prompt": prompt,
                "images": [image_base64],
                "stream": False,
                "options": {
                    "temperature": 0.1,  # Low temperature for factual extraction
                    "num_predict": 2048
                }
            }
            
            print(f"🚀 Sending request to Qwen2.5-VL ({self.model})...")
            start_t = datetime.now()
            
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=180
            )
            
            duration = (datetime.now() - start_t).total_seconds()
            print(f"⏱️ Response received in {duration:.2f}s")
            
            if response.status_code == 200:
                result_text = response.json().get("response", "").strip()
                # Try to clean markdown code blocks if present
                if "```json" in result_text:
                    result_text = result_text.split("```json")[1].split("```")[0].strip()
                elif "```" in result_text:
                    result_text = result_text.split("```")[1].split("```")[0].strip()
                    
                try:
                    return json.loads(result_text)
                except json.JSONDecodeError:
                    print("⚠️ Failed to parse JSON from Qwen response. Returning raw text wrapped.")
                    return {"error": "json_parse_error", "raw_text": result_text}
            else:
                print(f"❌ API Error: {response.text}")
                return {}
                
        except Exception as e:
            print(f"❌ Qwen extraction error: {e}")
            return {}

    def process_document(self, image_path: str, expected_claim_number: Optional[str] = None) -> Dict[str, Any]:
        """
        Main processing method
        """
        start_time = datetime.now()
        print(f"🔍 Processing document: {image_path}")
        
        # 1. Extract with Qwen
        extracted_data = self.extract_text_with_qwen(image_path)
        
        # 2. Post-process and Validate
        warnings = []
        issues = []
        
        # Normalize extracted data
        claim_number = str(extracted_data.get("claim_number", "")).strip()
        # Clean non-digits from claim number if mostly digits
        if sum(c.isdigit() for c in claim_number) > 3:
             claim_number = "".join([c for c in claim_number if c.isdigit()])
             
        # Fallback validation with regex if Qwen missed it (optional, but good for robustness)
        # For now relying on Qwen, but logic can be added here.
        
        # Compare with expected
        if expected_claim_number:
            if claim_number and expected_claim_number not in claim_number:
                 issues.append(f"Claim number mismatch: Expected {expected_claim_number}, got {claim_number}")
            elif not claim_number:
                 warnings.append("Claim number not found by AI")

        # Check signatures
        sigs = extracted_data.get("signatures", {})
        if not sigs.get("customer", False):
            issues.append("Customer signature missing")
            
        processing_time = (datetime.now() - start_time).total_seconds()
        
        status = "APPROVED" if not issues else "REJECTED"
        if warnings and status == "APPROVED":
            status = "NEEDS_REVIEW"
            
        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "filename": os.path.basename(image_path),
            "processing_time_seconds": processing_time,
            "document_type": DocumentType.SERVICE_ACT.value, # Assuming service act for now
            "extracted_data": extracted_data,
            "validation": {
                "status": status,
                "issues": issues,
                "warnings": warnings
            },
            "metadata": {
                "model": self.model,
                "engine": "Qwen2.5-VL"
            }
        }

if __name__ == "__main__":
    # Test
    processor = QwenOCRProcessor()
    # print(processor.process_document("test.jpg"))
