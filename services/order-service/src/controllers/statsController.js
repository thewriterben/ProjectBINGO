/**
 * Statistics Controller
 */

const { getPostgresPool, getRedisClient } = require('../../../../shared/utils/database');
const Logger = require('../../../../shared/utils/logger');

const logger = new Logger('stats-controller');

/**
 * Get marketplace statistics
 */
exports.getStats = async (req, res, next) => {
  const client = getPostgresPool();
  
  try {
    // Try to get from cache first
    let stats;
    try {
      const redisClient = await getRedisClient();
      const cached = await redisClient.get('marketplace:stats');
      if (cached) {
        stats = JSON.parse(cached);
      }
    } catch (error) {
      logger.warn('Redis cache unavailable', { error: error.message });
    }
    
    if (!stats) {
      // Calculate stats from database
      const totalOrders = await client.query('SELECT COUNT(*) FROM orders');
      const activeOrders = await client.query("SELECT COUNT(*) FROM orders WHERE status IN ('pending', 'assigned', 'in_production')");
      const completedOrders = await client.query("SELECT COUNT(*) FROM orders WHERE status = 'completed'");
      
      stats = {
        totalOrders: parseInt(totalOrders.rows[0].count),
        activeOrders: parseInt(activeOrders.rows[0].count),
        completedOrders: parseInt(completedOrders.rows[0].count),
        timestamp: new Date().toISOString()
      };
      
      // Cache for 5 minutes
      try {
        const redisClient = await getRedisClient();
        await redisClient.setEx('marketplace:stats', 300, JSON.stringify(stats));
      } catch (error) {
        logger.warn('Failed to cache stats', { error: error.message });
      }
    }
    
    res.json({
      success: true,
      stats
    });
  } catch (error) {
    next(error);
  }
};
