# Microservices Architecture Documentation

## Overview

ProjectBINGO has been transformed from a monolithic application into an enterprise-grade microservices architecture. This document provides a comprehensive guide to the new architecture.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (Web UI)                        │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      API Gateway (Port 3000)                     │
│  - Request routing                                               │
│  - Load balancing                                                │
│  - Rate limiting                                                 │
│  - Authentication                                                │
└──────┬──────────┬──────────┬──────────┬──────────┬─────────┬────┘
       │          │          │          │          │         │
       ▼          ▼          ▼          ▼          ▼         ▼
┌──────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌──────┐
│   User   │ │Manufac-│ │ Order  │ │Payment │ │   AI   │ │ File │
│ Service  │ │turer   │ │Service │ │Service │ │Service │ │Service│
│  :3001   │ │Service │ │ :3003  │ │ :3004  │ │ :3005  │ │ :3007│
└────┬─────┘ │ :3002  │ └───┬────┘ └────┬───┘ └────┬───┘ └──┬───┘
     │       └───┬────┘     │           │          │        │
     │           │          │           │          │        │
     └───────────┴──────────┴───────────┴──────────┴────────┘
                            │
     ┌──────────────────────┴──────────────────────┐
     │                                              │
     ▼                      ▼                       ▼
┌──────────┐         ┌──────────┐            ┌──────────┐
│PostgreSQL│         │  Redis   │            │ MongoDB  │
│  :5432   │         │  :6379   │            │  :27017  │
└──────────┘         └──────────┘            └──────────┘
```

## Microservices

### 1. API Gateway (Port 3000)
**Purpose**: Main entry point for all client requests

**Responsibilities**:
- Route requests to appropriate microservices
- Load balancing across service instances
- Rate limiting and DDoS protection
- Authentication and authorization
- API versioning
- Request/response logging
- Error handling

**Technologies**: Express.js, http-proxy-middleware

**Endpoints**:
- Proxies all `/api/v1/*` requests to respective services
- Backward compatibility for old API endpoints

### 2. User Service (Port 3001)
**Purpose**: User authentication and profile management

**Responsibilities**:
- User registration and login
- JWT token generation and validation
- Password hashing and verification
- Profile management
- Role-based access control (RBAC)
- Refresh token management

**Technologies**: Express.js, PostgreSQL, Redis, JWT, bcrypt

**Endpoints**:
- `POST /api/v1/auth/register` - Register new user
- `POST /api/v1/auth/login` - Login user
- `POST /api/v1/auth/refresh` - Refresh access token
- `POST /api/v1/auth/logout` - Logout user
- `GET /api/v1/users/profile` - Get user profile
- `PUT /api/v1/users/profile` - Update user profile
- `GET /api/v1/health` - Health check

**Database Tables**:
- `users` - User accounts and credentials

### 3. Manufacturer Service (Port 3002)
**Purpose**: Manufacturer profile management and verification

**Responsibilities**:
- Manufacturer registration
- Profile and capability management
- Verification and certification
- Rating and review aggregation
- Portfolio management

**Technologies**: Express.js, PostgreSQL

**Endpoints**:
- `GET /api/v1/manufacturers` - List all manufacturers
- `POST /api/v1/manufacturers` - Register manufacturer
- `GET /api/v1/manufacturers/:id` - Get manufacturer details
- `PUT /api/v1/manufacturers/:id` - Update manufacturer profile
- `GET /api/v1/health` - Health check

**Database Tables**:
- `manufacturers` - Manufacturer profiles and capabilities

### 4. Order Service (Port 3003)
**Purpose**: Order lifecycle and workflow management

**Responsibilities**:
- Order creation and tracking
- Order status management
- Order assignment to manufacturers
- Order history and analytics
- Marketplace statistics

**Technologies**: Express.js, PostgreSQL, Redis

**Endpoints**:
- `GET /api/v1/orders` - List orders
- `POST /api/v1/orders` - Create new order
- `GET /api/v1/orders/:id` - Get order details
- `PUT /api/v1/orders/:id` - Update order
- `DELETE /api/v1/orders/:id` - Cancel order
- `GET /api/v1/stats` - Marketplace statistics
- `GET /api/v1/health` - Health check

**Database Tables**:
- `orders` - Order details and status
- `reviews` - Order reviews and ratings

### 5. Payment Service (Port 3004)
**Purpose**: Payment processing and blockchain integration

**Responsibilities**:
- Payment processing
- Blockchain transaction management
- Smart contract integration
- Escrow management
- Payment tracking and history

**Technologies**: Express.js, Web3.js, PostgreSQL

**Endpoints**:
- `POST /api/v1/payments` - Process payment
- `GET /api/v1/payments/:id` - Get payment status
- `POST /api/v1/payments/escrow` - Create escrow
- `POST /api/v1/payments/release` - Release escrow funds
- `GET /api/v1/health` - Health check

**Database Tables**:
- `payments` - Payment records and transactions

### 6. AI Service (Port 3005)
**Purpose**: AI-powered cost estimation and manufacturer matching

**Responsibilities**:
- Cost estimation using ML models
- Manufacturer matching and recommendation
- Production time estimation
- Quality prediction
- Optimization algorithms

**Technologies**: Express.js, Python integration, Axios

**Endpoints**:
- `POST /api/v1/ai/estimate-cost` - AI cost estimation
- `POST /api/v1/ai/match-manufacturers` - AI manufacturer matching
- `POST /api/v1/ai/optimize` - Production optimization
- `GET /api/v1/health` - Health check

**Integration**: Communicates with Python AI module

### 7. Notification Service (Port 3006)
**Purpose**: Multi-channel notification delivery

**Responsibilities**:
- Email notifications
- SMS notifications
- Push notifications
- Notification templates
- Notification history and preferences

**Technologies**: Express.js, SendGrid/SES, Twilio, PostgreSQL

**Endpoints**:
- `POST /api/v1/notifications/email` - Send email
- `POST /api/v1/notifications/sms` - Send SMS
- `GET /api/v1/notifications` - Get notification history
- `PUT /api/v1/notifications/preferences` - Update preferences
- `GET /api/v1/health` - Health check

**Database Tables**:
- `notifications` - Notification history

### 8. File Service (Port 3007)
**Purpose**: File storage and document management

**Responsibilities**:
- File upload and download
- Document storage (specifications, designs)
- Image and media management
- File metadata management
- CDN integration

**Technologies**: Express.js, MongoDB, Multer, AWS S3/IPFS

**Endpoints**:
- `POST /api/v1/files/upload` - Upload file
- `GET /api/v1/files/:id` - Download file
- `DELETE /api/v1/files/:id` - Delete file
- `GET /api/v1/files` - List files
- `GET /api/v1/health` - Health check

**Database**: MongoDB for file metadata

## Databases

### PostgreSQL (Primary Database)
**Purpose**: Relational data storage

**Tables**:
- `users` - User accounts
- `manufacturers` - Manufacturer profiles
- `orders` - Order management
- `payments` - Payment records
- `notifications` - Notification history
- `reviews` - Reviews and ratings

**Configuration**:
- Host: postgres (Docker) / postgres-service (Kubernetes)
- Port: 5432
- Database: manufacturing_marketplace

### Redis (Cache)
**Purpose**: Caching and session management

**Use Cases**:
- JWT refresh token storage
- Session management
- API response caching
- Rate limiting counters
- Real-time data caching

**Configuration**:
- Host: redis (Docker) / redis-service (Kubernetes)
- Port: 6379

### MongoDB (Document Storage)
**Purpose**: Unstructured data and file metadata

**Collections**:
- `file_metadata` - File information and metadata
- `document_storage` - Large document storage

**Configuration**:
- URI: mongodb://mongodb:27017 (Docker)
- Database: manufacturing_files

## Communication Patterns

### Synchronous Communication
- **HTTP/REST**: Primary communication method between services
- **API Gateway**: Routes all external requests
- **Service-to-Service**: Direct HTTP calls when needed

### Asynchronous Communication (Future)
- **Message Queue**: RabbitMQ/Kafka for event-driven architecture
- **Event Bus**: For decoupled service communication

## Security

### Authentication
- **JWT Tokens**: Stateless authentication
- **Access Tokens**: Short-lived (15 minutes)
- **Refresh Tokens**: Long-lived (7 days)
- **Token Storage**: Redis for invalidation support

### Authorization
- **RBAC**: Role-based access control
- **Roles**: buyer, manufacturer, admin
- **Middleware**: Shared authentication middleware

### Data Security
- **Password Hashing**: bcrypt with salt
- **Encrypted Communication**: HTTPS/TLS
- **Environment Variables**: Secrets in Kubernetes Secrets
- **SQL Injection Prevention**: Parameterized queries

## Monitoring and Observability

### Health Checks
Each service exposes `/api/v1/health` endpoint with:
- Service status
- Database connectivity
- Cache connectivity
- Version information

### Logging
- **Structured Logging**: JSON format
- **Log Levels**: error, warn, info, debug
- **Centralized Logging**: ELK stack (future)

### Metrics
- **Prometheus**: Metrics collection (future)
- **Grafana**: Visualization dashboards (future)

### Tracing
- **Jaeger**: Distributed tracing (future)

## Deployment

### Docker Compose (Local Development)
```bash
docker-compose up -d
```

Services available at:
- API Gateway: http://localhost:3000
- User Service: http://localhost:3001
- Manufacturer Service: http://localhost:3002
- Order Service: http://localhost:3003
- (... other services)

### Kubernetes (Production)
```bash
kubectl apply -f infrastructure/kubernetes/
```

### CI/CD Pipeline
- **GitHub Actions**: Automated testing and deployment
- **Testing**: Unit, integration, and security tests
- **Building**: Docker images for each service
- **Deployment**: Automated to staging and production

## Scalability

### Horizontal Scaling
- Each service can scale independently
- Kubernetes manages replica sets
- Load balancing via API Gateway

### Caching Strategy
- Redis for frequently accessed data
- TTL-based cache invalidation
- Cache-aside pattern

### Database Optimization
- Connection pooling
- Indexed queries
- Query optimization

## Development Workflow

### Local Development
1. Install dependencies: `npm install`
2. Start services: `docker-compose up -d`
3. Run migrations: `npm run migrate`
4. Start development: `npm run dev`

### Testing
```bash
npm test                 # Run all tests
npm run test:unit        # Unit tests
npm run test:integration # Integration tests
npm run test:e2e         # End-to-end tests
```

### Code Quality
- ESLint for linting
- Prettier for formatting
- Jest for testing
- Pre-commit hooks

## Migration from Monolith

### Backward Compatibility
- Old API endpoints are proxied to new services
- `/api/orders` → `/api/v1/orders`
- `/api/manufacturers` → `/api/v1/manufacturers`
- Frontend requires minimal changes

### Data Migration
- Database schema created via init scripts
- Existing data can be migrated using provided scripts
- Smart contracts remain unchanged

## Future Enhancements

1. **Event-Driven Architecture**: Message queues for async communication
2. **Service Mesh**: Istio for advanced traffic management
3. **GraphQL Gateway**: Alternative to REST API
4. **WebSocket Support**: Real-time updates
5. **Advanced Monitoring**: Full observability stack
6. **Auto-scaling**: Based on metrics
7. **Multi-region Deployment**: Global distribution

## Troubleshooting

### Common Issues

**Service not starting:**
- Check Docker logs: `docker-compose logs [service-name]`
- Verify environment variables
- Check database connectivity

**Database connection errors:**
- Ensure PostgreSQL/Redis are running
- Verify credentials in environment variables
- Check network connectivity

**Authentication failures:**
- Verify JWT secret is configured
- Check token expiration
- Ensure Redis is running for refresh tokens

## Support and Documentation

- **Architecture**: This document
- **API Documentation**: `/docs/API.md`
- **Deployment Guide**: `/docs/DEPLOYMENT.md`
- **Development Guide**: `/docs/DEVELOPMENT.md`
