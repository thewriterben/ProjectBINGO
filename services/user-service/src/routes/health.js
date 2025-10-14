/**
 * Health Check Routes
 */

const express = require('express');
const router = express.Router();
const { getPostgresPool, getRedisClient } = require('../../../../shared/utils/database');

/**
 * Health check endpoint
 */
router.get('/', async (req, res) => {
  try {
    // Check database connections
    const pgPool = getPostgresPool();
    const pgHealth = await pgPool.query('SELECT NOW()');
    
    let redisHealth = false;
    try {
      const redisClient = await getRedisClient();
      redisHealth = await redisClient.ping() === 'PONG';
    } catch (error) {
      // Redis is optional for health check
    }

    res.json({
      status: 'healthy',
      timestamp: new Date().toISOString(),
      service: 'user-service',
      version: '1.0.0',
      database: {
        postgres: pgHealth ? 'connected' : 'disconnected',
        redis: redisHealth ? 'connected' : 'disconnected'
      }
    });
  } catch (error) {
    res.status(503).json({
      status: 'unhealthy',
      timestamp: new Date().toISOString(),
      service: 'user-service',
      error: error.message
    });
  }
});

module.exports = router;
