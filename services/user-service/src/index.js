/**
 * User Service
 * Handles user authentication, registration, and profile management
 */

const express = require('express');
const cors = require('cors');
const path = require('path');

// Import shared modules
const config = require('../../../shared/config');
const Logger = require('../../../shared/utils/logger');
const errorHandler = require('../../../shared/middleware/errorHandler');
const { rateLimit } = require('../../../shared/middleware/rateLimit');

// Import routes
const authRoutes = require('./routes/auth');
const userRoutes = require('./routes/users');
const healthRoutes = require('./routes/health');

const app = express();
const logger = new Logger('user-service');
const PORT = process.env.USER_SERVICE_PORT || 3001;

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
app.use('/api/v1/auth', authRoutes);
app.use('/api/v1/users', userRoutes);

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
app.use(errorHandler('user-service'));

// Start server
app.listen(PORT, () => {
  logger.info(`User Service started on port ${PORT}`);
  logger.info('Available routes:');
  logger.info('  POST   /api/v1/auth/register');
  logger.info('  POST   /api/v1/auth/login');
  logger.info('  POST   /api/v1/auth/refresh');
  logger.info('  POST   /api/v1/auth/logout');
  logger.info('  GET    /api/v1/users/profile');
  logger.info('  PUT    /api/v1/users/profile');
  logger.info('  GET    /api/v1/health');
});

module.exports = app;
