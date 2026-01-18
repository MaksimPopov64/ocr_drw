#!/usr/bin/env python3
import sys
import requests

def test_ollama_connection():
    """Тестирование подключения к Ollama"""
    print("🔍 Проверка подключения к Ollama...")
    
    try:
        # Проверка доступности сервера
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        
        if response.status_code == 200:
            models = response.json().get("models", [])
            print("✅ Ollama доступен!")
            print("📦 Доступные модели:")
            for model in models:
                print(f"   - {model['name']} ({model.get('size', 'N/A')})")
            
            # Проверка наличия нужных моделей
            required_models = ["mistral", "llava"]
            available = [m["name"] for m in models]
            
            for req in required_models:
                if any(req in m for m in available):
                    print(f"✅ Модель с '{req}' доступна")
                else:
                    print(f"⚠️  Модель с '{req}' не найдена")
                    print(f"   Установите: ollama pull {req}:7b")
            
            # Тестовый запрос
            print("\n🧪 Тестовый запрос к модели...")
            test_payload = {
                "model": available[0] if available else "mistral:7b",
                "prompt": "Привет! Ответь коротко.",
                "stream": False
            }
            
            response = requests.post(
                "http://localhost:11434/api/generate",
                json=test_payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Модель отвечает: {result.get('response', '')[:50]}...")
            else:
                print(f"❌ Ошибка запроса: {response.status_code}")
        
        else:
            print(f"❌ Ollama не доступен (код: {response.status_code})")
            
    except requests.ConnectionError:
        print("❌ Не удалось подключиться к Ollama")
        print("   Убедитесь, что Ollama запущен:")
        print("   1. Откройте терминал")
        print("   2. Выполните: ollama serve")
        print("   3. В другом терминале: ollama pull mistral:7b")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

def check_system_resources():
    """Проверка системных ресурсов"""
    import psutil
    
    print("\n💻 Проверка системных ресурсов...")
    
    # Память
    memory = psutil.virtual_memory()
    print(f"   Оперативная память: {memory.percent}% использовано")
    print(f"   Доступно: {memory.available / (1024**3):.1f} GB")
    
    # CPU
    cpu_count = psutil.cpu_count(logical=False)
    print(f"   CPU ядер: {cpu_count}")
    
    # Рекомендации
    if memory.available < 4 * 1024**3:  # Меньше 4GB
        print("⚠️  Мало оперативной памяти для работы моделей")
        print("   Рекомендуется минимум 8GB RAM")
    
    if cpu_count < 4:
        print("⚠️  Маловато CPU ядер для быстрой обработки")

if __name__ == "__main__":
    print("=" * 60)
    print("Проверка системы для работы Mistral OCR")
    print("=" * 60)
    
    test_ollama_connection()
    check_system_resources()
    
    print("\n" + "=" * 60)
    print("Инструкция по установке:")
    print("1. Установите Ollama: https://ollama.ai")
    print("2. Скачайте модели: ollama pull mistral:7b")
    print("3. Для работы с изображениями: ollama pull llava:7b")
    print("4. Запустите сервер: ollama serve")
    print("5. Запустите Flask приложение: python app.py")
    print("=" * 60)