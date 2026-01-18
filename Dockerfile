# Многоступенчатая сборка для уменьшения размера
FROM python:3.12-slim as builder

# Устанавливаем системные зависимости для сборки
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    wget \
    curl \
    git \
    build-essential \
    ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Устанавливаем Python зависимости
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Финальный образ
FROM python:3.12-slim

# Устанавливаем системные зависимости
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    wget \
    curl \
    supervisor \
    nginx \
    libgl1 \
    libglib2.0-0t64 \
    libsm6 \
    libxext6 \
    libxrender1 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Копируем Python зависимости
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /app/requirements.txt .

# Копируем код приложения
COPY . .

# Копируем конфигурационные файлы
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY nginx.conf /etc/nginx/sites-available/default
COPY entrypoint.sh /entrypoint.sh

# Настраиваем права
RUN chmod +x /entrypoint.sh && \
    mkdir -p /app/uploads /app/results /var/log/supervisor && \
    chown -R www-data:www-data /app/uploads /app/results

# Открываем порты
EXPOSE 80 11434

# Переменные окружения
ENV OLLAMA_HOST=0.0.0.0
ENV OLLAMA_KEEP_ALIVE=24h
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Точка входа
ENTRYPOINT ["/entrypoint.sh"]