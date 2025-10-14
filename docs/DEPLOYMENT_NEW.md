# Deployment Guide - Microservices Architecture

## Overview

This guide covers deploying ProjectBINGO's microservices architecture to various environments.

## Deployment Environments

- **Local**: Docker Compose for development
- **Staging**: Kubernetes cluster for testing
- **Production**: Kubernetes cluster with autoscaling

## Prerequisites

### All Environments
- Git
- Access to container registry
- Environment-specific credentials

### Docker Compose (Local)
- Docker v20+
- Docker Compose v2+

### Kubernetes (Staging/Production)
- kubectl configured
- Kubernetes cluster access
- Container registry access (Docker Hub, GitHub Container Registry, etc.)

## Local Deployment (Docker Compose)

### Quick Start
```bash
# Clone repository
git clone https://github.com/thewriterben/ProjectBINGO.git
cd ProjectBINGO

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Services Available
- API Gateway: http://localhost:3000
- PostgreSQL: localhost:5432
- Redis: localhost:6379
- MongoDB: localhost:27017

### Data Persistence
Data is persisted in Docker volumes:
```bash
# List volumes
docker volume ls | grep projectbingo

# Remove volumes (WARNING: destroys data)
docker-compose down -v
```

### Troubleshooting Local
```bash
# View service status
docker-compose ps

# Restart specific service
docker-compose restart user-service

# Rebuild service
docker-compose build user-service
docker-compose up -d user-service

# View service logs
docker-compose logs --tail=100 -f user-service
```

## Building Docker Images

### Build All Services
```bash
# Build all images
docker-compose build

# Build specific service
docker-compose build user-service
```

### Push to Registry
```bash
# Tag images
docker tag projectbingo_api-gateway:latest ghcr.io/thewriterben/projectbingo/api-gateway:latest

# Push to GitHub Container Registry
docker push ghcr.io/thewriterben/projectbingo/api-gateway:latest
```

### Automated Builds
GitHub Actions automatically builds and pushes images on:
- Push to `main` branch
- Push to `develop` branch
- Pull requests (build only)

## Kubernetes Deployment

### Prerequisites
```bash
# Verify kubectl access
kubectl cluster-info

# Create namespace
kubectl apply -f infrastructure/kubernetes/namespace.yaml
```

### Configuration

#### 1. Update ConfigMap
Edit `infrastructure/kubernetes/configmap.yaml` with environment-specific values:
```yaml
data:
  NODE_ENV: "production"
  POSTGRES_HOST: "your-postgres-host"
  # ... other configs
```

#### 2. Update Secrets
**IMPORTANT**: Never commit real secrets!

Edit `infrastructure/kubernetes/secrets.yaml`:
```yaml
stringData:
  POSTGRES_PASSWORD: "your-secure-password"
  JWT_SECRET: "your-jwt-secret"
  # ... other secrets
```

Or create from command line:
```bash
kubectl create secret generic projectbingo-secrets \
  --from-literal=POSTGRES_PASSWORD=your-password \
  --from-literal=JWT_SECRET=your-jwt-secret \
  -n projectbingo
```

### Deploy Services

#### Deploy All at Once
```bash
kubectl apply -f infrastructure/kubernetes/
```

#### Deploy Individually
```bash
# Deploy configuration
kubectl apply -f infrastructure/kubernetes/namespace.yaml
kubectl apply -f infrastructure/kubernetes/configmap.yaml
kubectl apply -f infrastructure/kubernetes/secrets.yaml

# Deploy services
kubectl apply -f infrastructure/kubernetes/api-gateway-deployment.yaml
kubectl apply -f infrastructure/kubernetes/user-service-deployment.yaml
# ... other services
```

### Verify Deployment
```bash
# Check pods
kubectl get pods -n projectbingo

# Check services
kubectl get svc -n projectbingo

# Check deployments
kubectl get deployments -n projectbingo

# View pod logs
kubectl logs -f deployment/api-gateway -n projectbingo

# Describe pod for troubleshooting
kubectl describe pod <pod-name> -n projectbingo
```

### Scaling

#### Manual Scaling
```bash
# Scale user service to 3 replicas
kubectl scale deployment user-service --replicas=3 -n projectbingo

# Verify scaling
kubectl get pods -n projectbingo
```

#### Auto-Scaling (Future)
Create HorizontalPodAutoscaler:
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: user-service-hpa
  namespace: projectbingo
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: user-service
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

### Updates and Rollbacks

#### Update Deployment
```bash
# Update image
kubectl set image deployment/user-service \
  user-service=ghcr.io/thewriterben/projectbingo/user-service:v2.0.0 \
  -n projectbingo

# Watch rollout
kubectl rollout status deployment/user-service -n projectbingo
```

#### Rollback
```bash
# View rollout history
kubectl rollout history deployment/user-service -n projectbingo

# Rollback to previous version
kubectl rollout undo deployment/user-service -n projectbingo

# Rollback to specific revision
kubectl rollout undo deployment/user-service --to-revision=2 -n projectbingo
```

## Database Setup

### PostgreSQL

#### Initial Setup
Database is automatically initialized from `init-db.sql` when using Docker Compose.

For Kubernetes, you need to:
1. Deploy PostgreSQL (using Helm or manifests)
2. Run initialization script manually:

```bash
# Copy init script to pod
kubectl cp infrastructure/docker/init-db.sql \
  postgres-pod-name:/tmp/init-db.sql -n projectbingo

# Execute script
kubectl exec -it postgres-pod-name -n projectbingo -- \
  psql -U postgres -d manufacturing_marketplace -f /tmp/init-db.sql
```

#### Managed Database (Recommended for Production)
Use managed PostgreSQL services:
- **AWS**: RDS for PostgreSQL
- **Google Cloud**: Cloud SQL for PostgreSQL
- **Azure**: Azure Database for PostgreSQL

Update ConfigMap with connection details.

### Redis

For production, use managed Redis:
- **AWS**: ElastiCache for Redis
- **Google Cloud**: Memorystore for Redis
- **Azure**: Azure Cache for Redis

### MongoDB

For production, use managed MongoDB:
- **MongoDB Atlas**: Managed MongoDB service
- **AWS DocumentDB**: MongoDB-compatible
- **Google Cloud**: MongoDB on GKE

## Environment Configuration

### Development
- Single replica per service
- Debug logging enabled
- No resource limits
- Local databases

### Staging
- 2 replicas per service
- Info-level logging
- Resource requests/limits set
- Staging databases
- Monitoring enabled

### Production
- 3+ replicas per service
- Error-level logging
- Strict resource limits
- Production databases
- Full monitoring and alerting
- Autoscaling enabled
- Backup and disaster recovery

## CI/CD Pipeline

### GitHub Actions Workflow

The `.github/workflows/ci-cd.yml` file automates:

1. **Testing**: Runs on every push and PR
   - Unit tests
   - Integration tests
   - Security scans

2. **Building**: Runs on push to main/develop
   - Builds Docker images
   - Pushes to container registry
   - Tags with commit SHA and branch

3. **Deployment**: Runs on push to main/develop
   - Staging: Deploys from develop branch
   - Production: Deploys from main branch

### Manual Deployment

To deploy manually:
```bash
# Build images
docker-compose build

# Tag for registry
docker tag projectbingo_user-service ghcr.io/thewriterben/projectbingo/user-service:v2.0.0

# Push to registry
docker push ghcr.io/thewriterben/projectbingo/user-service:v2.0.0

# Update Kubernetes
kubectl set image deployment/user-service \
  user-service=ghcr.io/thewriterben/projectbingo/user-service:v2.0.0 \
  -n projectbingo
```

## Monitoring and Logging

### Health Checks

All services expose health endpoints:
```bash
# Check API Gateway
curl http://your-domain/health

# Check specific service
curl http://user-service-url/api/v1/health
```

### Kubernetes Monitoring
```bash
# Resource usage
kubectl top nodes
kubectl top pods -n projectbingo

# Events
kubectl get events -n projectbingo --sort-by='.lastTimestamp'
```

### Centralized Logging (Future)

Deploy ELK stack for centralized logging:
```bash
# Add Elastic Helm repository
helm repo add elastic https://helm.elastic.co

# Install Elasticsearch
helm install elasticsearch elastic/elasticsearch -n projectbingo

# Install Kibana
helm install kibana elastic/kibana -n projectbingo

# Install Filebeat for log collection
helm install filebeat elastic/filebeat -n projectbingo
```

### Monitoring Stack (Future)

Deploy Prometheus and Grafana:
```bash
# Add Prometheus Helm repository
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts

# Install Prometheus
helm install prometheus prometheus-community/kube-prometheus-stack -n projectbingo
```

## Security Considerations

### Secrets Management
- Never commit secrets to Git
- Use Kubernetes Secrets or external secret managers
- Rotate secrets regularly
- Use separate secrets for each environment

### Network Security
- Enable network policies in Kubernetes
- Use TLS/HTTPS for all external communication
- Restrict database access to specific services
- Use private container registries

### Container Security
- Use official base images
- Scan images for vulnerabilities (Trivy in CI/CD)
- Run containers as non-root user
- Set resource limits

## Backup and Disaster Recovery

### Database Backups

#### PostgreSQL
```bash
# Backup
kubectl exec postgres-pod -n projectbingo -- \
  pg_dump -U postgres manufacturing_marketplace > backup.sql

# Restore
kubectl exec -i postgres-pod -n projectbingo -- \
  psql -U postgres manufacturing_marketplace < backup.sql
```

#### Automated Backups
Use managed database backup features or tools like:
- **Velero**: Kubernetes backup
- **pg_dump** with cron jobs
- Cloud provider backup services

### Disaster Recovery Plan

1. **Regular Backups**: Daily database backups
2. **Multiple Regions**: Deploy to multiple availability zones
3. **Monitoring**: Alert on service failures
4. **Runbooks**: Document recovery procedures
5. **Testing**: Regularly test disaster recovery

## Performance Optimization

### Database Optimization
- Use connection pooling (already configured)
- Add indexes for frequently queried columns (already done)
- Use read replicas for read-heavy workloads
- Implement caching with Redis

### Application Optimization
- Enable response compression
- Use CDN for static assets
- Implement proper caching strategies
- Optimize Docker images (multi-stage builds)

### Kubernetes Optimization
- Set appropriate resource requests/limits
- Use horizontal pod autoscaling
- Implement pod disruption budgets
- Use node affinity for optimal placement

## Cost Optimization

### Cloud Resources
- Use spot instances for non-critical workloads
- Right-size your resources based on metrics
- Use autoscaling to match demand
- Clean up unused resources

### Container Optimization
- Use smaller base images (Alpine)
- Implement layer caching
- Remove development dependencies in production

## Troubleshooting Production

### Common Issues

#### Pod CrashLoopBackOff
```bash
# Check logs
kubectl logs pod-name -n projectbingo

# Check events
kubectl describe pod pod-name -n projectbingo

# Check previous container logs
kubectl logs pod-name --previous -n projectbingo
```

#### Service Not Accessible
```bash
# Check service
kubectl get svc -n projectbingo

# Check endpoints
kubectl get endpoints service-name -n projectbingo

# Test service internally
kubectl run test-pod --image=curlimages/curl -it --rm -- \
  curl http://service-name:port/api/v1/health
```

#### Database Connection Issues
- Verify credentials in secrets
- Check network connectivity
- Verify database is running
- Check connection limits

### Emergency Procedures

#### Rollback Deployment
```bash
kubectl rollout undo deployment/service-name -n projectbingo
```

#### Scale Down Service
```bash
kubectl scale deployment service-name --replicas=0 -n projectbingo
```

#### Delete and Recreate
```bash
kubectl delete deployment service-name -n projectbingo
kubectl apply -f infrastructure/kubernetes/service-deployment.yaml
```

## Post-Deployment Checklist

- [ ] All pods are running
- [ ] Health checks are passing
- [ ] Database connections work
- [ ] API Gateway is accessible
- [ ] Authentication is working
- [ ] Monitoring is active
- [ ] Logs are being collected
- [ ] Backups are configured
- [ ] SSL/TLS certificates are valid
- [ ] DNS is configured correctly
- [ ] Load testing completed
- [ ] Documentation is updated

## Support

For deployment issues:
1. Check service logs
2. Review documentation
3. Check GitHub issues
4. Contact DevOps team

## Additional Resources

- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Docker Documentation](https://docs.docker.com/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Project Architecture](./MICROSERVICES_ARCHITECTURE.md)
- [Development Guide](./DEVELOPMENT.md)
