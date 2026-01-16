# Shif1 UP - Advanced F1 Analytics Platform

A production-ready Formula 1 analytics platform featuring real-time data streaming, historical analysis, and predictive modeling. Built with FastAPI, DuckDB, Redis, and WebSocket technology.

## 🏎️ Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   FastAPI       │    │   Live Poller   │
│   (React)       │◄──►│   (Backend)     │◄──►│   (FastF1)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   Redis         │
                    │   (Live State)  │
                    └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   DuckDB        │
                    │   (Historical)  │
                    └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   Parquet       │
                    │   (Telemetry)   │
                    └─────────────────┘
```

## 🚀 Features

### Core Features
- **Real-time Live Data**: WebSocket streaming of live race data
- **Historical Analysis**: Complete F1 history with DuckDB storage
- **Predictive Modeling**: AI-powered race outcome predictions
- **Telemetry Storage**: Efficient Parquet-based telemetry storage
- **Multi-source Data**: FastF1 + Ergast API integration
- **Production Ready**: Docker Compose deployment

### API Endpoints
- `GET /health` - Health check
- `GET /drivers?year={year}` - Driver listings
- `GET /races?year={year}` - Race schedules
- `GET /race/{race_id}/results` - Race classifications
- `GET /race/{race_id}/laps?driver={driver}` - Lap analysis
- `GET /live/{race_id}/state` - Live race state
- `WebSocket /ws/live/{race_id}` - Live data streaming

## 🛠️ Technology Stack

- **Backend**: FastAPI, Python 3.11+
- **Database**: DuckDB (historical data)
- **Cache**: Redis (live state + pub/sub)
- **Data Sources**: FastF1, Ergast API
- **Storage**: Parquet files (telemetry)
- **Frontend**: React + TypeScript + TailwindCSS
- **Deployment**: Docker Compose

## 📦 Quick Start

### Option 1: Docker Compose (Recommended)

```bash
# Clone and start all services
git clone <repository-url>
cd shif1_up
docker-compose up --build

# Services will be available at:
# - API: http://localhost:8000
# - Frontend: http://localhost:3000
# - Redis: localhost:6379
```

### Option 2: Local Development

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start Redis (required)
docker run -d -p 6379:6379 redis:7-alpine

# 4. Ingest historical data
python ingest/historical_ingest.py --years 2024

# 5. Start API server
uvicorn api.main:app --reload --port 8000

# 6. Start live poller (in another terminal)
RACE_YEAR=2024 RACE_GP=Bahrain python live/poller.py

# 7. Start prediction worker (optional)
python predict/worker.py
```

## 📊 Data Ingestion

### Historical Data
```bash
# Ingest specific years
python ingest/historical_ingest.py --years 2023 2024

# Ingest year range
python ingest/historical_ingest.py --start-year 2020 --end-year 2024

# Ingest with custom paths
python ingest/historical_ingest.py --years 2024 \
  --db-path data/f1_history.duckdb \
  --telemetry-dir data/telemetry \
  --cache-dir data/fastf1_cache
```

### Incremental Updates
```bash
# Check for new sessions
python ingest/incremental_ingest.py --dry-run

# Ingest new sessions
python ingest/incremental_ingest.py --years 2024
```

## 🔴 Live Data

### Starting Live Poller
```bash
# Poll specific race
RACE_YEAR=2024 RACE_GP=Bahrain python live/poller.py

# Custom poll interval (seconds)
RACE_YEAR=2024 RACE_GP=Bahrain POLL_INTERVAL=10 python live/poller.py

# With custom Redis URL
RACE_YEAR=2024 RACE_GP=Bahrain REDIS_URL=redis://localhost:6379 python live/poller.py
```

### WebSocket Connection
```javascript
// Connect to live race updates
const ws = new WebSocket('ws://localhost:8000/ws/live/2024_Bahrain');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Live update:', data);
};
```

## 🧪 Testing

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=api

# Run specific test file
pytest tests/test_api.py -v
```

## 📁 Project Structure

```
shif1_up/
├── api/                    # FastAPI backend
│   ├── main.py            # Main API application
│   ├── services/          # Service layer
│   │   ├── duckdb_service.py
│   │   ├── redis_service.py
│   │   ├── fastf1_service.py
│   │   └── ergast_service.py
│   └── models/            # Pydantic models
├── ingest/                # Data ingestion scripts
│   ├── historical_ingest.py
│   └── incremental_ingest.py
├── live/                  # Live data components
│   └── poller.py
├── predict/               # Prediction system
│   └── worker.py
├── tests/                 # Test suite
│   ├── test_api.py
│   └── sample_data/
├── data/                  # Data storage
│   ├── f1_history.duckdb
│   ├── telemetry/
│   └── fastf1_cache/
├── src/                   # React frontend
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## 🔧 Configuration

### Environment Variables
```bash
# Redis Configuration
REDIS_URL=redis://localhost:6379

# Database Configuration
DUCKDB_PATH=data/f1_history.duckdb

# FastF1 Configuration
FASTF1_CACHE_DIR=data/fastf1_cache

# Live Poller Configuration
RACE_YEAR=2024
RACE_GP=Bahrain
POLL_INTERVAL=5
```

### Docker Compose Services
- **api**: FastAPI backend server
- **redis**: Redis cache and pub/sub
- **poller**: Live data poller
- **worker**: Prediction worker

## 📈 Performance & Scaling

### Current Limitations
- Single poller process (by design)
- DuckDB for historical data (can be replaced with PostgreSQL)
- In-memory Redis (can be clustered)

### Production Recommendations
1. **Database**: Replace DuckDB with PostgreSQL for better concurrency
2. **Caching**: Use Redis Cluster for high availability
3. **Load Balancing**: Add nginx/HAProxy for API load balancing
4. **Monitoring**: Add Prometheus + Grafana for metrics
5. **Authentication**: Implement JWT-based authentication
6. **Rate Limiting**: Add API rate limiting

### Scaling Strategies
```yaml
# Example production docker-compose.yml
version: '3.8'
services:
  api:
    deploy:
      replicas: 3
    environment:
      - REDIS_URL=redis://redis-cluster:6379
      - DATABASE_URL=postgresql://user:pass@postgres:5432/f1db
  
  redis:
    image: redis:7-alpine
    command: redis-server --cluster-enabled yes
  
  postgres:
    image: postgres:15
    environment:
      - POSTGRES_DB=f1db
```

## 🐛 Troubleshooting

### Common Issues

**1. FastF1 Cache Issues**
```bash
# Clear FastF1 cache
rm -rf data/fastf1_cache/*
```

**2. Redis Connection Issues**
```bash
# Check Redis status
docker exec -it redis redis-cli ping
```

**3. DuckDB Lock Issues**
```bash
# Ensure only one process accesses DuckDB at a time
# Consider using PostgreSQL for concurrent access
```

**4. Port Conflicts**
```bash
# Check port usage
netstat -tulpn | grep :8000
netstat -tulpn | grep :6379
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- [FastF1](https://github.com/theOehrly/Fast-F1) - F1 data access
- [Ergast API](http://ergast.com/mrd/) - Historical F1 data
- [DuckDB](https://duckdb.org/) - Analytical database
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework

## 📞 Support

For questions and support:
- Create an issue on GitHub
- Check the troubleshooting section
- Review the API documentation at `/docs`

---

**Built with ❤️ for F1 fans and data enthusiasts**