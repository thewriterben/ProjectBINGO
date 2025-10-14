/**
 * IoT Service
 * Handles real-time device tracking, sensor data collection, and geolocation
 */

const express = require('express');
const cors = require('cors');
const config = require('../../../shared/config');
const Logger = require('../../../shared/utils/logger');
const errorHandler = require('../../../shared/middleware/errorHandler');
const deviceRoutes = require('./routes/devices');
const trackingRoutes = require('./routes/tracking');
const healthRoutes = require('./routes/health');

const app = express();
const logger = new Logger('iot-service');
const PORT = process.env.IOT_SERVICE_PORT || 3007;

// Middleware
app.use(cors(config.cors));
app.use(express.json());

// Request logging
app.use((req, res, next) => {
  logger.info(`${req.method} ${req.path}`, {
    query: req.query,
    body: req.body
  });
  next();
});

// Routes
app.use('/api/v1', healthRoutes);
app.use('/api/v1/devices', deviceRoutes);
app.use('/api/v1/tracking', trackingRoutes);

// Error handling
app.use(errorHandler('iot-service'));

// Start server
app.listen(PORT, () => {
  logger.info(`IoT Service started on port ${PORT}`);
});

module.exports = app;
