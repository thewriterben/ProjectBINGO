/**
 * Rate Limiting Middleware
 * Protect services from abuse
 */

const config = require('../config');
const { RateLimitError } = require('../utils/errors');

// Simple in-memory rate limiter
// In production, use Redis-based rate limiter
class RateLimiter {
  constructor() {
    this.requests = new Map();
  }

  isRateLimited(key, windowMs, maxRequests) {
    const now = Date.now();
    const userRequests = this.requests.get(key) || [];
    
    // Remove old requests outside the window
    const recentRequests = userRequests.filter(time => now - time < windowMs);
    
    if (recentRequests.length >= maxRequests) {
      return true;
    }
    
    recentRequests.push(now);
    this.requests.set(key, recentRequests);
    
    return false;
  }

  reset() {
    this.requests.clear();
  }
}

const limiter = new RateLimiter();

/**
 * Rate limiting middleware
 */
const rateLimit = (options = {}) => {
  const windowMs = options.windowMs || config.rateLimit.windowMs;
  const maxRequests = options.maxRequests || config.rateLimit.maxRequests;
  const keyGenerator = options.keyGenerator || ((req) => req.ip || req.connection.remoteAddress);

  return (req, res, next) => {
    const key = keyGenerator(req);
    
    if (limiter.isRateLimited(key, windowMs, maxRequests)) {
      return next(new RateLimitError());
    }
    
    next();
  };
};

module.exports = {
  rateLimit,
  limiter
};
