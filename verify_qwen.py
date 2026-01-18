import sys
import unittest
import json
from unittest.mock import patch, MagicMock
# Mock cv2 before importing processor because it is imported at top level
sys.modules["cv2"] = MagicMock()
from qwen_processor import QwenOCRProcessor

class TestQwenOCRProcessor(unittest.TestCase):
    def setUp(self):
        self.processor = QwenOCRProcessor(model="qwen2.5-vl:7b-test")

    @patch('qwen_processor.requests.post')
    def test_extract_text_with_qwen_success(self, mock_post):
        # Mock successful Ollama response
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        expected_json = {
            "claim_number": "123456",
            "date": "20.01.2025",
            "equipment": "HP LaserJet",
            "signatures": {"customer": True}
        }
        
        # Simulate Qwen wrapping JSON in markdown
        mock_response.json.return_value = {
            "response": "Here is the data:\n```json\n" + json.dumps(expected_json) + "\n```"
        }
        mock_post.return_value = mock_response

        # Mock preprocess to just return original path
        with patch.object(self.processor, 'preprocess_for_vlm', return_value="dummy.jpg"):
            with patch.object(self.processor, 'encode_image_to_base64', return_value="base64str"):
                 with patch('os.remove'): # Don't try to remove dummy file
                    result = self.processor.extract_text_with_qwen("dummy.jpg")
        
        self.assertEqual(result['claim_number'], "123456")
        self.assertEqual(result['equipment'], "HP LaserJet")

    def test_regex_fallback_patterns(self):
        # Test if regexes are valid regexes
        import re
        for key, patterns in self.processor.extraction_patterns.items():
            for pattern in patterns:
                try:
                    re.compile(pattern)
                except re.error:
                    self.fail(f"Invalid regex pattern: {pattern}")

if __name__ == '__main__':
    unittest.main()
