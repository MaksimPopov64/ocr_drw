# 🚀 Quick Start Guide - OCR System

## System Requirements

- Docker 20.10+
- Docker Compose 2.0+
- 8GB+ RAM (16GB+ recommended for Ollama)
- 15GB+ free disk space (for Ollama models)

## Setup Instructions

### 1. **Configure Environment** 
```bash
# Copy example env file
cp .env.example .env

# Edit .env with your secure values
nano .env
```

### 2. **Build Docker Images**
```bash
make build
```

This will:
- Download Python 3.11 slim base image (~150MB)
- Build application image (~500MB)
- Pull official Ollama image (~5GB first time only)

**Build time:** ~5-10 minutes (first time), ~2-3 minutes (subsequent)

### 3. **Start All Services**
```bash
make run
```

Services will start in order:
1. **Ollama** - AI model service (11434)
2. **ocr-app** - Flask web application (8080)
3. **PostgreSQL** - Database (5432) 
4. **Redis** - Cache (6379)

⏳ **Startup time:** ~1-2 minutes (Ollama models already cached)

### 4. **Access the Application**

Open your browser:
```
http://localhost:8080
```

### 5. **Check Service Status**
```bash
# View all running containers
docker-compose ps

# View logs for all services
docker-compose logs -f

# View logs for specific service
docker-compose logs -f ocr-app
docker-compose logs -f ollama
```

## Common Operations

### Stop Services
```bash
make stop
```

### View Logs
```bash
# All services
make logs

# Specific service
docker-compose logs -f ocr-app
```

### Download Ollama Models Manually
```bash
# List available models
docker-compose exec ollama ollama list

# Download specific model
docker-compose exec ollama ollama pull llava:7b-v1.5
```

### Clean Everything
```bash
# Stop and remove all containers, volumes
make clean
```

### Restart Services
```bash
docker-compose restart
```

## Troubleshooting

### Problem: Build fails with "apt-get" error
```bash
# Clean and rebuild
make clean
make build --no-cache
```

### Problem: Port 8080 already in use
Edit `docker-compose.yml` and change:
```yaml
ports:
  - "8080:80"  # Change 8080 to another port like 8888
```

### Problem: Ollama takes very long to start
- First startup downloads models (~5GB)
- Subsequent startups are much faster
- Models are cached in `ollama_data` volume

### Problem: Out of memory
- Allocate more RAM to Docker (Docker Desktop settings)
- Reduce Ollama model size in configuration
- Check: `docker stats` to see memory usage

### Problem: "Connection refused" errors
```bash
# Wait for services to fully start
sleep 30

# Check service logs
docker-compose logs ollama
docker-compose logs ocr-app

# Restart services
docker-compose restart
```

## API Endpoints

### Document Processing
```bash
# Upload and process document
curl -X POST http://localhost:8080/api/process \
  -F "file=@document.pdf"

# Get results
curl http://localhost:8080/api/results/<job_id>
```

### Health Check
```bash
curl http://localhost:8080/health
```

## File Structure

```
├── Dockerfile              # Multi-stage Docker image
├── docker-compose.yml      # Service orchestration
├── requirements.txt        # Python dependencies
├── app.py                 # Flask application
├── mistral_processor.py   # AI model integration
├── ocr_processor.py       # OCR processing
│
├── uploads/               # User uploads (auto-created)
├── results/              # Processing results (auto-created)
├── models/               # Additional models (auto-created)
│
└── static/               # Web assets
    ├── css/style.css
    └── js/script.js
```

## Performance Tips

1. **Use GPU acceleration** (if available):
   - Docker Desktop: Allocate GPU in settings
   - Docker Compose will auto-detect

2. **Optimize upload size**:
   - Max file size: 32MB (configurable in app.py)
   - PNG/JPEG images process faster than PDF

3. **Cache results**:
   - Results stored in `results/` directory
   - Redis caches frequently accessed data

4. **Monitor resource usage**:
   ```bash
   docker stats
   ```

## Security Checklist

- [ ] Change `FLASK_SECRET_KEY` in `.env`
- [ ] Change database password: `DB_PASSWORD` 
- [ ] Use environment variables for sensitive data
- [ ] Don't commit `.env` file to git
- [ ] Set up firewall rules for production
- [ ] Use HTTPS with reverse proxy
- [ ] Limit API rate (default: 200 per day)

## Production Deployment

For production, use:
- A reverse proxy (Nginx/Traefik)
- SSL/TLS certificates (Let's Encrypt)
- Persistent database backups
- Log aggregation
- Monitoring (Prometheus, Grafana)
- Horizontal scaling with load balancing

See `DOCKER_FIXES.md` for detailed architecture information.

## Support

For issues:
1. Check logs: `make logs`
2. Read `DOCKER_FIXES.md` for known issues
3. Verify Docker installation: `docker --version`
4. Check disk space: `docker system df`
5. Review `app.py` configuration

---

**Status:** ✅ Ready to use
**Last Updated:** 2026-01-18
