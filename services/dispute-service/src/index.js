/**
 * Dispute Resolution Service
 * Handles disputes, arbitration, mediation, and evidence management
 */

const express = require('express');
const cors = require('cors');
const config = require('../../../shared/config');
const Logger = require('../../../shared/utils/logger');
const errorHandler = require('../../../shared/middleware/errorHandler');
const disputeRoutes = require('./routes/disputes');
const evidenceRoutes = require('./routes/evidence');
const healthRoutes = require('./routes/health');

const app = express();
const logger = new Logger('dispute-service');
const PORT = process.env.DISPUTE_SERVICE_PORT || 3008;

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
app.use('/api/v1/disputes', disputeRoutes);
app.use('/api/v1/evidence', evidenceRoutes);

// Error handling
app.use(errorHandler('dispute-service'));

// Start server
app.listen(PORT, () => {
  logger.info(`Dispute Resolution Service started on port ${PORT}`);
});

module.exports = app;
