/**
 * Supply Chain Service
 * Handles supply chain tracking, vendor management, and inventory
 */

const express = require('express');
const cors = require('cors');
const config = require('../../../shared/config');
const Logger = require('../../../shared/utils/logger');
const errorHandler = require('../../../shared/middleware/errorHandler');
const supplyChainRoutes = require('./routes/supplyChain');
const vendorRoutes = require('./routes/vendors');
const inventoryRoutes = require('./routes/inventory');
const healthRoutes = require('./routes/health');

const app = express();
const logger = new Logger('supply-chain-service');
const PORT = process.env.SUPPLY_CHAIN_SERVICE_PORT || 3009;

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
app.use('/api/v1/supply-chain', supplyChainRoutes);
app.use('/api/v1/vendors', vendorRoutes);
app.use('/api/v1/inventory', inventoryRoutes);

// Error handling
app.use(errorHandler('supply-chain-service'));

// Start server
app.listen(PORT, () => {
  logger.info(`Supply Chain Service started on port ${PORT}`);
});

module.exports = app;
