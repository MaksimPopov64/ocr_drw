"""
Mistral OCR Processor для распознавания и анализа документов через Ollama
"""
import os
import json
import base64
import requests
import cv2
import numpy as np
from datetime import datetime
from typing import Dict, Any, Optional, List
import re

class MistralOCRProcessor:
    def __init__(self, ollama_url: str = "http://localhost:11434", model: str = "mistral:7b-instruct-v0.2-q4_K_M"):
        """
        Инициализация процессора для работы с Mistral через Ollama
        
        Args:
            ollama_url: URL сервера Ollama
            model: Название модели для использования
        """
        self.ollama_url = ollama_url
        self.model = model
        self.vision_model = "llava:7b"  # Альтернатива с поддержкой изображений
        
        # Проверяем доступность Ollama
        self.check_ollama_connection()
        
        # Шаблон для парсинга актов
        self.document_template = {
            "claim_number": None,
            "equipment_model": None,
            "cartridge_model": None,
            "customer_name": None,
            "work_type": None,
            "signature_present": False,
            "stamp_present": False,
            "total_pages": None,
            "service_date": None
        }
    
    def check_ollama_connection(self):
        """Проверка соединения с Ollama"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags")
            if response.status_code == 200:
                print(f"✅ Ollama доступен. Модели: {response.json()}")
            else:
                print(f"⚠️ Ollama ответил с кодом: {response.status_code}")
        except Exception as e:
            print(f"❌ Не удалось подключиться к Ollama: {e}")
            print("Убедитесь, что Ollama запущен: ollama serve")
    
    def encode_image_to_base64(self, image_path: str) -> str:
        """
        Кодирование изображения в base64 для отправки в модель
        """
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        return encoded_string
    
    def preprocess_image_for_ocr(self, image_path: str) -> str:
        """
        Предобработка изображения для улучшения читаемости
        """
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Не удалось загрузить изображение: {image_path}")
        
        # Улучшение контраста и четкости
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Адаптивное пороговое преобразование
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 11, 2
        )
        
        # Удаление шума
        kernel = np.ones((1, 1), np.uint8)
        processed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        
        # Сохраняем обработанное изображение
        temp_path = f"temp_processed_{os.path.basename(image_path)}"
        cv2.imwrite(temp_path, processed)
        
        return temp_path
    
    def extract_text_with_mistral(self, image_path: str) -> str:
        """
        Извлечение текста с изображения с помощью Mistral
        """
        try:
            # Кодируем изображение в base64
            image_base64 = self.encode_image_to_base64(image_path)
            
            # Подготавливаем промпт для OCR
            prompt = """Ты - система оптического распознавания текста (OCR). 
            Извлеки весь текст с изображения документа максимально точно.
            Сохрани структуру текста, включая таблицы если они есть.
            Верни только распознанный текст, без комментариев."""
            
            # Формируем запрос к Ollama API
            payload = {
                "model": self.model,
                "prompt": prompt,
                "images": [image_base64],
                "stream": False,
                "options": {
                    "temperature": 0.1,  # Низкая температура для точности
                    "num_predict": 4096
                }
            }
            
            # Отправляем запрос
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=300  # Увеличиваем таймаут для больших документов
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("response", "")
            else:
                print(f"Ошибка API Ollama: {response.status_code}")
                print(f"Ответ: {response.text}")
                return ""
                
        except Exception as e:
            print(f"Ошибка при извлечении текста: {e}")
            return ""
    
    def analyze_document_structure(self, text: str) -> Dict[str, Any]:
        """
        Анализ структуры документа с помощью Mistral
        """
        try:
            # Промпт для анализа акта выполненных работ
            prompt = f"""Ты анализируешь документ "Акт выполненных работ". 
            Извлеки следующую информацию в формате JSON:
            
            1. Номер заявки (цифры)
            2. Модель оборудования (например, HP, Canon, Xerox)
            3. Модель картриджа (например, CE285A, Q2612A)
            4. Наименование заказчика/клиента
            5. Тип выполненных работ (Осмотр, ТО1, ТО2, ТО3, Ремонт, Замена картриджа)
            6. Наличие подписи клиента (да/нет)
            7. Наличие печати/штампа (да/нет)
            8. Количество отпечатанных страниц (цифра)
            9. Дата выполнения работ
            
            Текст документа:
            {text[:3000]}  # Ограничиваем длину для промпта
            
            Верни ТОЛЬКО JSON в формате:
            {{
                "claim_number": "значение или null",
                "equipment_model": "значение или null",
                "cartridge_model": "значение или null",
                "customer_name": "значение или null",
                "work_type": "значение или null",
                "signature_present": true/false,
                "stamp_present": true/false,
                "total_pages": число или null,
                "service_date": "дата или null"
            }}
            
            Не добавляй пояснений, только JSON."""
            
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 2048
                }
            }
            
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=180
            )
            
            if response.status_code == 200:
                result = response.json()
                response_text = result.get("response", "")
                
                # Извлекаем JSON из ответа
                try:
                    # Ищем JSON в ответе (модель может добавить текст до/после JSON)
                    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(0)
                        parsed_data = json.loads(json_str)
                        return parsed_data
                    else:
                        print(f"Не найден JSON в ответе: {response_text}")
                        return self.document_template
                except json.JSONDecodeError as e:
                    print(f"Ошибка парсинга JSON: {e}")
                    print(f"Ответ модели: {response_text}")
                    return self.document_template
            else:
                print(f"Ошибка API при анализе: {response.status_code}")
                return self.document_template
                
        except Exception as e:
            print(f"Ошибка анализа документа: {e}")
            return self.document_template
    
    def detect_signature_and_stamp(self, image_path: str) -> Dict[str, bool]:
        """
        Детекция подписи и печати на изображении
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                return {"signature": False, "stamp": False}
            
            height, width = img.shape[:2]
            
            # Анализ нижней части документа (где обычно подпись и печать)
            bottom_section = img[int(height*0.7):height, 0:width]
            
            # Кодируем секцию в base64
            temp_path = "temp_bottom_section.jpg"
            cv2.imwrite(temp_path, bottom_section)
            image_base64 = self.encode_image_to_base64(temp_path)
            
            # Промпт для анализа подписи и печати
            prompt = """Проанализируй изображение. Это нижняя часть документа.
            Определи: 
            1. Есть ли на изображении подпись (рукописная)?
            2. Есть ли на изображении печать/штамп (обычно круглая)?
            
            Верни ответ в формате JSON:
            {
                "has_signature": true/false,
                "has_stamp": true/false
            }"""
            
            payload = {
                "model": self.vision_model if self.check_model_exists(self.vision_model) else self.model,
                "prompt": prompt,
                "images": [image_base64],
                "stream": False,
                "options": {"temperature": 0.1}
            }
            
            response = requests.post(f"{self.ollama_url}/api/generate", json=payload)
            
            if response.status_code == 200:
                result = response.json()
                response_text = result.get("response", "")
                
                # Парсим ответ
                try:
                    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                    if json_match:
                        return json.loads(json_match.group(0))
                except:
                    pass
            
            # Если модель не сработала, используем компьютерное зрение
            return self.cv_detect_signature_stamp(img)
            
        except Exception as e:
            print(f"Ошибка детекции подписи/печати: {e}")
            return {"has_signature": False, "has_stamp": False}
        finally:
            # Удаляем временный файл
            if os.path.exists("temp_bottom_section.jpg"):
                os.remove("temp_bottom_section.jpg")
    
    def cv_detect_signature_stamp(self, img: np.ndarray) -> Dict[str, bool]:
        """
        Детекция подписи и печати с помощью компьютерного зрения
        """
        result = {"has_signature": False, "has_stamp": False}
        
        try:
            # Преобразуем в HSV для цветовой сегментации
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            
            # Поиск красного цвета (печати)
            lower_red1 = np.array([0, 70, 50])
            upper_red1 = np.array([10, 255, 255])
            lower_red2 = np.array([170, 70, 50])
            upper_red2 = np.array([180, 255, 255])
            
            mask_red1 = cv2.inRange(hsv, lower_red1, upper_red1)
            mask_red2 = cv2.inRange(hsv, lower_red2, upper_red2)
            red_mask = cv2.bitwise_or(mask_red1, mask_red2)
            
            # Поиск кругов (печати обычно круглые)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            circles = cv2.HoughCircles(
                gray, cv2.HOUGH_GRADIENT, dp=1.2, 
                minDist=50, param1=50, param2=30, 
                minRadius=20, maxRadius=100
            )
            
            result["has_stamp"] = (np.sum(red_mask) > 10000) or (circles is not None)
            
            # Поиск подписи (контуры с высокой детализацией)
            edges = cv2.Canny(gray, 50, 150)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            signature_contours = []
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if 100 < area < 5000:  # Подпись среднего размера
                    perimeter = cv2.arcLength(cnt, True)
                    if perimeter > 0:
                        circularity = 4 * np.pi * area / (perimeter * perimeter)
                        if circularity < 0.5:  # Не круглый объект
                            signature_contours.append(cnt)
            
            result["has_signature"] = len(signature_contours) > 2
            
            return result
            
        except Exception as e:
            print(f"Ошибка CV детекции: {e}")
            return result
    
    def check_model_exists(self, model_name: str) -> bool:
        """Проверка доступности модели"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags")
            models = [m["name"] for m in response.json().get("models", [])]
            return any(model_name in m for m in models)
        except:
            return False
    
    def process_document(self, image_path: str, expected_claim_number: Optional[str] = None) -> Dict[str, Any]:
        """
        Полная обработка документа
        """
        start_time = datetime.now()
        
        print(f"🔍 Начинаем обработку документа: {image_path}")
        
        try:
            # 1. Предобработка изображения
            print("📝 Предобработка изображения...")
            processed_path = self.preprocess_image_for_ocr(image_path)
            
            # 2. Извлечение текста
            print("🔤 Извлечение текста с помощью Mistral...")
            extracted_text = self.extract_text_with_mistral(processed_path)
            
            # Если Mistral не сработал, пробуем Tesseract как fallback
            if not extracted_text or len(extracted_text.strip()) < 10:
                print("⚠️ Mistral не извлек текст, используем Tesseract...")
                extracted_text = self.extract_text_with_tesseract(processed_path)
            
            print(f"📊 Извлечено символов: {len(extracted_text)}")
            
            # 3. Анализ структуры документа
            print("🧠 Анализ структуры документа...")
            parsed_data = self.analyze_document_structure(extracted_text)
            
            # 4. Детекция подписи и печати
            print("🖋️ Детекция подписи и печати...")
            signature_stamp = self.detect_signature_and_stamp(image_path)
            
            # 5. Проверка требований
            print("✅ Проверка требований...")
            check_result = self.check_requirements(
                parsed_data, 
                signature_stamp, 
                expected_claim_number
            )
            
            # 6. Формирование результата
            result = {
                "timestamp": datetime.now().isoformat(),
                "filename": os.path.basename(image_path),
                "processing_time_seconds": (datetime.now() - start_time).total_seconds(),
                "parsed_data": {
                    **parsed_data,
                    "signature_status": "FOUND" if signature_stamp.get("has_signature") else "NOT_FOUND",
                    "stamp_status": "FOUND" if signature_stamp.get("has_stamp") else "NOT_FOUND",
                    "full_text": extracted_text[:5000]  # Ограничиваем для вывода
                },
                "check_result": check_result,
                "ocr_engine": "Mistral/Ollama",
                "model_used": self.model,
                "success": True
            }
            
            result["status"] = check_result.get("status", "UNKNOWN")
            
            print(f"✅ Обработка завершена за {result['processing_time_seconds']:.2f} сек")
            
            return result
            
        except Exception as e:
            print(f"❌ Ошибка обработки: {e}")
            return {
                "error": f"Ошибка обработки документа: {str(e)}",
                "status": "ERROR",
                "timestamp": datetime.now().isoformat(),
                "success": False
            }
        finally:
            # Удаляем временные файлы
            if 'processed_path' in locals() and os.path.exists(processed_path):
                os.remove(processed_path)
    
    def extract_text_with_tesseract(self, image_path: str) -> str:
        """Fallback метод с Tesseract"""
        try:
            import pytesseract
            img = cv2.imread(image_path)
            text = pytesseract.image_to_string(img, lang='rus+eng')
            return text
        except ImportError:
            return "Tesseract не установлен"
        except Exception as e:
            print(f"Ошибка Tesseract: {e}")
            return ""
    
    def check_requirements(self, parsed_data: Dict, signature_stamp: Dict, expected_claim: Optional[str]) -> Dict:
        """Проверка требований к документу"""
        issues = []
        warnings = []
        
        # 1. Проверка номера заявки
        claim_number = parsed_data.get("claim_number")
        if expected_claim and claim_number:
            if str(claim_number) != str(expected_claim):
                issues.append({
                    "code": "CLAIM_MISMATCH",
                    "message": f"Номер заявки не совпадает. Ожидалось: {expected_claim}, найдено: {claim_number}",
                    "severity": "ERROR"
                })
        
        if not claim_number:
            warnings.append({
                "code": "CLAIM_NOT_FOUND",
                "message": "Номер заявки не найден в документе",
                "severity": "WARNING"
            })
        
        # 2. Проверка модели оборудования
        if not parsed_data.get("equipment_model"):
            issues.append({
                "code": "MODEL_NOT_FOUND",
                "message": "Модель оборудования не найдена",
                "severity": "ERROR"
            })
        
        # 3. Проверка подписи
        if not signature_stamp.get("has_signature"):
            issues.append({
                "code": "SIGNATURE_NOT_FOUND",
                "message": "Подпись клиента не обнаружена",
                "severity": "ERROR"
            })
        
        # 4. Проверка печати
        if not signature_stamp.get("has_stamp"):
            warnings.append({
                "code": "STAMP_NOT_FOUND",
                "message": "Печать клиента не обнаружена",
                "severity": "WARNING"
            })
        
        # Определение статуса
        has_errors = any(i.get("severity") == "ERROR" for i in issues)
        has_warnings = any(w.get("severity") == "WARNING" for w in warnings)
        
        if has_errors:
            status = "REJECTED"
        elif has_warnings:
            status = "NEEDS_REVIEW"
        else:
            status = "APPROVED"
        
        return {
            "status": status,
            "issues": issues,
            "warnings": warnings,
            "decision": {
                "action": "CLOSE_CLAIM" if status == "APPROVED" else 
                         "REVIEW_REQUIRED" if status == "NEEDS_REVIEW" else 
                         "RETURN_FOR_CORRECTION",
                "message": "Все проверки пройдены" if status == "APPROVED" else
                          "Требуется ручная проверка" if status == "NEEDS_REVIEW" else
                          "Документ не прошел проверку",
                "steps": [
                    f"Внести номенклатуру: {parsed_data.get('cartridge_model', 'N/A')}",
                    f"Внести количество: 1",
                    "Перевести заявку в статус 'ЗАКРЫТО'"
                ] if status == "APPROVED" else ["Передать документ на ручную проверку"]
            }
        }