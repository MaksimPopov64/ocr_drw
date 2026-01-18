#!/usr/bin/env python3
"""
Скрипт для проверки здоровья системы
"""
import sys
import requests
import time

def check_ollama():
    """Проверка доступности Ollama"""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            print("✅ Ollama доступен")
            return True
    except Exception as e:
        print(f"❌ Ollama не доступен: {e}")
        return False

def check_flask():
    """Проверка доступности Flask"""
    try:
        response = requests.get("http://localhost:5000/health", timeout=5)
        if response.status_code == 200:
            print("✅ Flask доступен")
            return True
    except Exception as e:
        print(f"❌ Flask не доступен: {e}")
        return False

def check_disk_space():
    """Проверка свободного места на диске"""
    import shutil
    
    total, used, free = shutil.disk_usage("/")
    free_gb = free // (2**30)
    
    print(f"💾 Свободное место: {free_gb} GB")
    
    if free_gb < 5:
        print("⚠️  Мало свободного места на диске")
        return False
    return True

def check_gpu():
    """Проверка доступности GPU"""
    try:
        import torch
        if torch.cuda.is_available():
            print(f"🎮 GPU доступен: {torch.cuda.get_device_name(0)}")
            return True
        else:
            print("ℹ️  GPU не доступен, используется CPU")
            return True
    except ImportError:
        print("ℹ️  PyTorch не установлен, GPU проверка пропущена")
        return True

def main():
    """Основная функция проверки здоровья"""
    print("🔍 Проверка здоровья системы...")
    
    checks = [
        ("Ollama", check_ollama),
        ("Flask", check_flask),
        ("Disk Space", check_disk_space),
        ("GPU", check_gpu)
    ]
    
    all_ok = True
    for name, check_func in checks:
        print(f"\n📋 Проверка {name}...")
        if not check_func():
            all_ok = False
    
    if all_ok:
        print("\n✅ Все системы работают нормально")
        sys.exit(0)
    else:
        print("\n❌ Обнаружены проблемы")
        sys.exit(1)

if __name__ == "__main__":
    main()