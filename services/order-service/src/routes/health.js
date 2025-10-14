/**
 * Health Check Routes
 */

const express = require('express');
const router = express.Router();
const { getPostgresPool } = require('../../../../shared/utils/database');

router.get('/', async (req, res) => {
  try {
    const pgPool = getPostgresPool();
    await pgPool.query('SELECT NOW()');

    res.json({
      status: 'healthy',
      timestamp: new Date().toISOString(),
      service: 'order-service',
      version: '1.0.0',
      database: {
        postgres: 'connected'
      }
    });
  } catch (error) {
    res.status(503).json({
      status: 'unhealthy',
      timestamp: new Date().toISOString(),
      service: 'order-service',
      error: error.message
    });
  }
});

module.exports = router;
