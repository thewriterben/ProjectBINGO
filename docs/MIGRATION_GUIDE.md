# Migration Guide: Monolith to Microservices

## Overview

This guide helps you migrate from the original monolithic backend to the new microservices architecture. The migration is designed to be smooth with backward compatibility maintained.

## What Has Changed

### Architecture
- **Before**: Single `backend/server.js` file handling all requests
- **After**: 7 separate microservices + API Gateway
- **Frontend**: No changes required (backward compatibility maintained)

### Service Breakdown

| Old Endpoint | New Service | New Endpoint |
|-------------|-------------|--------------|
| `/api/health` | User Service | `/api/v1/health` (proxied) |
| `/api/orders` | Order Service | `/api/v1/orders` |
| `/api/orders/:id` | Order Service | `/api/v1/orders/:id` |
| `/api/manufacturers` | Manufacturer Service | `/api/v1/manufacturers` |
| `/api/manufacturers/register` | Manufacturer Service | `/api/v1/manufacturers` |
| `/api/ai/estimate-cost` | AI Service | `/api/v1/ai/estimate-cost` |
| `/api/ai/match-manufacturers` | AI Service | `/api/v1/ai/match-manufacturers` |
| `/api/stats` | Order Service | `/api/v1/stats` |

## Migration Strategies

### Strategy 1: Big Bang Migration (Recommended for Development)

Replace the entire monolith at once:

1. **Stop old backend**: `Ctrl+C` on running `npm start`
2. **Start new services**: `docker-compose up -d`
3. **Verify**: Test all endpoints
4. **Update env vars**: Update frontend if needed

**Pros**: Clean break, full feature set immediately
**Cons**: Higher risk, all-or-nothing

### Strategy 2: Strangler Pattern (Recommended for Production)

Gradually migrate endpoints:

1. **Deploy API Gateway** alongside old backend
2. **Route some endpoints** to new services
3. **Route remaining endpoints** to old backend
4. **Gradually migrate** all endpoints
5. **Decommission** old backend

**Pros**: Lower risk, gradual transition
**Cons**: More complex, temporary dual-run

### Strategy 3: Parallel Run

Run both systems simultaneously:

1. **Deploy new system** on different ports
2. **Run both systems** side-by-side
3. **Verify parity** between systems
4. **Switch over** when confident
5. **Decommission old** system

**Pros**: Easiest rollback, low risk
**Cons**: Resource intensive, complex testing

## Migration Steps

### Pre-Migration Checklist

- [ ] Backup all data
- [ ] Document current API behavior
- [ ] Test suite exists and passes
- [ ] Docker and Docker Compose installed
- [ ] Review new architecture documentation
- [ ] Identify customizations in old backend
- [ ] Plan downtime window (if needed)

### Step 1: Setup New Environment

```bash
# Clone or pull latest code
git pull origin main

# Install dependencies
npm install

# Copy environment variables
cp .env.example .env

# Edit .env with your configuration
nano .env
```

### Step 2: Database Migration

#### If Using Existing Database

The new system uses PostgreSQL. If you had data in a different database:

```bash
# Export data from old system
# (Implement based on your old database)

# Start new database
docker-compose up -d postgres

# Initialize schema
docker exec projectbingo-postgres psql -U postgres -d manufacturing_marketplace -f /docker-entrypoint-initdb.d/init.sql

# Import data
# (Implement based on your data format)
```

#### If Starting Fresh

```bash
# Start all services (includes database initialization)
docker-compose up -d
```

### Step 3: Start Microservices

```bash
# Start all services
docker-compose up -d

# Verify all services are running
docker-compose ps

# Check logs
docker-compose logs -f
```

### Step 4: Verify Services

```bash
# Health check
curl http://localhost:3000/health

# Test user registration
curl -X POST http://localhost:3000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123"
  }'

# Test login
curl -X POST http://localhost:3000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123"
  }'
```

### Step 5: Update Frontend (If Needed)

The API Gateway maintains backward compatibility, so minimal changes needed:

#### Option A: No Changes (Backward Compatible)
Frontend continues to use `/api/orders`, `/api/manufacturers`, etc.
API Gateway proxies these to new endpoints.

#### Option B: Update to New Endpoints
Update frontend to use new versioned endpoints:

```javascript
// Old
const response = await fetch('http://localhost:3000/api/orders');

// New (same behavior, but versioned)
const response = await fetch('http://localhost:3000/api/v1/orders');
```

### Step 6: Migrate Custom Logic

If you customized the old `backend/server.js`:

1. **Identify customizations**: Review your changes
2. **Map to services**: Determine which service should handle it
3. **Implement in service**: Add to appropriate microservice
4. **Test thoroughly**: Ensure behavior matches

Example:
```javascript
// Old (in backend/server.js)
app.get('/api/custom-endpoint', (req, res) => {
  // Your custom logic
});

// New (in services/order-service/src/routes/custom.js)
router.get('/api/v1/custom-endpoint', (req, res) => {
  // Same logic, in appropriate service
});
```

### Step 7: Migrate Authentication

#### Old System
If you had authentication in the monolith:
```javascript
// Extract existing user data
// Map to new user table structure
```

#### New System
- JWT-based authentication
- Refresh tokens stored in Redis
- bcrypt password hashing

#### Migration Script Example
```javascript
const { hashPassword } = require('./shared/utils/crypto');
const { getPostgresPool } = require('./shared/utils/database');

async function migrateUsers(oldUsers) {
  const pool = getPostgresPool();
  
  for (const user of oldUsers) {
    // Hash password if not already hashed
    const passwordHash = await hashPassword(user.password);
    
    await pool.query(
      `INSERT INTO users (email, password_hash, role, wallet_address)
       VALUES ($1, $2, $3, $4)
       ON CONFLICT (email) DO NOTHING`,
      [user.email, passwordHash, user.role || 'buyer', user.walletAddress]
    );
  }
}
```

### Step 8: Data Migration

#### Users
```sql
-- Export from old system
SELECT id, email, password_hash, role, wallet_address, created_at
FROM old_users;

-- Import to new system
-- (Run migration script or manual INSERT)
```

#### Orders
```sql
-- Export from old system
SELECT id, client_address, manufacturer_address, specifications, 
       price, quantity, status, created_at
FROM old_orders;

-- Import to new system with transformations
-- (Map addresses to user IDs, adjust schema)
```

### Step 9: Testing

Run comprehensive tests:

```bash
# Unit tests
npm test

# Integration tests
npm run test:integration

# Manual API testing
# Use Postman collection or curl commands
```

Test critical paths:
- [ ] User registration
- [ ] User login
- [ ] Create order
- [ ] List orders
- [ ] Update order
- [ ] Manufacturer registration
- [ ] AI cost estimation
- [ ] Payment processing

### Step 10: Cutover

#### For Development
```bash
# Stop old backend
# (If still running)

# Ensure new services are running
docker-compose ps

# Update any scripts/configs to point to new system
```

#### For Production

1. **Schedule maintenance window**
2. **Notify users** of upcoming changes
3. **Backup everything**
4. **Deploy new system** to staging
5. **Test thoroughly** in staging
6. **Deploy to production**
7. **Monitor closely**
8. **Keep old system** on standby for 24-48 hours

## Backward Compatibility

### Maintained Endpoints

All old endpoints work through API Gateway:

```
/api/orders          → /api/v1/orders
/api/manufacturers   → /api/v1/manufacturers
/api/ai/*            → /api/v1/ai/*
/api/stats           → /api/v1/stats
/api/health          → /api/v1/health
```

### Breaking Changes

**None** - The system is designed for zero breaking changes.

However, new features require new endpoints:
- User authentication: `/api/v1/auth/*`
- User profiles: `/api/v1/users/*`

## Troubleshooting Migration

### Services Won't Start

```bash
# Check Docker
docker ps

# Check logs
docker-compose logs -f

# Check ports
lsof -i :3000
lsof -i :5432

# Restart services
docker-compose restart
```

### Database Connection Errors

```bash
# Verify PostgreSQL is running
docker-compose ps postgres

# Check connection
docker exec projectbingo-postgres psql -U postgres -c "SELECT 1"

# Check environment variables
docker-compose config
```

### Authentication Not Working

```bash
# Check JWT secret is set
echo $JWT_SECRET

# Check Redis is running
docker-compose ps redis

# Test Redis connection
docker exec projectbingo-redis redis-cli ping
```

### Data Missing After Migration

```bash
# Check database tables
docker exec projectbingo-postgres psql -U postgres -d manufacturing_marketplace -c "\dt"

# Verify data
docker exec projectbingo-postgres psql -U postgres -d manufacturing_marketplace -c "SELECT COUNT(*) FROM users"

# Re-run migration if needed
```

## Rollback Procedure

If migration fails:

### Quick Rollback
```bash
# Stop new services
docker-compose down

# Start old backend
cd backend
npm start
```

### Complete Rollback
```bash
# Stop new services and remove volumes
docker-compose down -v

# Restore database backup
# (If you backed up original database)

# Start old system
npm run start:legacy
```

## Post-Migration Tasks

- [ ] Monitor service health
- [ ] Check error logs
- [ ] Verify all features work
- [ ] Monitor performance metrics
- [ ] Collect user feedback
- [ ] Update documentation
- [ ] Train team on new architecture
- [ ] Plan for decommissioning old code

## Decommissioning Old Backend

After successful migration (recommended: 30 days):

1. **Verify** new system is stable
2. **Archive** old backend code
3. **Update** documentation
4. **Remove** old dependencies
5. **Celebrate** successful migration! 🎉

```bash
# Archive old backend
mkdir archive
mv backend/ archive/backend-deprecated-$(date +%Y%m%d)

# Update .gitignore if needed
echo "archive/" >> .gitignore
```

## Performance Comparison

| Metric | Monolith | Microservices |
|--------|----------|---------------|
| Startup Time | ~2s | ~10s (all services) |
| Memory Usage | ~200MB | ~1GB (all services) |
| CPU Usage | Low | Moderate |
| Scalability | Limited | High |
| Deployment | All-or-nothing | Independent |
| Fault Tolerance | Low | High |

## Benefits Realized

After migration:
- ✅ **Independent scaling** - Scale services based on load
- ✅ **Fault isolation** - One service failure doesn't affect others
- ✅ **Technology flexibility** - Use different tech per service
- ✅ **Faster deployment** - Deploy one service at a time
- ✅ **Better organization** - Clear service boundaries
- ✅ **Enhanced security** - Service-level security controls
- ✅ **Improved monitoring** - Service-specific metrics

## Support

Need help with migration?
- Review [Architecture Documentation](./MICROSERVICES_ARCHITECTURE.md)
- Check [Development Guide](./DEVELOPMENT.md)
- Create GitHub issue
- Contact DevOps team

## Checklist

Use this checklist to track your migration:

- [ ] Read migration guide
- [ ] Backup all data
- [ ] Install Docker and Docker Compose
- [ ] Clone/update repository
- [ ] Configure environment variables
- [ ] Start new services
- [ ] Verify all services running
- [ ] Test critical endpoints
- [ ] Migrate custom code
- [ ] Migrate data
- [ ] Update frontend (if needed)
- [ ] Run full test suite
- [ ] Perform load testing
- [ ] Plan cutover
- [ ] Execute cutover
- [ ] Monitor post-migration
- [ ] Document lessons learned
- [ ] Decommission old system (after verification period)

Good luck with your migration! 🚀
