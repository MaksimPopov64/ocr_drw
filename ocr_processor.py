import cv2
import pytesseract
import re
import numpy as np
from pytesseract import Output
from datetime import datetime
import os
import easyocr

class DocumentProcessor:
    def __init__(self):
        # Инициализируем EasyOCR один раз (может занять несколько секунд)
        # Указываем языки: русский и английский
        print("Инициализация EasyOCR...")
        self.reader = easyocr.Reader(['ru', 'en'], gpu=False)  # gpu=True если есть видеокарта
        print("EasyOCR готов к работе.")
    
    def extract_text_easyocr(self, image_path):
        """
        Распознавание текста с помощью EasyOCR.
        Возвращает полный текст и список детализированных результатов.
        """
        # Чтение изображения
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Не удалось загрузить изображение: {image_path}")
        
        # EasyOCR сам выполняет предобработку
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        try:
            # Распознавание текста
            results = self.reader.readtext(
                img_rgb, 
                paragraph=False,  # Изменено на False для простоты
                detail=1,
                text_threshold=0.5
            )
            
            # Отладочный вывод
            print(f"EasyOCR results type: {type(results)}")
            print(f"EasyOCR results length: {len(results)}")
            if results and len(results) > 0:
                print(f"First result type: {type(results[0])}")
                print(f"First result: {results[0]}")
            
        except Exception as e:
            print(f"Ошибка при вызове EasyOCR: {e}")
            return "", []
        
        # Форматируем результаты
        full_text = ""
        text_details = []
        
        for item in results:
            try:
                # Обрабатываем разные форматы ответа EasyOCR
                if len(item) == 3:
                    # Стандартный формат: (bbox, text, confidence)
                    bbox, text, confidence = item
                elif len(item) == 2:
                    # Упрощенный формат: (text, confidence) или (bbox, text)
                    if isinstance(item[0], str):
                        text, confidence = item
                        bbox = None
                    else:
                        bbox, text = item
                        confidence = 0.0
                else:
                    # Неизвестный формат, пропускаем
                    print(f"Неизвестный формат элемента: {item}")
                    continue
                
                # Извлекаем координаты bbox, если они есть
                if bbox is not None:
                    try:
                        # bbox - это массив из 4 точек [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
                        top_left = tuple(map(int, bbox[0]))
                        bottom_right = tuple(map(int, bbox[2]))
                    except:
                        top_left = (0, 0)
                        bottom_right = (0, 0)
                else:
                    top_left = (0, 0)
                    bottom_right = (0, 0)
                
                # Добавляем текст
                full_text += text + "\n"
                text_details.append({
                    'text': text,
                    'confidence': float(confidence) if confidence else 0.0,
                    'bbox': [top_left, bottom_right]
                })
                
            except Exception as e:
                print(f"Ошибка обработки элемента {item}: {e}")
                continue
        
        return full_text.strip(), text_details
    
    def parse_document_easyocr(self, text, details):
        """
        Парсинг распознанного текста с учетом структуры документа.
        """
        result = {
            'claim_number': None,
            'equipment_model': None,
            'cartridge_model': None,
            'page_count': None,
            'customer_name': None,
            'nomenclature': None,
            'quantity': 1
        }
        
        # Ищем номер заявки по различным шаблонам
        claim_patterns = [
            r'заявки?[^\d\n№]*[№\s]*(\d{6,10})',
            r'№\s*(\d{6,10})',
            r'акт.*?(\d{6,10})',
            r'(\d{6,10})'  # Просто ищем последовательность из 6-10 цифр
        ]
        
        for pattern in claim_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result['claim_number'] = match.group(1)
                break
        
        # Ищем модель оборудования (HP и т.д.)
        if 'HP' in text.upper():
            lines = text.split('\n')
            for line in lines:
                if 'HP' in line.upper():
                    result['equipment_model'] = line.strip()
                    break
        
        # Ищем модель картриджа
        cartridge_match = re.search(r'CE\d+[A-Z]?', text)
        if cartridge_match:
            result['cartridge_model'] = cartridge_match.group(0)
            result['nomenclature'] = f"Картридж {cartridge_match.group(0)}"
        
        return result
        
    def preprocess_image(self, image_path):
        """
        Предобработка изображения
        """
        # Загружаем изображение
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Не удалось загрузить изображение: {image_path}")
        
        # Сохраняем оригинал для аннотаций
        original = img.copy()
        
        # Изменяем размер для лучшей обработки
        height, width = img.shape[:2]
        if width > 2000:
            scale = 2000 / width
            new_width = 2000
            new_height = int(height * scale)
            img = cv2.resize(img, (new_width, new_height))
        
        # Преобразуем в оттенки серого
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Улучшаем контраст
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        
        # Применяем адаптивное пороговое преобразование
        thresh = cv2.adaptiveThreshold(
            enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 11, 2
        )
        
        # Удаляем шум
        kernel = np.ones((2, 2), np.uint8)
        processed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        processed = cv2.medianBlur(processed, 3)

        kernel_sharpen = np.array([[-1, -1, -1],
                            [-1,  9, -1],
                            [-1, -1, -1]])
        processed = cv2.filter2D(processed, -1, kernel_sharpen)

        # Удаление мелкого шума (пикселей-одиночек)
        kernel_clean = np.ones((1,1), np.uint8)
        processed = cv2.morphologyEx(processed, cv2.MORPH_OPEN, kernel_clean)
        
        return original, img, processed
    
    def extract_text_with_boxes(self, image):
        """
        Извлечение текста с координатами bounding boxes
        """
        # Получаем данные OCR
        data = pytesseract.image_to_data(
            image, 
            config=self.ocr_config, 
            output_type=Output.DICT
        )
        
        # Извлекаем текст
        text = pytesseract.image_to_string(image, config=self.ocr_config)
        
        return text, data
    
    def find_signature_area(self, image):
        """
        Поиск области с подписью
        """
        height, width = image.shape[:2]
        
        # Определяем нижнюю часть изображения (30%)
        bottom_start = int(height * 0.7)
        bottom_area = image[bottom_start:height, 0:width]
        
        # Ищем горизонтальные линии (под чертой для подписи)
        edges = cv2.Canny(bottom_area, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(
            edges, 
            1, 
            np.pi/180, 
            threshold=50, 
            minLineLength=100, 
            maxLineGap=10
        )
        
        has_signature_line = False
        signature_y = height
        
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                # Горизонтальные линии
                if abs(y2 - y1) < 10 and abs(x2 - x1) > 200:
                    has_signature_line = True
                    signature_y = bottom_start + min(y1, y2)
                    break
        
        # Ищем текст в области подписи
        if has_signature_line:
            signature_area = image[signature_y:height, 0:width]
            
            # Проверяем наличие текста в этой области
            signature_text = pytesseract.image_to_string(
                signature_area, 
                config=self.ocr_config
            )
            
            # Подпись обычно содержит мало текста или рукописный текст
            # Проверяем по характерным словам
            signature_keywords = ['подпись', 'signature', 'исполнитель', 'заказчик', 'клиент']
            has_signature_text = any(
                keyword in signature_text.lower() 
                for keyword in signature_keywords
            )
            
            return has_signature_line or has_signature_text
        
        return False
    
    def find_stamp_area(self, image):
        """
        Поиск круглой печати
        """
        # Преобразуем в оттенки серого
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # Улучшаем контраст для поиска кругов
        enhanced = cv2.equalizeHist(gray)
        
        # Детектируем круги
        circles = cv2.HoughCircles(
            enhanced,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=100,
            param1=100,
            param2=30,
            minRadius=30,
            maxRadius=100
        )
        
        return circles is not None
    
    def parse_document_text(self, text, ocr_data):
        """
        Парсинг извлеченного текста
        """
        result = {
            'claim_number': None,
            'equipment_model': None,
            'cartridge_model': None,
            'page_count': None,
            'work_type': None,
            'service_date': None,
            'customer_name': None,
            'nomenclature': None,
            'quantity': 1,
            'signature_status': 'NOT_FOUND',
            'stamp_status': 'NOT_FOUND'
        }
        
        # 1. Поиск номера заявки
        patterns = [
            r'заявки?[^\d\n№]*[№\s]*(\d{6,10})',
            r'№\s*(\d{6,10})',
            r'акт.*?(\d{6,10})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result['claim_number'] = match.group(1)
                break
        
        # 2. Поиск модели оборудования
        equipment_patterns = [
            r'HP\s+(?:LJ\s+)?(?:P\d+|M\d+|1214)[^\s]*',
            r'модель[:\s]*([^\n]+)',
            r'оборудован[ия]?[:\s]*([^\n]+)'
        ]
        
        for pattern in equipment_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result['equipment_model'] = match.group(0).strip()
                break
        
        # 3. Поиск картриджа
        cartridge_match = re.search(r'CE\d+[A-Z]?', text)
        if cartridge_match:
            result['cartridge_model'] = cartridge_match.group(0)
            result['nomenclature'] = f"Картридж {cartridge_match.group(0)}"
        
        # 4. Количество страниц
        page_match = re.search(r'страниц[^\d]*(\d+)', text, re.IGNORECASE)
        if page_match:
            result['page_count'] = int(page_match.group(1))
        
        # 5. Тип работ
        work_types = ['Осмотр', 'Инсталляция', 'ТО1', 'ТО2', 'ТО3', 'Ремонт', 'Доставка']
        for work_type in work_types:
            if work_type in text:
                result['work_type'] = work_type
                break
        
        # 6. Дата
        date_match = re.search(r'\d{2}\.\d{2}\.\d{4}', text)
        if date_match:
            result['service_date'] = date_match.group(0)
        
        # 7. Заказчик
        customer_match = re.search(r'Заказчик[:\s]*([^\n]+)', text, re.IGNORECASE)
        if customer_match:
            result['customer_name'] = customer_match.group(1).strip()
        
        return result
    
    def check_requirements(self, parsed_data, expected_claim_number=None):
        """
        Проверка требований к документу
        """
        issues = []
        warnings = []
        
        # 1. Проверка номера заявки
        if expected_claim_number and parsed_data['claim_number']:
            if parsed_data['claim_number'] != expected_claim_number:
                issues.append({
                    'code': 'CLAIM_MISMATCH',
                    'message': f'Номер заявки не совпадает. Ожидалось: {expected_claim_number}, найдено: {parsed_data["claim_number"]}',
                    'severity': 'ERROR'
                })
        
        if not parsed_data['claim_number']:
            warnings.append({
                'code': 'CLAIM_NOT_FOUND',
                'message': 'Номер заявки не найден в документе',
                'severity': 'WARNING'
            })
        
        # 2. Проверка модели оборудования
        if not parsed_data['equipment_model']:
            issues.append({
                'code': 'MODEL_NOT_FOUND',
                'message': 'Модель оборудования не найдена',
                'severity': 'ERROR'
            })
        
        # 3. Проверка номенклатуры
        if not parsed_data['nomenclature']:
            issues.append({
                'code': 'NOMENCLATURE_NOT_FOUND',
                'message': 'Номенклатура (картридж) не найдена',
                'severity': 'ERROR'
            })
        
        # 4. Проверка подписи
        if parsed_data['signature_status'] != 'FOUND':
            issues.append({
                'code': 'SIGNATURE_NOT_FOUND',
                'message': 'Подпись клиента не обнаружена',
                'severity': 'ERROR'
            })
        
        # 5. Проверка печати
        if parsed_data['stamp_status'] != 'FOUND':
            warnings.append({
                'code': 'STAMP_NOT_FOUND',
                'message': 'Печать клиента не обнаружена',
                'severity': 'WARNING'
            })
        
        # Определяем общий статус
        has_errors = any(issue['severity'] == 'ERROR' for issue in issues)
        has_warnings = any(warning['severity'] == 'WARNING' for warning in warnings)
        
        if has_errors:
            status = 'REJECTED'
        elif has_warnings:
            status = 'NEEDS_REVIEW'
        else:
            status = 'APPROVED'
        
        return {
            'status': status,
            'issues': issues,
            'warnings': warnings,
            'decision': self.get_decision(status, parsed_data)
        }
    
    def get_decision(self, status, parsed_data):
        """
        Формирование решения на основе статуса
        """
        if status == 'APPROVED':
            return {
                'action': 'CLOSE_CLAIM',
                'message': 'Все проверки пройдены. Заявку можно закрыть.',
                'steps': [
                    f'Внести номенклатуру: {parsed_data.get("nomenclature", "N/A")}',
                    f'Внести количество: {parsed_data.get("quantity", 1)}',
                    'Перевести заявку в статус "ЗАКРЫТО"'
                ]
            }
        elif status == 'NEEDS_REVIEW':
            return {
                'action': 'REVIEW_REQUIRED',
                'message': 'Требуется ручная проверка некоторых пунктов',
                'steps': ['Передать документ на ручную проверку']
            }
        else:  # REJECTED
            return {
                'action': 'RETURN_FOR_CORRECTION',
                'message': 'Документ не прошел проверку. Требуется доработка.',
                'steps': ['Вернуть документ сотруднику для исправления']
            }
    
    def create_annotated_image(self, image_path):
        """
        Создание аннотированного изображения с выделенными областями
        """
        original, img, processed = self.preprocess_image(image_path)
        annotated = original.copy()
        
        # Извлекаем данные OCR с bounding boxes
        text, ocr_data = self.extract_text_with_boxes(processed)
        
        # Рисуем bounding boxes для текста
        n_boxes = len(ocr_data['text'])
        for i in range(n_boxes):
            if int(ocr_data['conf'][i]) > 60:  # Только уверенные распознавания
                (x, y, w, h) = (
                    ocr_data['left'][i], 
                    ocr_data['top'][i], 
                    ocr_data['width'][i], 
                    ocr_data['height'][i]
                )
                cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 255, 0), 2)
        
        # Ищем и отмечаем область подписи
        height, width = annotated.shape[:2]
        signature_rect = (0, int(height * 0.7), width, int(height * 0.3))
        cv2.rectangle(
            annotated, 
            (signature_rect[0], signature_rect[1]),
            (signature_rect[0] + signature_rect[2], signature_rect[1] + signature_rect[3]),
            (255, 0, 0), 
            3
        )
        cv2.putText(
            annotated, 
            'Область подписи', 
            (signature_rect[0], signature_rect[1] - 10),
            cv2.FONT_HERSHEY_SIMPLEX, 
            0.7, 
            (255, 0, 0), 
            2
        )
        
        # Добавляем метки
        cv2.putText(
            annotated, 
            'Распознанный текст выделен зеленым', 
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 
            0.7, 
            (0, 255, 0), 
            2
        )
        
        cv2.putText(
            annotated, 
            'Область поиска подписи выделена синим', 
            (10, 60),
            cv2.FONT_HERSHEY_SIMPLEX, 
            0.7, 
            (255, 0, 0), 
            2
        )
        
        return annotated
    
    def find_signature_by_features(self, image):
        """
        Ищет подпись, находя контур с высокой детализацией (много углов/ключевых точек).
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Детектор углов (например, метод Харриса) найдет много точек в зоне подписи
        corners = cv2.cornerHarris(gray, 2, 3, 0.04)
        corners = cv2.dilate(corners, None)
        
        # Порог для выделения значительных углов
        _, corners_thresh = cv2.threshold(corners, 0.01 * corners.max(), 255, 0)
        corners_thresh = np.uint8(corners_thresh)
        
        # Находим контуры этих точек
        contours, _ = cv2.findContours(corners_thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Фильтруем контуры: подпись обычно компактная, но с высокой плотностью точек
        signature_contours = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            aspect_ratio = w / float(h)
            area = cv2.contourArea(cnt)
            
            # Критерии для подписи: не слишком большая/маленькая, не идеально прямоугольная
            if (area > 500 and area < 5000 and 
                aspect_ratio > 0.5 and aspect_ratio < 3.0):
                # Оцениваем "сложность" контура
                if len(cnt) > 20:  # Контур с большим количеством точек = детализированный
                    signature_contours.append(cnt)
        
        return len(signature_contours) > 0



    def find_stamp_by_color(self, image):
        """
        Ищет круглые объекты красного цвета.
        """
        # Преобразуем в цветовое пространство HSV для лучшего выделения цвета
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        
        # Диапазоны красного цвета в HSV (красный находится у границы hue)
        lower_red1 = np.array([0, 70, 50])
        upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([170, 70, 50])
        upper_red2 = np.array([180, 255, 255])
        
        mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
        mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
        red_mask = cv2.bitwise_or(mask1, mask2)
        
        # Очищаем маску
        kernel = np.ones((5,5), np.uint8)
        red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, kernel)
        red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, kernel)
        
        # Ищем контуры
        contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 500:  # Слишком маленький объект
                continue
            
            # Проверяем, насколько контур близок к кругу
            perimeter = cv2.arcLength(cnt, True)
            if perimeter == 0:
                continue
            
            circularity = 4 * np.pi * area / (perimeter * perimeter)
            # circularity ~1.0 для идеального круга
            if circularity > 0.6:
                return True
        
        return False
    
    def detect_signature_advanced(self, image):
        """
        Улучшенный метод обнаружения подписи.
        Комбинирует несколько подходов.
        """
        # 1. Ищем текст в нижней части документа
        height, width = image.shape[:2]
        bottom_region = image[int(height*0.7):height, 0:width]
        
        # Пробуем распознать текст в этой области
        bottom_rgb = cv2.cvtColor(bottom_region, cv2.COLOR_BGR2RGB)
        results = self.reader.readtext(bottom_rgb, detail=0)
        bottom_text = ' '.join(results).lower()
        
        # Ключевые слова, указывающие на область подписи
        signature_keywords = ['подпись', 'signature', 'исполнитель', 'заказчик', 'клиент']
        has_signature_keyword = any(keyword in bottom_text for keyword in signature_keywords)
        
        # 2. Анализ текстурных особенностей (подпись имеет уникальную текстуру)
        gray = cv2.cvtColor(bottom_region, cv2.COLOR_BGR2GRAY)
        
        # Вычисляем меру "рукописности" через анализ градиентов
        sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        gradient_magnitude = np.sqrt(sobelx**2 + sobely**2)
        
        # Высокая вариация градиентов характерна для подписи
        gradient_variance = np.var(gradient_magnitude)
        has_high_variance = gradient_variance > 1000  # Эмпирический порог
        
        # 3. Поиск характерных контуров
        edges = cv2.Canny(gray, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        signature_like_contours = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if 500 < area < 5000:  # Подпись обычно среднего размера
                perimeter = cv2.arcLength(contour, True)
                if perimeter == 0:
                    continue
                    
                # Коэффициент компактности (подпись менее компактна, чем печать)
                compactness = 4 * np.pi * area / (perimeter * perimeter)
                if compactness < 0.5:  # Не круглый объект
                    signature_like_contours.append(contour)
        
        has_contours = len(signature_like_contours) > 0
        
        # Итоговое решение (можно комбинировать условия)
        return has_signature_keyword or (has_high_variance and has_contours)
    
    def detect_stamp_advanced(self, image):
        """
        Улучшенный метод обнаружения печати.
        Ищет круглые объекты красного/синего цвета.
        """
        # 1. Цветовая сегментация
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        
        # Диапазоны для красного цвета (печати часто красные)
        lower_red1 = np.array([0, 70, 50])
        upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([170, 70, 50])
        upper_red2 = np.array([180, 255, 255])
        
        mask_red1 = cv2.inRange(hsv, lower_red1, upper_red1)
        mask_red2 = cv2.inRange(hsv, lower_red2, upper_red2)
        red_mask = cv2.bitwise_or(mask_red1, mask_red2)
        
        # Диапазоны для синего цвета
        lower_blue = np.array([100, 70, 50])
        upper_blue = np.array([130, 255, 255])
        blue_mask = cv2.inRange(hsv, lower_blue, upper_blue)
        
        # Объединяем маски
        color_mask = cv2.bitwise_or(red_mask, blue_mask)
        
        # Очистка маски
        kernel = np.ones((5, 5), np.uint8)
        color_mask = cv2.morphologyEx(color_mask, cv2.MORPH_CLOSE, kernel)
        color_mask = cv2.morphologyEx(color_mask, cv2.MORPH_OPEN, kernel)
        
        # 2. Поиск круглых контуров
        contours, _ = cv2.findContours(color_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < 300:  # Слишком маленький объект
                continue
            
            # Проверка на округлость
            perimeter = cv2.arcLength(contour, True)
            if perimeter == 0:
                continue
            
            circularity = 4 * np.pi * area / (perimeter * perimeter)
            
            # Круглые печати имеют circularity близкую к 1
            if circularity > 0.6:
                # Дополнительная проверка: печать обычно имеет текст по окружности
                # Можно добавить проверку наличия текста внутри области
                return True
        
        # 3. Если не нашли по цвету, ищем по форме (черно-белые печати)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # Ищем круги с помощью преобразования Хафа
        circles = cv2.HoughCircles(binary, cv2.HOUGH_GRADIENT, dp=1.2, 
                                   minDist=100, param1=50, param2=30, 
                                   minRadius=20, maxRadius=100)
        
        return circles is not None and len(circles[0]) > 0
    
    def process_document_improved(self, image_path, expected_claim_number=None):
        """
        Улучшенная обработка документа с EasyOCR.
        """
        try:
            # 1. Распознаем текст с помощью EasyOCR
            print(f"Начинаем обработку документа: {image_path}")
            
            # Пробуем оба метода на случай ошибок
            try:
                full_text, text_details = self.extract_text_easyocr(image_path)
            except Exception as e:
                print(f"Первый метод не сработал: {e}")
                full_text, text_details = self.extract_text_easyocr_simple(image_path)
            
            print(f"Распознанный текст (первые 500 символов): {full_text[:500]}")
            
            # 2. Парсим данные
            parsed_data = self.parse_document_easyocr(full_text, text_details)
            parsed_data['full_text'] = full_text
            
            # 3. Ищем подпись и печать
            img = cv2.imread(image_path)
            
            # Обнаружение подписи
            try:
                has_signature = self.detect_signature_advanced(img)
                parsed_data['signature_status'] = 'FOUND' if has_signature else 'NOT_FOUND'
            except Exception as e:
                print(f"Ошибка детекции подписи: {e}")
                parsed_data['signature_status'] = 'NOT_FOUND'
            
            # Обнаружение печати
            try:
                has_stamp = self.detect_stamp_advanced(img)
                parsed_data['stamp_status'] = 'FOUND' if has_stamp else 'NOT_FOUND'
            except Exception as e:
                print(f"Ошибка детекции печати: {e}")
                parsed_data['stamp_status'] = 'NOT_FOUND'
            
            # 4. Проверяем требования
            check_result = self.check_requirements(parsed_data, expected_claim_number)
            
            # 5. Формируем результат
            result = {
                'timestamp': datetime.now().isoformat(),
                'filename': os.path.basename(image_path),
                'parsed_data': parsed_data,
                'check_result': check_result,
                'ocr_engine': 'EasyOCR',
                'text_details': text_details[:5] if text_details else []
            }
            
            result['status'] = check_result['status']
            
            return result
            
        except Exception as e:
            print(f"Критическая ошибка в process_document_improved: {e}")
            return {
                'error': f'Ошибка обработки документа: {str(e)}',
                'status': 'ERROR',
                'timestamp': datetime.now().isoformat()
            }
        
