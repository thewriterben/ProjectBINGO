/**
 * API Gateway
 * Main entry point for all client requests
 * Routes requests to appropriate microservices
 */

const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const { createProxyMiddleware } = require('http-proxy-middleware');

const config = require('../../../shared/config');
const Logger = require('../../../shared/utils/logger');
const errorHandler = require('../../../shared/middleware/errorHandler');
const { rateLimit } = require('../../../shared/middleware/rateLimit');

const app = express();
const logger = new Logger('api-gateway');
const PORT = process.env.API_GATEWAY_PORT || 3000;

// Security middleware
app.use(helmet());
app.use(cors(config.cors));

// Body parsing
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Rate limiting
app.use(rateLimit());

// Request logging
app.use((req, res, next) => {
  logger.info(`${req.method} ${req.path}`, {
    ip: req.ip,
    userAgent: req.get('user-agent')
  });
  next();
});

// Health check for gateway itself
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    service: 'api-gateway',
    version: '1.0.0'
  });
});

// Service proxy routes
const services = [
  {
    path: '/api/v1/auth',
    target: config.services.userService,
    name: 'user-service (auth)'
  },
  {
    path: '/api/v1/users',
    target: config.services.userService,
    name: 'user-service (users)'
  },
  {
    path: '/api/v1/manufacturers',
    target: config.services.manufacturerService,
    name: 'manufacturer-service'
  },
  {
    path: '/api/v1/orders',
    target: config.services.orderService,
    name: 'order-service'
  },
  {
    path: '/api/v1/payments',
    target: config.services.paymentService,
    name: 'payment-service'
  },
  {
    path: '/api/v1/ai',
    target: config.services.aiService,
    name: 'ai-service'
  },
  {
    path: '/api/v1/notifications',
    target: config.services.notificationService,
    name: 'notification-service'
  },
  {
    path: '/api/v1/files',
    target: config.services.fileService,
    name: 'file-service'
  }
];

// Create proxy for each service
services.forEach(service => {
  app.use(
    service.path,
    createProxyMiddleware({
      target: service.target,
      changeOrigin: true,
      onProxyReq: (proxyReq, req) => {
        logger.debug(`Proxying to ${service.name}`, {
          path: req.path,
          method: req.method
        });
      },
      onError: (err, req, res) => {
        logger.error(`Proxy error for ${service.name}`, {
          error: err.message,
          path: req.path
        });
        
        res.status(503).json({
          success: false,
          error: {
            message: `Service temporarily unavailable: ${service.name}`,
            code: 'SERVICE_UNAVAILABLE'
          }
        });
      }
    })
  );
  
  logger.info(`Proxying ${service.path} -> ${service.target} (${service.name})`);
});

// Backward compatibility with old API endpoints (from original backend)
app.use('/api/health', createProxyMiddleware({
  target: config.services.userService,
  pathRewrite: { '^/api/health': '/api/v1/health' },
  changeOrigin: true
}));

app.use('/api/orders', createProxyMiddleware({
  target: config.services.orderService,
  pathRewrite: { '^/api/orders': '/api/v1/orders' },
  changeOrigin: true
}));

app.use('/api/manufacturers', createProxyMiddleware({
  target: config.services.manufacturerService,
  pathRewrite: { '^/api/manufacturers': '/api/v1/manufacturers' },
  changeOrigin: true
}));

app.use('/api/ai', createProxyMiddleware({
  target: config.services.aiService,
  pathRewrite: { '^/api/ai': '/api/v1/ai' },
  changeOrigin: true
}));

app.use('/api/stats', createProxyMiddleware({
  target: config.services.orderService,
  pathRewrite: { '^/api/stats': '/api/v1/stats' },
  changeOrigin: true
}));

// 404 handler
app.use((req, res) => {
  res.status(404).json({
    success: false,
    error: {
      message: 'Route not found',
      code: 'NOT_FOUND'
    }
  });
});

// Error handler
app.use(errorHandler('api-gateway'));

// Start server
app.listen(PORT, () => {
  logger.info(`API Gateway started on port ${PORT}`);
  logger.info('Service routing:');
  services.forEach(service => {
    logger.info(`  ${service.path} -> ${service.target}`);
  });
});

module.exports = app;
