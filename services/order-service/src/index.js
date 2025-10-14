/**
 * Order Service
 * Handles order lifecycle, tracking, and workflow management
 */

const express = require('express');
const cors = require('cors');

const config = require('../../../shared/config');
const Logger = require('../../../shared/utils/logger');
const errorHandler = require('../../../shared/middleware/errorHandler');
const { rateLimit } = require('../../../shared/middleware/rateLimit');

const healthRoutes = require('./routes/health');
const orderRoutes = require('./routes/orders');
const statsRoutes = require('./routes/stats');

const app = express();
const logger = new Logger('order-service');
const PORT = process.env.ORDER_SERVICE_PORT || 3003;

// Middleware
app.use(cors(config.cors));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(rateLimit());

// Request logging
app.use((req, res, next) => {
  logger.info(`${req.method} ${req.path}`, {
    ip: req.ip,
    userAgent: req.get('user-agent')
  });
  next();
});

// Routes
app.use('/api/v1/health', healthRoutes);
app.use('/api/v1/orders', orderRoutes);
app.use('/api/v1/stats', statsRoutes);

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
app.use(errorHandler('order-service'));

// Start server
app.listen(PORT, () => {
  logger.info(`Order Service started on port ${PORT}`);
  logger.info('Available routes:');
  logger.info('  GET    /api/v1/orders');
  logger.info('  POST   /api/v1/orders');
  logger.info('  GET    /api/v1/orders/:orderId');
  logger.info('  PUT    /api/v1/orders/:orderId');
  logger.info('  GET    /api/v1/stats');
  logger.info('  GET    /api/v1/health');
});

module.exports = app;
