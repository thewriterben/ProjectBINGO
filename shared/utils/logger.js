/**
 * Shared Logger Utility
 * Standardized logging across all microservices
 */

const config = require('../config');

class Logger {
  constructor(serviceName) {
    this.serviceName = serviceName;
    this.level = config.logging.level;
  }

  formatMessage(level, message, meta = {}) {
    const timestamp = new Date().toISOString();
    
    if (config.logging.format === 'json') {
      return JSON.stringify({
        timestamp,
        level,
        service: this.serviceName,
        message,
        ...meta
      });
    }
    
    return `[${timestamp}] [${level.toUpperCase()}] [${this.serviceName}] ${message} ${JSON.stringify(meta)}`;
  }

  log(level, message, meta = {}) {
    const levels = { error: 0, warn: 1, info: 2, debug: 3 };
    const currentLevel = levels[this.level] || 2;
    const messageLevel = levels[level] || 2;

    if (messageLevel <= currentLevel) {
      const formattedMessage = this.formatMessage(level, message, meta);
      
      if (level === 'error') {
        console.error(formattedMessage);
      } else if (level === 'warn') {
        console.warn(formattedMessage);
      } else {
        console.log(formattedMessage);
      }
    }
  }

  error(message, meta = {}) {
    this.log('error', message, meta);
  }

  warn(message, meta = {}) {
    this.log('warn', message, meta);
  }

  info(message, meta = {}) {
    this.log('info', message, meta);
  }

  debug(message, meta = {}) {
    this.log('debug', message, meta);
  }
}

module.exports = Logger;
