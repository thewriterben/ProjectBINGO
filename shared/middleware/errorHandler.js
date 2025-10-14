/**
 * Error Handling Middleware
 * Centralized error handling for all microservices
 */

const Logger = require('../utils/logger');
const { AppError } = require('../utils/errors');

const errorHandler = (serviceName) => {
  const logger = new Logger(serviceName);

  return (err, req, res, next) => {
    let error = err;

    // Convert non-operational errors to AppError
    if (!(error instanceof AppError)) {
      error = new AppError(
        error.message || 'Internal server error',
        error.statusCode || 500,
        error.code || 'INTERNAL_ERROR'
      );
    }

    // Log error
    logger.error(error.message, {
      code: error.code,
      statusCode: error.statusCode,
      stack: error.stack,
      path: req.path,
      method: req.method,
      ip: req.ip
    });

    // Send response
    const response = {
      success: false,
      error: {
        message: error.message,
        code: error.code
      }
    };

    // Include details for validation errors
    if (error.details) {
      response.error.details = error.details;
    }

    // Include stack trace in development
    if (process.env.NODE_ENV === 'development') {
      response.error.stack = error.stack;
    }

    res.status(error.statusCode).json(response);
  };
};

module.exports = errorHandler;
