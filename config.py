import os
from dotenv import load_dotenv
# Импортируем torch НЕ на уровне модуля, чтобы избежать ошибок инициализации
# import torch  # <-- Закомментируйте или удалите эту строку!

load_dotenv()

class Config:
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', 'ocr-app-secret-key')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    UPLOAD_FOLDER = 'uploads'
    PROCESSED_FOLDER = 'processed'
    BOTTOM_REGION_RATIO = 0.3        # Доля нижней части изображения для поиска (30%)
    MIN_CONTOUR_AREA = 0.0005        # Минимальная площадь контура (0.05% от площади изображения)
    MAX_CONTOUR_AREA = 0.05
    
    # Модель Qwen
    MODEL_NAME = os.environ.get('MODEL_NAME', 'Qwen/Qwen2.5-VL-3B-Instruct')
    
    # ОБНОВЛЕНО: Функция для безопасного определения устройства
    @staticmethod
    def get_device():
        """Безопасно определяет доступное устройство для PyTorch."""
        try:
            import torch
            
            # 1. Сначала проверяем, задано ли устройство через переменную окружения
            env_device = os.environ.get('DEVICE', '').lower()
            if env_device in ['cuda', 'mps', 'cpu']:
                # Проверяем доступность запрошенного через окружение устройства
                if env_device == 'cuda' and torch.cuda.is_available():
                    return 'cuda'
                elif env_device == 'mps' and hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                    return 'mps'
                else:
                    return 'cpu'  # Если заданное через env устройство недоступно, отступаем на CPU
            # 2. Если переменная окружения не задана, автоматически определяем лучшее доступное
            if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                return 'mps'  # Приоритет для Apple Silicon
            elif torch.cuda.is_available():
                return 'cuda' # Для машин с NVIDIA GPU
            else:
                return 'cpu'
        except ImportError:
            # Если torch не установлен (маловероятно в нашем случае)
            return 'cpu'
    
    # Используем свойство или вызовем функцию позже. Для простоты зададим DEVICE строкой.
    # Мы зададим его после определения класса, чтобы использовать метод.
    
    # Предобработка
    TARGET_HEIGHT = 2000
    ENABLE_PREPROCESSING = True

# Инициализируем DEVICE после определения класса, безопасно вызывая метод
config = Config()
config.DEVICE = 'cpu'  # Явно используем CPU
config.TORCH_DTYPE = 'float32'  # Для CPU используем float32
config.MAX_NEW_TOKENS = 512