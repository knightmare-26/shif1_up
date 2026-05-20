# Shif1 UP - FastAPI Backend

A comprehensive FastAPI backend for the Shif1 UP F1 Analytics Platform, integrating with the FastF1 library for real Formula 1 data.

## 🚀 Features

- **FastF1 Integration**: Real F1 data from official sources
- **RESTful API**: Clean, documented API endpoints
- **Caching System**: Multi-level caching for performance
- **Real-time Data**: Live session monitoring and telemetry
- **Background Tasks**: Asynchronous data processing
- **Error Handling**: Comprehensive error handling and fallbacks
- **Type Safety**: Full Pydantic model validation

## 📋 Prerequisites

- Python 3.8+
- pip or poetry
- FastF1 library (for real F1 data)

## 🛠️ Installation

1. **Clone the repository** (if not already done):
   ```bash
   git clone <repository-url>
   cd shif1_up/backend
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**:
   ```bash
   cp env.example .env
   # Edit .env with your configuration
   ```

## 🏃‍♂️ Running the Backend

### Development Mode
```bash
python start.py
```

### Production Mode
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

The API will be available at:
- **API**: http://localhost:8000
- **Documentation**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 📚 API Endpoints

### Health Check
- `GET /health` - Service health status

### Driver Data
- `GET /api/drivers` - Driver standings
- `GET /api/drivers/{driver_id}` - Driver details

### Constructor Data
- `GET /api/constructors` - Constructor standings

### Race Data
- `GET /api/races` - Race schedule
- `GET /api/races/{race_id}` - Race details

### Session Data
- `GET /api/sessions/{session_id}` - Session data
- `GET /api/live/session` - Live session data
- `GET /api/live/positions` - Live positions

### Telemetry
- `GET /api/telemetry/{session_id}/{driver_id}` - Driver telemetry

### Weather
- `GET /api/weather/{session_id}` - Session weather

### Cache Management
- `GET /api/cache/stats` - Cache statistics
- `POST /api/cache/clear` - Clear cache

### Background Tasks
- `POST /api/refresh/{data_type}` - Trigger data refresh

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `API_HOST` | API host address | `0.0.0.0` |
| `API_PORT` | API port | `8000` |
| `API_RELOAD` | Auto-reload in development | `true` |
| `CORS_ORIGINS` | Allowed CORS origins | `http://localhost:3000` |
| `CACHE_DIR` | Cache directory | `./cache` |
| `CACHE_TTL` | Default cache TTL (seconds) | `3600` |
| `FASTF1_CACHE_DIR` | FastF1 cache directory | `./fastf1_cache` |
| `LOG_LEVEL` | Logging level | `INFO` |

### FastF1 Configuration

The backend uses FastF1 for real F1 data. FastF1 will automatically:
- Cache data locally for performance
- Handle rate limiting
- Provide fallback data when needed

## 📊 Data Sources

### Primary Sources
- **FastF1**: Official F1 timing data, telemetry, and results
- **Ergast API**: Historical F1 data
- **F1 Official API**: Live timing and positions

### Fallback Data
- Mock data for development and testing
- Cached data for offline scenarios

## 🏗️ Architecture

```
backend/
├── main.py                 # FastAPI application
├── start.py               # Startup script
├── requirements.txt       # Python dependencies
├── env.example           # Environment variables template
├── models/
│   └── f1_models.py      # Pydantic data models
├── services/
│   ├── fastf1_service.py # FastF1 integration
│   └── cache_service.py  # Caching system
└── cache/                # Cache directory (auto-created)
```

## 🔄 Data Flow

1. **Request** → FastAPI endpoint
2. **Cache Check** → Memory + persistent cache
3. **FastF1** → Real F1 data (if not cached)
4. **Processing** → Data transformation and validation
5. **Response** → JSON response with caching headers
6. **Background** → Cache cleanup and data refresh

## 🧪 Testing

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=.

# Run specific test file
pytest tests/test_fastf1_service.py
```

## 📈 Performance

### Caching Strategy
- **Memory Cache**: Fast access for frequently requested data
- **Persistent Cache**: Survives server restarts
- **FastF1 Cache**: Reduces API calls to F1 servers
- **TTL Management**: Automatic cache expiration

### Optimization
- **Async/Await**: Non-blocking I/O operations
- **Connection Pooling**: Efficient HTTP connections
- **Background Tasks**: Offload heavy operations
- **Data Compression**: Reduced payload sizes

## 🚨 Error Handling

The backend includes comprehensive error handling:
- **HTTP Errors**: Proper status codes and messages
- **FastF1 Errors**: Graceful fallbacks to mock data
- **Network Errors**: Retry logic and timeouts
- **Validation Errors**: Detailed error messages

## 🔒 Security

- **CORS**: Configurable cross-origin requests
- **Rate Limiting**: Prevent API abuse
- **Input Validation**: Pydantic model validation
- **Error Sanitization**: No sensitive data in errors

## 📝 Logging

Structured logging with different levels:
- **INFO**: General application flow
- **DEBUG**: Detailed debugging information
- **WARNING**: Non-critical issues
- **ERROR**: Critical errors

## 🚀 Deployment

### Docker (Recommended)
```bash
# Build image
docker build -t shif1-up-backend .

# Run container
docker run -p 8000:8000 shif1-up-backend
```

### Traditional Deployment
```bash
# Install production dependencies
pip install -r requirements.txt

# Run with Gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

## 🆘 Support

For issues and questions:
- Check the [API documentation](http://localhost:8000/docs)
- Review the logs for error details
- Ensure FastF1 is properly installed
- Verify environment variables are set correctly

## 🔮 Future Enhancements

- [ ] WebSocket support for real-time updates
- [ ] Database integration for historical data
- [ ] Machine learning predictions
- [ ] Advanced telemetry analysis
- [ ] Multi-language support
- [ ] API versioning
- [ ] Rate limiting per user
- [ ] Authentication and authorization