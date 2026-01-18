import os
import json
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, url_for
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename
import cv2
import numpy as np
from qwen_processor import QwenOCRProcessor as OCRProcessor
import uuid

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Настройка лимитера
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# Конфигурация
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'your-secret-key-change-this')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['RESULT_FOLDER'] = 'results'
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32MB
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'pdf', 'bmp', 'tiff'}
app.config['OLLAMA_URL'] = os.environ.get('OLLAMA_URL', 'http://localhost:11434')

# Создаем папки
for folder in [app.config['UPLOAD_FOLDER'], app.config['RESULT_FOLDER']]:
    os.makedirs(folder, exist_ok=True)

# Инициализируем процессор
try:
    processor = OCRProcessor(
        ollama_url=app.config['OLLAMA_URL'],
        model=os.environ.get('OLLAMA_MODEL', 'qwen2.5-vl:7b')
    )
    logger.info("✅ Qwen2.5-VL OCR Processor initialized")
except Exception as e:
    logger.error(f"❌ Ошибка инициализации процессора: {e}")
    processor = None

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Health check endpoint
@app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "OCR System",
        "version": "1.0.0"
    })

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
@app.route('/upload_mistral', methods=['POST'])
@limiter.limit("10 per minute")
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400
    
    if not processor:
        return jsonify({'error': 'OCR processor not available'}), 500
    
    # Генерируем уникальное имя файла
    file_id = str(uuid.uuid4())
    original_filename = secure_filename(file.filename)
    extension = original_filename.rsplit('.', 1)[1].lower()
    filename = f"{file_id}.{extension}"
    
    # Сохраняем файл
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    # Получаем ожидаемый номер заявки
    expected_claim = request.form.get('expected_claim', '').strip()
    
    try:
        logger.info(f"Processing document: {original_filename}")
        
        result = processor.process_document(
            filepath, 
            expected_claim_number=expected_claim if expected_claim else None
        )
        
        # Сохраняем результат
        result_filename = f"{file_id}.json"
        result_path = os.path.join(app.config['RESULT_FOLDER'], result_filename)
        
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Document processed successfully: {file_id}")
        
        return jsonify({
            'success': True,
            'file_id': file_id,
            'original_name': original_filename,
            'result': result
        })
        
    except Exception as e:
        logger.error(f"Error processing document: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/result/<file_id>')
def show_result(file_id):
    result_path = os.path.join(app.config['RESULT_FOLDER'], f"{file_id}.json")
    
    if not os.path.exists(result_path):
        return render_template('error.html', message="Result not found"), 404
    
    try:
        with open(result_path, 'r', encoding='utf-8') as f:
            result = json.load(f)
        
        return render_template('result.html', result=result, file_id=file_id)
        
    except Exception as e:
        logger.error(f"Error loading result: {e}")
        return render_template('error.html', message="Error loading result"), 500

@app.route('/download/<file_id>')
def download_result(file_id):
    result_path = os.path.join(app.config['RESULT_FOLDER'], f"{file_id}.json")
    
    if not os.path.exists(result_path):
        return "Result not found", 404
    
    return send_file(
        result_path,
        as_attachment=True,
        download_name=f"ocr_result_{file_id}.json",
        mimetype='application/json'
    )

@app.route('/api/batch', methods=['POST'])
@limiter.limit("5 per minute")
def batch_process():
    """Пакетная обработка"""
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

@app.route('/api/models')
def get_models():
    """Получить список доступных моделей"""
    try:
        import requests
        response = requests.get(f"{app.config['OLLAMA_URL']}/api/tags")
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({'error': 'Failed to get models'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/history')
def get_history():
    """Получить историю обработанных документов"""
    try:
        history = []
        result_folder = app.config['RESULT_FOLDER']
        
        if os.path.exists(result_folder):
            # Читаем все файлы результатов
            for filename in sorted(os.listdir(result_folder), reverse=True):
                if filename.endswith('.json'):
                    file_id = filename.replace('.json', '')
                    filepath = os.path.join(result_folder, filename)
                    
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        # Извлекаем нужные данные
                        parsed = data.get('parsed_data', {})
                        check = data.get('check_result', {})
                        
                        history_item = {
                            'file_id': file_id,
                            'timestamp': data.get('timestamp'),
                            'claim_number': parsed.get('claim_number'),
                            'status': check.get('status', 'UNKNOWN'),
                            'filename': data.get('filename')
                        }
                        history.append(history_item)
                    except Exception as e:
                        logger.warning(f"Error reading result file {filename}: {e}")
                        continue
        
        return jsonify({'history': history})
    except Exception as e:
        logger.error(f"Error loading history: {e}")
        return jsonify({'error': str(e), 'history': []}), 500

@app.route('/favicon.ico')
def favicon():
    """Favicon endpoint"""
    return '', 204

@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', message="Page not found"), 404

@app.errorhandler(500)
def server_error(error):
    return render_template('error.html', message="Internal server error"), 500

if __name__ == '__main__':
    # В production используем gunicorn
    app.run(host='0.0.0.0', port=5000, debug=False)