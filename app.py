import os
import json
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, url_for
from werkzeug.utils import secure_filename
import cv2
import numpy as np
from ocr_processor import DocumentProcessor
import uuid

app = Flask(__name__)

# Конфигурация
app.config['SECRET_KEY'] = 'your-secret-key-change-this'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['RESULT_FOLDER'] = 'results'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'pdf', 'bmp'}

# Создаем папки если их нет
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RESULT_FOLDER'], exist_ok=True)

# Инициализируем процессор документов
processor = DocumentProcessor()

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400
    
    # Генерируем уникальное имя файла
    file_id = str(uuid.uuid4())
    original_filename = secure_filename(file.filename)
    extension = original_filename.rsplit('.', 1)[1].lower()
    filename = f"{file_id}.{extension}"
    
    # Сохраняем файл
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    # Получаем ожидаемый номер заявки (если есть)
    expected_claim = request.form.get('expected_claim', '').strip()
    
    # Обрабатываем документ
    try:
        result = processor.process_document(
            filepath, 
            expected_claim_number=expected_claim if expected_claim else None
        )
        
        # Сохраняем результат
        result_filename = f"{file_id}.json"
        result_path = os.path.join(app.config['RESULT_FOLDER'], result_filename)
        
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        # Возвращаем результат
        return jsonify({
            'success': True,
            'file_id': file_id,
            'original_name': original_filename,
            'result': result
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/result/<file_id>')
def show_result(file_id):
    result_path = os.path.join(app.config['RESULT_FOLDER'], f"{file_id}.json")
    
    if not os.path.exists(result_path):
        return "Result not found", 404
    
    with open(result_path, 'r', encoding='utf-8') as f:
        result = json.load(f)
    
    return render_template('result.html', result=result, file_id=file_id)

@app.route('/download/<file_id>')
def download_result(file_id):
    result_path = os.path.join(app.config['RESULT_FOLDER'], f"{file_id}.json")
    
    if not os.path.exists(result_path):
        return "Result not found", 404
    
    return send_file(
        result_path,
        as_attachment=True,
        download_name=f"ocr_result_{file_id}.json"
    )

@app.route('/annotated/<file_id>')
def get_annotated_image(file_id):
    # Ищем файл изображения
    upload_folder = app.config['UPLOAD_FOLDER']
    image_path = None
    
    for ext in ['jpg', 'jpeg', 'png', 'bmp']:
        test_path = os.path.join(upload_folder, f"{file_id}.{ext}")
        if os.path.exists(test_path):
            image_path = test_path
            break
    
    if not image_path:
        return "Image not found", 404
    
    # Создаем аннотированное изображение
    annotated_image = processor.create_annotated_image(image_path)
    
    # Сохраняем временно
    temp_path = os.path.join(app.config['UPLOAD_FOLDER'], f"annotated_{file_id}.jpg")
    cv2.imwrite(temp_path, annotated_image)
    
    return send_file(temp_path, mimetype='image/jpeg')

@app.route('/api/check', methods=['POST'])
def api_check():
    """API endpoint для интеграции с другими системами"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type'}), 400
    
    # Сохраняем временно
    temp_path = os.path.join(app.config['UPLOAD_FOLDER'], f"temp_{uuid.uuid4()}.jpg")
    file.save(temp_path)
    
    try:
        # Получаем параметры из запроса
        expected_claim = request.form.get('expected_claim')
        
        # Обрабатываем
        result = processor.process_document(
            temp_path,
            expected_claim_number=expected_claim
        )
        
        # Очищаем временный файл
        os.remove(temp_path)
        
        return jsonify(result)
        
    except Exception as e:
        # Очищаем в случае ошибки
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({'error': str(e)}), 500

@app.route('/batch', methods=['POST'])
def batch_process():
    """Пакетная обработка нескольких файлов"""
    if 'files[]' not in request.files:
        return jsonify({'error': 'No files provided'}), 400
    
    files = request.files.getlist('files[]')
    results = []
    
    for file in files:
        if file.filename == '':
            continue
        
        if not allowed_file(file.filename):
            continue
        
        try:
            # Сохраняем временно
            file_id = str(uuid.uuid4())
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"{file_id}.jpg")
            file.save(filepath)
            
            # Обрабатываем
            result = processor.process_document(filepath)
            result['original_filename'] = file.filename
            result['file_id'] = file_id
            
            results.append(result)
            
        except Exception as e:
            results.append({
                'original_filename': file.filename,
                'error': str(e),
                'status': 'ERROR'
            })
    
    return jsonify({
        'success': True,
        'processed': len(results),
        'results': results
    })

@app.route('/history')
def get_history():
    """Получить историю обработок"""
    history = []
    result_folder = app.config['RESULT_FOLDER']
    
    for filename in os.listdir(result_folder):
        if filename.endswith('.json'):
            filepath = os.path.join(result_folder, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    file_id = filename.replace('.json', '')
                    
                    history.append({
                        'file_id': file_id,
                        'timestamp': data.get('timestamp'),
                        'claim_number': data.get('claim_number'),
                        'status': data.get('status')
                    })
            except:
                continue
    
    # Сортируем по времени (новые сначала)
    history.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    return jsonify({'history': history})

if __name__ == '__main__':
    # Для продакшена используйте waitress:
    # from waitress import serve
    # serve(app, host='0.0.0.0', port=5000)
    
    # Для разработки:
    app.run(debug=True, host='0.0.0.0', port=3000)