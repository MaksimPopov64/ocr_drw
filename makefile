.PHONY: build run stop logs clean test

# Docker сборка
build:
	docker-compose build --no-cache

# Запуск
run:
	docker-compose up -d

# Остановка
stop:
	docker-compose down

# Логи
logs:
	docker-compose logs -f

# Очистка
clean:
	docker-compose down -v
	docker system prune -f

# Тестирование
test:
	docker-compose run --rm ocr-app python -m pytest tests/

# Миграции БД
migrate:
	docker-compose exec ocr-app python manage.py db migrate
	docker-compose exec ocr-app python manage.py db upgrade

# Резервное копирование
backup:
	mkdir -p backups
	docker-compose exec -T postgres pg_dump -U ocr_user ocr_db > backups/backup_$$(date +%Y%m%d_%H%M%S).sql

# Мониторинг
monitor:
	docker stats