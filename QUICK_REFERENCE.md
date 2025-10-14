# ProjectBINGO v2.0 - Quick Reference Guide

## 🚀 Quick Start

```bash
# Start everything
docker-compose up -d

# View logs
docker-compose logs -f

# Stop everything
docker-compose down
```

## 🌐 Service URLs

| Service | URL | Purpose |
|---------|-----|---------|
| API Gateway | http://localhost:3000 | Main entry point |
| User Service | http://localhost:3001 | Authentication |
| Manufacturer Service | http://localhost:3002 | Manufacturers |
| Order Service | http://localhost:3003 | Orders |
| Payment Service | http://localhost:3004 | Payments |
| AI Service | http://localhost:3005 | AI features |
| Notification Service | http://localhost:3006 | Notifications |
| File Service | http://localhost:3007 | Files |

## 🗄️ Databases

| Database | Port | Credentials |
|----------|------|-------------|
| PostgreSQL | 5432 | postgres / postgres |
| Redis | 6379 | (no password) |
| MongoDB | 27017 | (no auth) |

## 📍 Key Endpoints

### Authentication
```bash
# Register
POST /api/v1/auth/register
{
  "email": "user@example.com",
  "password": "password123",
  "role": "buyer"
}

# Login
POST /api/v1/auth/login
{
  "email": "user@example.com",
  "password": "password123"
}

# Get Profile (requires JWT)
GET /api/v1/users/profile
Authorization: Bearer <access_token>
```

### Orders
```bash
# List orders
GET /api/v1/orders

# Create order (requires auth)
POST /api/v1/orders
Authorization: Bearer <access_token>
{
  "specifications": "Metal brackets",
  "quantity": 100,
  "material": "steel"
}

# Get order
GET /api/v1/orders/:orderId
```

### Health Checks
```bash
# API Gateway
curl http://localhost:3000/health

# User Service
curl http://localhost:3001/api/v1/health

# Order Service
curl http://localhost:3003/api/v1/health
```

## 🔑 JWT Tokens

**Access Token**: 15 minutes expiry
**Refresh Token**: 7 days expiry

```bash
# Use access token in header
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Refresh token
POST /api/v1/auth/refresh
{
  "refreshToken": "your_refresh_token"
}
```

## 🐳 Docker Commands

```bash
# Build services
docker-compose build

# Start specific service
docker-compose up -d user-service

# View service logs
docker-compose logs -f user-service

# Restart service
docker-compose restart user-service

# Stop all
docker-compose down

# Remove volumes (WARNING: deletes data)
docker-compose down -v

# Check status
docker-compose ps
```

## 🗃️ Database Commands

### PostgreSQL
```bash
# Connect to database
docker exec -it projectbingo-postgres psql -U postgres -d manufacturing_marketplace

# List tables
\dt

# View users
SELECT * FROM users;

# View orders
SELECT * FROM orders;

# Exit
\q
```

### Redis
```bash
# Connect to Redis
docker exec -it projectbingo-redis redis-cli

# List all keys
KEYS *

# Get value
GET key_name

# Delete key
DEL key_name

# Exit
exit
```

### MongoDB
```bash
# Connect to MongoDB
docker exec -it projectbingo-mongodb mongosh

# Use database
use manufacturing_files

# List collections
show collections

# Find documents
db.files.find()

# Exit
exit
```

## 📝 Common Tasks

### Register and Login
```bash
# 1. Register
curl -X POST http://localhost:3000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123"
  }'

# 2. Login (save the access_token)
curl -X POST http://localhost:3000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123"
  }'

# 3. Use token
export TOKEN="your_access_token_here"

# 4. Get profile
curl http://localhost:3000/api/v1/users/profile \
  -H "Authorization: Bearer $TOKEN"
```

### Create and View Order
```bash
# Create order
curl -X POST http://localhost:3000/api/v1/orders \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "specifications": "Custom metal parts",
    "quantity": 50,
    "material": "aluminum"
  }'

# List orders
curl http://localhost:3000/api/v1/orders
```

## 🔍 Troubleshooting

### Service won't start
```bash
# Check logs
docker-compose logs service-name

# Check if port is in use
lsof -i :3000

# Restart service
docker-compose restart service-name
```

### Database connection error
```bash
# Check if database is running
docker-compose ps postgres

# Restart database
docker-compose restart postgres

# Check database logs
docker-compose logs postgres
```

### Can't connect to service
```bash
# Check if service is running
docker-compose ps

# Check health endpoint
curl http://localhost:3000/health

# View service logs
docker-compose logs -f api-gateway
```

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| [README_MICROSERVICES.md](README_MICROSERVICES.md) | Overview |
| [MICROSERVICES_ARCHITECTURE.md](docs/MICROSERVICES_ARCHITECTURE.md) | Architecture |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md) | Development |
| [DEPLOYMENT_NEW.md](docs/DEPLOYMENT_NEW.md) | Deployment |
| [MIGRATION_GUIDE.md](docs/MIGRATION_GUIDE.md) | Migration |

## 🎯 Environment Variables

Key variables in `.env`:
```bash
# Server
NODE_ENV=development
PORT=3000

# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=manufacturing_marketplace
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# JWT
JWT_SECRET=your-secret-key
JWT_ACCESS_EXPIRY=15m
JWT_REFRESH_EXPIRY=7d

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
```

## 🧪 Testing

```bash
# Run tests
npm test

# Run with coverage
npm run test:coverage

# Test specific service
cd services/user-service
npm test
```

## 🚀 Deployment

### Local
```bash
docker-compose up -d
```

### Kubernetes
```bash
kubectl apply -f infrastructure/kubernetes/
```

## 📊 Monitoring

### Health Checks
```bash
# Check all services
for port in 3000 3001 3002 3003 3004 3005 3006 3007; do
  echo "Port $port:"
  curl -s http://localhost:$port/api/v1/health | jq .
done
```

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f user-service --tail=100
```

## 💡 Tips

- **Use the API Gateway** (port 3000) for all requests
- **Save JWT tokens** after login
- **Check health endpoints** before testing
- **View logs** when troubleshooting
- **Read documentation** for detailed guides

## 🆘 Help

- **Issues**: https://github.com/thewriterben/ProjectBINGO/issues
- **Documentation**: `/docs` directory
- **Architecture**: `docs/MICROSERVICES_ARCHITECTURE.md`

---

**Version**: 2.0.0  
**Last Updated**: October 2025
