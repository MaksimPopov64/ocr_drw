#!/bin/bash
set -e

echo "🚀 Запуск OCR системы..."

# Создаем необходимые директории
mkdir -p /app/uploads /app/results /var/log/supervisor

# Настраиваем права
chown -R www-data:www-data /app/uploads /app/results

# Получаем URL Ollama из переменной окружения
OLLAMA_URL=${OLLAMA_URL:-http://ollama:11434}
echo "🔗 Ollama URL: $OLLAMA_URL"

# Ждем запуска Ollama
echo "⏳ Ожидание запуска Ollama..."
timeout=120
counter=0

while ! curl -s "$OLLAMA_URL/api/tags" > /dev/null 2>&1; do
    sleep 2
    counter=$((counter + 2))
    if [ $counter -ge $timeout ]; then
        echo "⚠️  Ollama недоступна, но продолжаем (модели должны быть загружены отдельно)"
        break
    fi
    echo "⏳ Ожидание Ollama... ($counter/$timeout сек)"
done

if curl -s "$OLLAMA_URL/api/tags" > /dev/null 2>&1; then
    echo "✅ Ollama запущена и доступна!"
    
    # Проверяем наличие нужных моделей и загружаем их в фоне, если требуется
    echo "📦 Проверка моделей..."
    
    # Функция для загрузки модели в фоне (не блокирует запуск)
    load_model_async() {
        local model=$1
        local model_name=$2
        (
            echo "📥 Загружаем модель $model в фоне..."
            curl -X POST "$OLLAMA_URL/api/pull" -d "{\"name\":\"$model\"}" -H "Content-Type: application/json" > /dev/null 2>&1 && \
            echo "✅ Модель $model загружена" || \
            echo "⚠️  Не удалось загрузить $model - используется резервное решение"
        ) &
    }
    
    # Проверяем llava (для OCR)
    if ! curl -s "$OLLAMA_URL/api/tags" | grep -q "llava"; then
        load_model_async "llava:7b" "llava"
    else
        echo "✅ Модель llava уже загружена"
    fi
    
    # Проверяем mistral (для анализа)
    if ! curl -s "$OLLAMA_URL/api/tags" | grep -q "mistral"; then
        load_model_async "mistral:7b" "mistral"
    else
        echo "✅ Модель mistral уже загружена"
    fi
fi

# Инициализируем базу данных (если используется)
# Note: init_db.py is actually the Flask app, not a DB init script
# if [ -f /app/init_db.py ]; then
#     echo "🗄️  Инициализация базы данных..."
#     python /app/init_db.py || echo "⚠️  Инициализация БД не требуется"
# fi

# Запускаем миграции (если есть)
if [ -f /app/manage.py ]; then
    echo "🔄 Применение миграций..."
    python /app/manage.py db upgrade || echo "⚠️  Миграции не требуются"
fi

# Запускаем супервизор
echo "🚦 Запуск всех сервисов..."
exec supervisord -c /etc/supervisor/conf.d/supervisord.conf