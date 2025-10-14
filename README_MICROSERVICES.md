# ProjectBINGO: Enterprise-Grade Manufacturing Marketplace

[![CI/CD Pipeline](https://github.com/thewriterben/ProjectBINGO/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/thewriterben/ProjectBINGO/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **🚀 Version 2.0** - Now with Enterprise-Grade Microservices Architecture!

## 📋 Overview

ProjectBINGO is a production-ready, AI-powered decentralized manufacturing marketplace built with modern microservices architecture. Connect manufacturers with clients through secure blockchain transactions and intelligent AI matching.

### What's New in v2.0

✨ **Enterprise-Grade Microservices Architecture**
- 7 independent microservices + API Gateway
- Horizontal scaling capabilities
- Fault isolation and high availability

🛡️ **Production-Ready Security**
- JWT authentication with refresh tokens
- Role-based access control (RBAC)
- API rate limiting and DDoS protection

🐳 **Complete Containerization**
- Docker Compose for local development
- Kubernetes-ready deployments
- CI/CD pipeline with GitHub Actions

📊 **Monitoring & Observability**
- Health check endpoints for all services
- Structured logging
- Prometheus-ready metrics

🗄️ **Multi-Database Architecture**
- PostgreSQL for transactional data
- Redis for caching and sessions
- MongoDB for document storage

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────┐
│              Frontend (Web UI)                    │
└───────────────────┬──────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────┐
│           API Gateway (Port 3000)                 │
│  • Request Routing    • Rate Limiting             │
│  • Authentication     • Load Balancing            │
└──────┬────┬────┬────┬────┬────┬────┬────────────┘
       │    │    │    │    │    │    │
       ▼    ▼    ▼    ▼    ▼    ▼    ▼
    ┌─────────────────────────────────────┐
    │       Microservices Layer           │
    │  • User Service         :3001       │
    │  • Manufacturer Service :3002       │
    │  • Order Service        :3003       │
    │  • Payment Service      :3004       │
    │  • AI Service           :3005       │
    │  • Notification Service :3006       │
    │  • File Service         :3007       │
    └──────────────┬──────────────────────┘
                   │
          ┌────────┴─────────┐
          ▼                  ▼
    ┌──────────┐      ┌──────────┐
    │PostgreSQL│      │  Redis   │
    │  :5432   │      │  :6379   │
    └──────────┘      └──────────┘
          ▼
    ┌──────────┐
    │ MongoDB  │
    │  :27017  │
    └──────────┘
```

## ✨ Key Features

### 🔐 Authentication & Authorization
- Secure JWT-based authentication
- Refresh token mechanism
- Role-based access control (RBAC)
- Password hashing with bcrypt

### 🏭 Manufacturing Marketplace
- Order creation and tracking
- Manufacturer profiles and verification
- AI-powered cost estimation
- Intelligent manufacturer matching
- Real-time order status updates

### 💰 Blockchain Integration
- Ethereum smart contracts
- Secure escrow payments
- Transparent transaction history
- Web3 wallet integration

### 🤖 AI-Powered Features
- Cost estimation algorithms
- Manufacturer matching
- Production time prediction
- Quality optimization

### 📧 Notifications
- Email notifications
- SMS alerts (via Twilio)
- Push notifications
- Customizable preferences

### 📁 File Management
- Document upload/download
- Design file storage
- Media management
- CDN integration ready

## 🚀 Quick Start

### Prerequisites
- Docker 20+
- Docker Compose v2+
- Node.js 18+ (for local development)

### 1. Clone Repository
```bash
git clone https://github.com/thewriterben/ProjectBINGO.git
cd ProjectBINGO
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env with your configuration
```

### 3. Start Services
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Check status
docker-compose ps
```

### 4. Access Services
- **API Gateway**: http://localhost:3000
- **Frontend**: http://localhost:8080 (serve `frontend/`)
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379
- **MongoDB**: localhost:27017

### 5. Test API
```bash
# Health check
curl http://localhost:3000/health

# Register user
curl -X POST http://localhost:3000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password123"}'
```

## 📖 Documentation

| Document | Description |
|----------|-------------|
| [Microservices Architecture](./docs/MICROSERVICES_ARCHITECTURE.md) | Complete architecture overview |
| [Development Guide](./docs/DEVELOPMENT.md) | Local development setup |
| [Deployment Guide](./docs/DEPLOYMENT_NEW.md) | Production deployment |
| [Migration Guide](./docs/MIGRATION_GUIDE.md) | Migrate from v1.0 |
| [API Documentation](./docs/API.md) | API reference |

## 🛠️ Tech Stack

### Backend Services
- **Runtime**: Node.js 18
- **Framework**: Express.js
- **Authentication**: JWT, bcrypt
- **Validation**: Joi

### Databases
- **PostgreSQL** 15 - Primary database
- **Redis** 7 - Caching & sessions
- **MongoDB** 7 - Document storage

### Blockchain
- **Solidity** - Smart contracts
- **Web3.js** - Ethereum integration

### DevOps
- **Docker** - Containerization
- **Kubernetes** - Orchestration
- **GitHub Actions** - CI/CD
- **Terraform** - Infrastructure as Code

### Monitoring (Planned)
- **Prometheus** - Metrics
- **Grafana** - Dashboards
- **ELK Stack** - Logging
- **Jaeger** - Distributed tracing

## 📁 Project Structure

```
ProjectBINGO/
├── services/                    # Microservices
│   ├── api-gateway/            # API Gateway
│   ├── user-service/           # User management
│   ├── manufacturer-service/   # Manufacturer profiles
│   ├── order-service/          # Order management
│   ├── payment-service/        # Payments & blockchain
│   ├── ai-service/             # AI algorithms
│   ├── notification-service/   # Notifications
│   └── file-service/           # File management
├── shared/                     # Shared code
│   ├── config/                 # Configuration
│   ├── middleware/             # Common middleware
│   ├── utils/                  # Utilities
│   └── models/                 # Data models
├── infrastructure/             # Infrastructure as Code
│   ├── docker/                 # Docker files
│   ├── kubernetes/             # K8s manifests
│   └── monitoring/             # Monitoring configs
├── docs/                       # Documentation
├── tests/                      # Tests
├── frontend/                   # Web UI (unchanged)
├── contracts/                  # Smart contracts
├── ai-module/                  # AI/ML code (Python)
├── docker-compose.yml          # Local development
└── .github/workflows/          # CI/CD pipelines
```

## 🧪 Testing

```bash
# Run all tests
npm test

# Unit tests
npm run test:unit

# Integration tests
npm run test:integration

# With coverage
npm run test:coverage
```

## 🔒 Security Features

- **JWT Authentication**: Secure token-based auth
- **Password Hashing**: bcrypt with salt
- **Rate Limiting**: Protect against abuse
- **Input Validation**: Joi schema validation
- **SQL Injection Prevention**: Parameterized queries
- **XSS Protection**: Helmet.js security headers
- **CORS Configuration**: Controlled cross-origin requests

## 📊 Performance Features

- **Connection Pooling**: PostgreSQL connections
- **Redis Caching**: Fast data access
- **Horizontal Scaling**: Independent service scaling
- **Load Balancing**: API Gateway routing
- **Async Operations**: Non-blocking I/O

## 🚢 Deployment

### Docker Compose (Development)
```bash
docker-compose up -d
```

### Kubernetes (Production)
```bash
kubectl apply -f infrastructure/kubernetes/
```

### CI/CD Pipeline
Automatic deployment on push to:
- `develop` → Staging
- `main` → Production

## 🔄 Migration from v1.0

Migrating from the monolithic version? See our comprehensive [Migration Guide](./docs/MIGRATION_GUIDE.md).

**Backward Compatibility**: All old endpoints continue to work! The API Gateway maintains compatibility while routing to new services.

## 📈 Scalability

### Service Scaling
```bash
# Scale user service to 5 replicas
kubectl scale deployment user-service --replicas=5 -n projectbingo
```

### Auto-Scaling
Configure Horizontal Pod Autoscaler for automatic scaling based on CPU/memory.

### Database Scaling
- **PostgreSQL**: Read replicas for read-heavy loads
- **Redis**: Redis Cluster for distributed caching
- **MongoDB**: Sharding for large document stores

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

### Development Workflow
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Write/update tests
5. Submit a pull request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👤 Author

**Benjamin J. Snider** (thewriterben)

## 🌟 Show Your Support

Give a ⭐️ if this project helped you!

## 📞 Support

- **Documentation**: Check `/docs` directory
- **Issues**: [GitHub Issues](https://github.com/thewriterben/ProjectBINGO/issues)
- **Discussions**: [GitHub Discussions](https://github.com/thewriterben/ProjectBINGO/discussions)

## 🗺️ Roadmap

### Current (v2.0)
- ✅ Microservices architecture
- ✅ Docker containerization
- ✅ Kubernetes deployment
- ✅ CI/CD pipeline
- ✅ JWT authentication
- ✅ Multi-database support

### Planned (v2.1)
- [ ] Full monitoring stack (Prometheus, Grafana)
- [ ] Centralized logging (ELK)
- [ ] Distributed tracing (Jaeger)
- [ ] Message queue (RabbitMQ/Kafka)
- [ ] Service mesh (Istio)
- [ ] GraphQL API
- [ ] WebSocket support
- [ ] Mobile app
- [ ] Advanced AI features

## 🔗 Links

- [Original README](./README.md)
- [Technical Requirements](./docs/TECHNICAL_REQUIREMENTS.md)
- [API Documentation](./docs/API.md)
- [Future Improvements](./docs/FUTURE_IMPROVEMENTS.md)

---

**Built with ❤️ using Microservices Architecture**
