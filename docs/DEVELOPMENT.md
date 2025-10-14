# Development Guide

## Getting Started

This guide will help you set up your local development environment for ProjectBINGO's microservices architecture.

## Prerequisites

### Required Software
- **Node.js** v18+ (LTS recommended)
- **Docker** v20+
- **Docker Compose** v2+
- **Git**
- **PostgreSQL** 15+ (if running locally)
- **Redis** 7+ (if running locally)

### Optional Tools
- **kubectl** (for Kubernetes development)
- **Postman** or **Insomnia** (for API testing)
- **VS Code** (recommended IDE)

## Initial Setup

### 1. Clone the Repository
```bash
git clone https://github.com/thewriterben/ProjectBINGO.git
cd ProjectBINGO
```

### 2. Install Dependencies
```bash
npm install
```

### 3. Environment Configuration
Create a `.env` file in the root directory:
```bash
cp .env.example .env
```

Edit `.env` with your local configuration:
```env
# Server Configuration
NODE_ENV=development
PORT=3000

# Database Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=manufacturing_marketplace
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

REDIS_HOST=localhost
REDIS_PORT=6379

MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=manufacturing_files

# JWT Configuration
JWT_SECRET=your-local-dev-secret-key
JWT_ACCESS_EXPIRY=15m
JWT_REFRESH_EXPIRY=7d

# Service URLs (for local development)
USER_SERVICE_URL=http://localhost:3001
MANUFACTURER_SERVICE_URL=http://localhost:3002
ORDER_SERVICE_URL=http://localhost:3003
PAYMENT_SERVICE_URL=http://localhost:3004
AI_SERVICE_URL=http://localhost:3005
NOTIFICATION_SERVICE_URL=http://localhost:3006
FILE_SERVICE_URL=http://localhost:3007
```

## Development Options

### Option 1: Docker Compose (Recommended)

**Start all services with Docker:**
```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop all services
docker-compose down
```

**Access services:**
- API Gateway: http://localhost:3000
- User Service: http://localhost:3001
- Manufacturer Service: http://localhost:3002
- Order Service: http://localhost:3003
- Payment Service: http://localhost:3004
- AI Service: http://localhost:3005
- Notification Service: http://localhost:3006
- File Service: http://localhost:3007

**View individual service logs:**
```bash
docker-compose logs -f api-gateway
docker-compose logs -f user-service
docker-compose logs -f order-service
```

### Option 2: Local Development

**Start databases with Docker:**
```bash
# Start only databases
docker-compose up -d postgres redis mongodb
```

**Run services locally:**

Terminal 1 - API Gateway:
```bash
npm run dev:gateway
```

Terminal 2 - User Service:
```bash
npm run dev:user
```

Terminal 3 - Order Service:
```bash
npm run dev:order
```

(Repeat for other services as needed)

### Option 3: Hybrid Approach

Run some services in Docker and others locally for active development:

```bash
# Start databases and stable services
docker-compose up -d postgres redis mongodb api-gateway

# Run service you're working on locally
cd services/user-service
npm run dev
```

## Database Management

### Initialize Database
Database is automatically initialized when using Docker Compose. The `init-db.sql` script creates all necessary tables.

### Manual Database Setup
If running PostgreSQL locally:
```bash
psql -U postgres -f infrastructure/docker/init-db.sql
```

### View Database
```bash
# Connect to PostgreSQL in Docker
docker exec -it projectbingo-postgres psql -U postgres -d manufacturing_marketplace

# List tables
\dt

# View users table
SELECT * FROM users;

# Exit
\q
```

### Redis CLI
```bash
# Connect to Redis
docker exec -it projectbingo-redis redis-cli

# View all keys
KEYS *

# Get refresh token
GET refresh_token:user-id-here

# Exit
exit
```

## Testing APIs

### Using cURL

**Health Check:**
```bash
curl http://localhost:3000/health
```

**Register User:**
```bash
curl -X POST http://localhost:3000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123",
    "role": "buyer"
  }'
```

**Login:**
```bash
curl -X POST http://localhost:3000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123"
  }'
```

**Get Profile (with JWT):**
```bash
curl http://localhost:3000/api/v1/users/profile \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### Using Postman

Import the Postman collection (create one from the endpoints in MICROSERVICES_ARCHITECTURE.md).

## Testing

### Run All Tests
```bash
npm test
```

### Run Specific Test Files
```bash
npm test -- tests/api.test.js
```

### Run Tests with Coverage
```bash
npm run test:coverage
```

### Watch Mode (for development)
```bash
npm test -- --watch
```

## Code Quality

### Linting (Future)
```bash
npm run lint
```

### Formatting (Future)
```bash
npm run format
```

## Project Structure

```
ProjectBINGO/
├── services/                    # Microservices
│   ├── api-gateway/            # API Gateway
│   │   ├── src/
│   │   │   ├── index.js        # Main entry point
│   │   │   ├── routes/
│   │   │   └── middleware/
│   │   ├── tests/
│   │   └── package.json
│   ├── user-service/           # User Service
│   │   ├── src/
│   │   │   ├── index.js
│   │   │   ├── routes/
│   │   │   ├── controllers/
│   │   │   └── schemas/
│   │   ├── tests/
│   │   └── package.json
│   └── [other services...]
├── shared/                     # Shared code
│   ├── config/                 # Configuration
│   ├── middleware/             # Shared middleware
│   ├── utils/                  # Utilities
│   └── models/                 # Data models
├── infrastructure/             # Infrastructure as Code
│   ├── docker/                 # Docker files
│   │   ├── Dockerfile.service
│   │   └── init-db.sql
│   ├── kubernetes/             # Kubernetes manifests
│   └── monitoring/             # Monitoring configs
├── backend/                    # Legacy monolith (deprecated)
│   └── server.js
├── frontend/                   # Frontend (unchanged)
├── docs/                       # Documentation
├── tests/                      # Integration tests
├── docker-compose.yml          # Local development
└── package.json
```

## Common Development Tasks

### Add a New Endpoint

1. **Define the route** in `services/[service]/src/routes/`
2. **Create controller** in `services/[service]/src/controllers/`
3. **Add validation schema** in `services/[service]/src/schemas/`
4. **Write tests** in `services/[service]/tests/`
5. **Update documentation** in `docs/`

### Add a New Service

1. **Create directory structure**:
```bash
mkdir -p services/new-service/src/{routes,controllers,schemas}
mkdir -p services/new-service/tests
```

2. **Copy package.json** from existing service
3. **Create index.js** with Express setup
4. **Add to docker-compose.yml**
5. **Add to API Gateway** routing
6. **Create Kubernetes manifests**
7. **Update documentation**

### Database Migrations

For schema changes:
1. **Create migration file** in `infrastructure/docker/migrations/`
2. **Run migration**:
```bash
docker exec projectbingo-postgres psql -U postgres -d manufacturing_marketplace -f /path/to/migration.sql
```

## Debugging

### Service Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f user-service

# Last 100 lines
docker-compose logs --tail=100 user-service
```

### Node.js Debugging

Add to your service's package.json:
```json
"scripts": {
  "debug": "node --inspect=0.0.0.0:9229 src/index.js"
}
```

Then attach your debugger to port 9229.

### Database Queries

Enable query logging in PostgreSQL connection:
```javascript
const pool = new Pool({
  // ... config
  log: (msg) => console.log('PG:', msg)
});
```

## Performance Optimization

### Enable Caching
Implement Redis caching for frequently accessed data:
```javascript
const { getRedisClient } = require('../../shared/utils/database');

const cachedData = await redisClient.get('cache_key');
if (cachedData) {
  return JSON.parse(cachedData);
}

// Fetch from database...
await redisClient.setEx('cache_key', 300, JSON.stringify(data));
```

### Connection Pooling
Already configured in `shared/utils/database.js` for PostgreSQL.

### Query Optimization
- Use indexes (already created in init-db.sql)
- Limit result sets
- Use pagination
- Avoid N+1 queries

## Troubleshooting

### Port Already in Use
```bash
# Find process using port 3000
lsof -i :3000

# Kill process
kill -9 [PID]
```

### Database Connection Failed
- Check if PostgreSQL is running: `docker ps`
- Verify credentials in `.env`
- Check network: `docker network ls`

### Service Not Responding
1. Check service logs: `docker-compose logs [service]`
2. Verify environment variables
3. Check database connectivity
4. Restart service: `docker-compose restart [service]`

### Docker Issues
```bash
# Remove all containers and volumes
docker-compose down -v

# Rebuild from scratch
docker-compose build --no-cache
docker-compose up -d
```

## Git Workflow

### Branch Strategy
- `main` - Production code
- `develop` - Development branch
- `feature/*` - New features
- `bugfix/*` - Bug fixes
- `hotfix/*` - Production hotfixes

### Commit Messages
Follow conventional commits:
```
feat: add user authentication endpoint
fix: resolve JWT token expiration issue
docs: update API documentation
test: add unit tests for order service
refactor: optimize database queries
```

### Pull Requests
1. Create feature branch from `develop`
2. Make changes and commit
3. Push branch and create PR
4. Wait for CI/CD checks
5. Request code review
6. Merge after approval

## Resources

- [Microservices Architecture](./MICROSERVICES_ARCHITECTURE.md)
- [API Documentation](./API.md)
- [Deployment Guide](./DEPLOYMENT.md)
- [Express.js Docs](https://expressjs.com/)
- [Docker Docs](https://docs.docker.com/)
- [Kubernetes Docs](https://kubernetes.io/docs/)

## Getting Help

- Check existing documentation in `/docs`
- Review issues on GitHub
- Contact the development team
- Read service-specific README files

## Next Steps

1. **Explore the codebase**: Start with `services/api-gateway`
2. **Run the tests**: `npm test`
3. **Make a small change**: Add a console.log, restart service
4. **Create a new endpoint**: Follow the patterns in existing code
5. **Read the architecture docs**: Understand the system design

Happy coding! 🚀
