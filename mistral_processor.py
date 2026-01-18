"""
Enhanced Mistral OCR Processor с улучшенной обработкой текста и детекцией
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
    """Типы документов"""
    SERVICE_ACT = "service_act"
    INVOICE = "invoice"
    CONTRACT = "contract"
    UNKNOWN = "unknown"

@dataclass
class OCRConfig:
    """Конфигурация OCR"""
    use_tesseract_first: bool = True
    use_llava_fallback: bool = True
    preprocess_image: bool = True
    clean_with_llm: bool = True
    max_text_length: int = 5000
    confidence_threshold: float = 0.7
    
class EnhancedMistralOCRProcessor:
    def __init__(self, 
                 ollama_url: str = "http://localhost:11434",
                 model: str = "mistral:7b-instruct-v0.2-q4_K_M",
                 config: Optional[OCRConfig] = None):
        """
        Инициализация улучшенного процессора
        """
        self.ollama_url = ollama_url
        self.model = model
        self.vision_model = "llava:7b"
        self.config = config or OCRConfig()
        
        # Проверяем соединение
        self.check_ollama_connection()
        
        # Словарь исправлений типичных ошибок OCR
        self.ocr_corrections = {
            # Русские слова
            "ниоподписонся": "нижеподписавшиеся",
            "впарить": "оборудование",
            "выпопнил": "выполнил",
            "BRT": "АКТ",
            "прадетовителем": "представителем",
            "Boiron": "Выполненные",
            "Cyerarmum": "Сервисные",
            "Эрве": "Замена",
            
            # Английские артефакты на русские
            "doraron": "",
            "aos yy eae": "",
            "nia wa": "ООО",
            "taore Vonwrera": "представитель Заказчика",
            "tenner": "картридж",
            
            # Модели оборудования
            "Ls ОМЗ ОЛА": "LaserJet M1132",
        }
        
        # Паттерны для извлечения ключевой информации
        self.extraction_patterns = {
            "claim_number": [
                r"заявк\w*\s*(?:№|N|No|#)?\s*(\d{5,})",
                r"(?:№|N|No|#)\s*(\d{6,})",
                r"Номер заявки[:\s]+(\d+)",
                r"АКТ.*?(\d{6,})"
            ],
            "equipment_model": [
                r"(HP|Canon|Xerox|Brother|Samsung|Kyocera)[\s\w]+\d+",
                r"модель[:\s]+([\w\s\d]+)",
                r"принтер[:\s]+([\w\s\d]+)",
                r"аппарат[:\s]+([\w\s\d]+)"
            ],
            "cartridge_model": [
                r"(CE\d{3}[A-Z])",
                r"(Q\d{4}[A-Z])",
                r"картридж[:\s]+([\w\d]+)",
                r"(TK-\d+)",
                r"(MLT-\w\d+)"
            ],
            "customer_name": [
                r"ООО\s+[\"«]([^\"»]+)[\"»]",
                r"Заказчик[:\s]+([^\n]+)",
                r"Организация[:\s]+([^\n]+)"
            ]
        }
    
    def advanced_preprocess_image(self, image_path: str) -> str:
        """
        Продвинутая предобработка изображения для OCR
        """
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Не удалось загрузить изображение: {image_path}")
        
        # 1. Исправление перспективы (если документ сфотографирован под углом)
        img = self.correct_perspective(img)
        
        # 2. Удаление шума
        img = cv2.fastNlMeansDenoisingColored(img, None, 10, 10, 7, 21)
        
        # 3. Конвертация в grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 4. Адаптивная бинаризация (лучше для текста)
        binary = cv2.adaptiveThreshold(
            gray, 255, 
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 
            11, 2
        )
        
        # 5. Морфологические операции для улучшения текста
        kernel = np.ones((1, 1), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        
        # 6. Увеличение резкости
        kernel_sharp = np.array([[-1,-1,-1],
                                 [-1, 9,-1],
                                 [-1,-1,-1]])
        sharp = cv2.filter2D(binary, -1, kernel_sharp)
        
        # Сохраняем обработанное изображение
        temp_path = f"temp_enhanced_{os.path.basename(image_path)}"
        cv2.imwrite(temp_path, sharp)
        
        return temp_path
    
    def correct_perspective(self, img: np.ndarray) -> np.ndarray:
        """
        Коррекция перспективы документа
        """
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150, apertureSize=3)
            
            # Находим контуры
            contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]
            
            for contour in contours:
                peri = cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
                
                if len(approx) == 4:
                    # Нашли четырехугольник - возможно документ
                    pts = approx.reshape(4, 2)
                    rect = self.order_points(pts)
                    
                    # Применяем преобразование перспективы
                    dst = self.four_point_transform(img, rect)
                    return dst
            
            return img  # Если не нашли документ, возвращаем оригинал
            
        except Exception as e:
            print(f"Не удалось скорректировать перспективу: {e}")
            return img
    
    def order_points(self, pts):
        """Упорядочивание точек для преобразования перспективы"""
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]
        return rect
    
    def four_point_transform(self, image, pts):
        """Преобразование перспективы по 4 точкам"""
        rect = self.order_points(pts)
        (tl, tr, br, bl) = rect
        
        widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
        widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
        maxWidth = max(int(widthA), int(widthB))
        
        heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
        heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
        maxHeight = max(int(heightA), int(heightB))
        
        dst = np.array([
            [0, 0],
            [maxWidth - 1, 0],
            [maxWidth - 1, maxHeight - 1],
            [0, maxHeight - 1]], dtype="float32")
        
        M = cv2.getPerspectiveTransform(rect, dst)
        warped = cv2.warpPerspective(image, M, (maxWidth, maxHeight))
        
        return warped
    
    def enhanced_tesseract_ocr(self, image_path: str) -> Tuple[str, float]:
        """
        Улучшенный Tesseract OCR с confidence score
        """
        try:
            import pytesseract
            from PIL import Image
            
            img = Image.open(image_path)
            
            # Используем разные режимы PSM для лучшего результата
            psm_modes = [3, 6, 11, 4]  # Разные режимы сегментации
            best_text = ""
            best_confidence = 0
            
            for psm in psm_modes:
                try:
                    # Получаем данные с confidence
                    custom_config = f'--psm {psm} --oem 3'
                    data = pytesseract.image_to_data(
                        img, 
                        lang='rus+eng',
                        config=custom_config,
                        output_type=pytesseract.Output.DICT
                    )
                    
                    # Собираем текст и считаем среднюю уверенность
                    words = []
                    confidences = []
                    
                    for i in range(len(data['text'])):
                        if int(data['conf'][i]) > 0:  # Игнорируем слова без уверенности
                            word = data['text'][i].strip()
                            if word:
                                words.append(word)
                                confidences.append(int(data['conf'][i]))
                    
                    text = ' '.join(words)
                    avg_confidence = np.mean(confidences) if confidences else 0
                    
                    if avg_confidence > best_confidence:
                        best_text = text
                        best_confidence = avg_confidence
                        
                except Exception:
                    continue
            
            print(f"✓ Tesseract: {len(best_text)} символов, уверенность: {best_confidence:.1f}%")
            return best_text, best_confidence / 100
            
        except Exception as e:
            print(f"❌ Ошибка Tesseract: {e}")
            return "", 0.0
    
    def smart_text_cleaning(self, text: str) -> str:
        """
        Умная очистка текста с использованием словаря и паттернов
        """
        if not text:
            return text
        
        # 1. Применяем словарь исправлений
        for wrong, correct in self.ocr_corrections.items():
            text = text.replace(wrong, correct)
        
        # 2. Удаляем строки, состоящие только из мусора
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                cleaned_lines.append('')
                continue
            
            # Проверяем соотношение букв к общему количеству символов
            if len(line) > 3:
                letter_count = sum(1 for c in line if c.isalpha())
                ratio = letter_count / len(line)
                
                # Если менее 30% букв - вероятно мусор
                if ratio < 0.3:
                    continue
            
            # Проверяем на известные паттерны мусора
            garbage_patterns = [
                r'^[a-z]{2,4}\s+[a-z]{2,4}\s+[a-z]{2,4}$',  # Короткие англ слова
                r'^[\W_]+$',  # Только спецсимволы
                r'^[a-z\s]+$' if len(line) < 10 else None,  # Короткие англ строки
            ]
            
            is_garbage = False
            for pattern in garbage_patterns:
                if pattern and re.match(pattern, line.lower()):
                    is_garbage = True
                    break
            
            if not is_garbage:
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)
    
    def extract_key_information(self, text: str) -> Dict[str, Any]:
        """
        Извлечение ключевой информации с использованием паттернов
        """
        result = {
            "claim_number": None,
            "equipment_model": None,
            "cartridge_model": None,
            "customer_name": None,
            "work_type": None,
            "service_date": None
        }
        
        # Извлекаем по паттернам
        for field, patterns in self.extraction_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    result[field] = match.group(1).strip()
                    break
        
        # Определяем тип работ
        work_types = {
            "Замена картриджа": ["замен", "картридж"],
            "Техническое обслуживание": ["ТО", "обслуживание", "профилактика"],
            "Ремонт": ["ремонт", "починка", "восстановление"],
            "Диагностика": ["диагностика", "осмотр", "проверка"]
        }
        
        text_lower = text.lower()
        for work_type, keywords in work_types.items():
            if any(keyword in text_lower for keyword in keywords):
                result["work_type"] = work_type
                break
        
        # Извлекаем дату
        date_patterns = [
            r'(\d{1,2}[./]\d{1,2}[./]\d{2,4})',
            r'(\d{1,2}\s+\w+\s+\d{4})',
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                result["service_date"] = match.group(1)
                break
        
        return result
    
    def hybrid_ocr_strategy(self, image_path: str) -> str:
        """
        Гибридная стратегия OCR: комбинирует несколько методов
        """
        results = []
        
        # 1. Tesseract на оригинальном изображении
        if self.config.use_tesseract_first:
            text, confidence = self.enhanced_tesseract_ocr(image_path)
            if text and confidence > self.config.confidence_threshold:
                results.append((text, confidence, "tesseract_original"))
        
        # 2. Tesseract на предобработанном изображении
        if self.config.preprocess_image:
            try:
                processed_path = self.advanced_preprocess_image(image_path)
                text, confidence = self.enhanced_tesseract_ocr(processed_path)
                if text and confidence > self.config.confidence_threshold:
                    results.append((text, confidence, "tesseract_processed"))
                os.remove(processed_path)
            except Exception as e:
                print(f"Ошибка предобработки: {e}")
        
        # 3. LLaVA для сложных случаев
        if self.config.use_llava_fallback and (not results or max(r[1] for r in results) < 0.5):
            try:
                llava_text = self.extract_text_with_llava_enhanced(image_path)
                if llava_text:
                    results.append((llava_text, 0.6, "llava"))  # Фиксированная confidence для LLaVA
            except Exception as e:
                print(f"Ошибка LLaVA: {e}")
        
        # Выбираем лучший результат
        if results:
            best_result = max(results, key=lambda x: (x[1], len(x[0])))
            print(f"📊 Выбран метод: {best_result[2]} (confidence: {best_result[1]:.2f})")
            return best_result[0]
        
        return ""
    
    def extract_text_with_llava_enhanced(self, image_path: str) -> str:
        """
        Улучшенная версия извлечения текста через LLaVA
        """
        try:
            image_base64 = self.encode_image_to_base64(image_path)
            
            # Специализированный промпт для русских документов
            prompt = """You are an expert OCR system for Russian service documents.
Analyze the image and extract the data into a structured format.

Focus on:
1. Service Act Number (АКТ по заявке №)
2. Equipment Model (Модель аппарата)
3. Serial Number (Серийный №)
4. Counter readings (Счетчик страниц: Ч/Б and Цветных)
5. COMPLETED WORKS (Выполненные работы) - extract as a list of items with descriptions and quantities if available.
6. Checkboxes - indicate which specific works were checked (Осмотр, Инсталляция, ТО1, ТО2, ТО3, Ремонт, Доставка).

FORMAT: Return as a clean JSON object.
{
  "act_number": "number",
  "equipment": {
    "model": "model name",
    "serial": "serial number",
    "counters": {"bw": 0, "color": 0}
  },
  "work_items": [
    {"description": "item description", "quantity": 1}
  ],
  "checkboxes": {
    "inspection": boolean,
    "installation": boolean,
    "to1": boolean,
    "to2": boolean,
    "to3": boolean,
    "repair": boolean,
    "delivery": boolean
  }
}
If JSON is not possible, extract text maintaining layout."""
            
            payload = {
                "model": "llava:7b",
                "prompt": prompt,
                "images": [image_base64],
                "stream": False,
                "options": {
                    "temperature": 0.05,
                    "num_predict": 4096,
                    "seed": 42
                }
            }
            
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=300
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("response", "").strip()
            
        except Exception as e:
            print(f"Ошибка LLaVA: {e}")
        
        return ""
    
    def advanced_llm_cleaning(self, text: str) -> str:
        """
        Продвинутая очистка текста с помощью LLM
        """
        if not text or len(text.strip()) < 10:
            return text
        
        # Сначала применяем быструю очистку
        text = self.smart_text_cleaning(text)
        
        if not self.config.clean_with_llm:
            return text
        
        try:
            # Ограничиваем размер для LLM
            text_chunk = text[:2000] if len(text) > 2000 else text
            
            prompt = f"""You are a Russian document text correction expert.

INPUT: OCR text from a Russian service document with recognition errors.

YOUR TASK:
1. Fix OCR errors in Russian words
2. Remove garbage text that doesn't make sense
3. Reconstruct damaged Russian words
4. Keep all numbers, dates, and model names intact
5. Preserve document structure

COMMON CORRECTIONS:
- "ниоподписонся" → "нижеподписавшиеся"
- "выпопнил" → "выполнил"
- "BRT" → "АКТ"
- Random English letters between Russian words should be removed

CORRUPTED TEXT:
{text_chunk}

CORRECTED TEXT (Russian, clean, structured):"""
            
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "top_p": 0.9,
                        "num_predict": 2048
                    }
                },
                timeout=60
            )
            
            if response.status_code == 200:
                cleaned = response.json().get("response", text).strip()
                if cleaned and len(cleaned) > len(text) * 0.3:  # Проверка что не удалили слишком много
                    # Объединяем с остальной частью если текст был обрезан
                    if len(text) > 2000:
                        return cleaned + text[2000:]
                    return cleaned
            
        except Exception as e:
            print(f"Ошибка LLM очистки: {e}")
        
        return text
    
    def detect_signature_and_stamp_advanced(self, image_path: str) -> Dict[str, bool]:
        """
        Обнаружение подписи и печати на изображении.
        Использует CV-методы для поиска контрастных и геометрических признаков.
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                return {"has_signature": False, "has_stamp": False}
            
            height, width = img.shape[:2]
            
            # 1. Поиск печати (круги + цвет)
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            
            # Диапазоны для красного и синего (типичные цвета печатей)
            red_mask = cv2.bitwise_or(
                cv2.inRange(hsv, np.array([0, 50, 50]), np.array([10, 255, 255])),
                cv2.inRange(hsv, np.array([170, 50, 50]), np.array([180, 255, 255]))
            )
            blue_mask = cv2.inRange(hsv, np.array([100, 50, 50]), np.array([130, 255, 255]))
            color_mask = cv2.bitwise_or(red_mask, blue_mask)
            
            # Морфологическая очистка
            kernel = np.ones((5, 5), np.uint8)
            color_mask = cv2.morphologyEx(color_mask, cv2.MORPH_OPEN, kernel)
            
            # Поиск круглых контуров
            contours, _ = cv2.findContours(color_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            has_stamp = False
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area > 1000:
                    perimeter = cv2.arcLength(cnt, True)
                    circularity = 4 * np.pi * area / (perimeter * perimeter) if perimeter > 0 else 0
                    if circularity > 0.5:
                        has_stamp = True
                        break
            
            # 2. Поиск подписи (нижняя треть, высокая плотность линий)
            bottom_start = int(height * 0.7)
            bottom_area = img[bottom_start:height, :]
            gray_bottom = cv2.cvtColor(bottom_area, cv2.COLOR_BGR2GRAY)
            
            # Используем Canny для поиска краев (подписи обычно имеют много резких краев)
            edges = cv2.Canny(gray_bottom, 50, 150)
            edge_density = np.sum(edges > 0) / (edges.shape[0] * edges.shape[1])
            
            # Эмпирический порог для плотности рукописного текста
            has_signature = edge_density > 0.01
            
            return {
                "has_signature": has_signature,
                "has_stamp": has_stamp
            }
            
        except Exception as e:
            print(f"Ошибка в detect_signature_and_stamp_advanced: {e}")
            return {"has_signature": False, "has_stamp": False}

    def process_document_enhanced(self, image_path: str, expected_claim_number: Optional[str] = None) -> Dict[str, Any]:
        """
        Улучшенная обработка документа
        """
        start_time = datetime.now()
        print(f"🔍 Обработка документа: {image_path}")
        
        try:
            # 1. Гибридное извлечение текста
            print("📖 Извлечение текста (гибридная стратегия)...")
            extracted_text = self.hybrid_ocr_strategy(image_path)
            
            if not extracted_text:
                raise ValueError("Не удалось извлечь текст из документа")
            
            print(f"📊 Извлечено {len(extracted_text)} символов")
            
            # 2. Продвинутая очистка
            print("🧹 Очистка текста...")
            cleaned_text = self.advanced_llm_cleaning(extracted_text)
            print(f"📊 После очистки: {len(cleaned_text)} символов")
            
            # 3. Извлечение ключевой информации
            print("🔑 Извлечение ключевой информации...")
            key_info = self.extract_key_information(cleaned_text)
            
            # 4. Детекция подписи и печати
            print("🖋️ Поиск подписи и печати...")
            signature_stamp = self.detect_signature_and_stamp_advanced(image_path)
            
            # 5. Проверка требований
            print("✅ Проверка требований...")
            check_result = self.check_requirements_enhanced(
                key_info, 
                signature_stamp, 
                expected_claim_number
            )
            
            # 6. Определение типа документа
            doc_type = self.detect_document_type(cleaned_text)
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            result = {
                "success": True,
                "timestamp": datetime.now().isoformat(),
                "filename": os.path.basename(image_path),
                "processing_time_seconds": processing_time,
                "document_type": doc_type.value,
                "extracted_data": {
                    **key_info,
                    "has_signature": signature_stamp.get("has_signature", False),
                    "has_stamp": signature_stamp.get("has_stamp", False),
                    "text_preview": cleaned_text[:500] + "..." if len(cleaned_text) > 500 else cleaned_text
                },
                "validation": check_result,
                "full_text": cleaned_text,
                "metadata": {
                    "ocr_engine": "Hybrid (Tesseract + LLaVA)",
                    "llm_model": self.model,
                    "preprocessing_applied": self.config.preprocess_image,
                    "llm_cleaning_applied": self.config.clean_with_llm
                }
            }
            
            print(f"✅ Обработка завершена за {processing_time:.2f} сек")
            print(f"📋 Тип документа: {doc_type.value}")
            print(f"📝 Номер заявки: {key_info.get('claim_number', 'Не найден')}")
            
            return result
            
        except Exception as e:
            print(f"❌ Ошибка обработки: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
                "filename": os.path.basename(image_path)
            }
    
    def detect_document_type(self, text: str) -> DocumentType:
        """
        Определение типа документа
        """
        text_lower = text.lower()
        
        if "акт" in text_lower and "заявк" in text_lower:
            return DocumentType.SERVICE_ACT
        elif "счет" in text_lower or "invoice" in text_lower:
            return DocumentType.INVOICE
        elif "договор" in text_lower or "contract" in text_lower:
            return DocumentType.CONTRACT
        else:
            return DocumentType.UNKNOWN
    
    def check_requirements_enhanced(self, 
                                   key_info: Dict, 
                                   signature_stamp: Dict,
                                   expected_claim: Optional[str]) -> Dict:
        """
        Улучшенная проверка требований
        """
        issues = []
        warnings = []
        suggestions = []
        
        # Проверка номера заявки
        if expected_claim:
            claim = key_info.get("claim_number")
            if claim:
                if str(claim) != str(expected_claim):
                    issues.append({
                        "field": "claim_number",
                        "issue": "mismatch",
                        "expected": expected_claim,
                        "found": claim,
                        "severity": "high"
                    })
            else:
                warnings.append({
                    "field": "claim_number",
                    "issue": "not_found",
                    "severity": "medium"
                })
        
        # Проверка обязательных полей
        required_fields = {
            "equipment_model": "Модель оборудования",
            "customer_name": "Название заказчика",
            "work_type": "Тип выполненных работ"
        }
        
        for field, description in required_fields.items():
            if not key_info.get(field):
                warnings.append({
                    "field": field,
                    "issue": "missing",
                    "description": f"{description} не найдено",
                    "severity": "medium"
                })
        
        # Проверка подписи и печати
        if not signature_stamp.get("has_signature"):
            issues.append({
                "field": "signature",
                "issue": "missing",
                "description": "Подпись не обнаружена",
                "severity": "high"
            })
        
        if not signature_stamp.get("has_stamp"):
            warnings.append({
                "field": "stamp",
                "issue": "missing",
                "description": "Печать не обнаружена",
                "severity": "low"
            })
        
        # Формирование рекомендаций
        if issues:
            suggestions.append("Документ требует доработки перед закрытием заявки")
        elif warnings:
            suggestions.append("Рекомендуется ручная проверка документа")
        else:
            suggestions.append("Документ готов к обработке")
        
        # Определение статуса
        if any(i["severity"] == "high" for i in issues):
            status = "REJECTED"
        elif warnings:
            status = "NEEDS_REVIEW"
        else:
            status = "APPROVED"
        
        return {
            "status": status,
            "issues": issues,
            "warnings": warnings,
            "suggestions": suggestions,
            "can_process": status == "APPROVED",
            "requires_manual_review": status == "NEEDS_REVIEW"
        }

# Пример использования
if __name__ == "__main__":
    # Создаем процессор с оптимальными настройками
    config = OCRConfig(
        use_tesseract_first=True,
        use_llava_fallback=True,
        preprocess_image=True,
        clean_with_llm=True,
        confidence_threshold=0.5
    )
    
    processor = EnhancedMistralOCRProcessor(config=config)
    
    # Обрабатываем документ
    result = processor.process_document_enhanced(
        "path/to/your/document.jpg",
        expected_claim_number="1847896"
    )
    
    # Выводим результат
    if result["success"]:
        print("\n📄 РЕЗУЛЬТАТ ОБРАБОТКИ:")
        print(f"Тип документа: {result['document_type']}")
        print(f"Статус валидации: {result['validation']['status']}")
        print(f"\nИзвлеченные данные:")
        for key, value in result['extracted_data'].items():
            if value and key != 'text_preview':
                print(f"  • {key}: {value}")
    else:
        print(f"\n❌ Ошибка: {result['error']}")
