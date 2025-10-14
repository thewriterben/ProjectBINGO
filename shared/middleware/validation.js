/**
 * Request Validation Middleware
 * Validate request data against schemas
 */

const { ValidationError } = require('../utils/errors');

/**
 * Validate request body against schema
 */
const validateBody = (schema) => {
  return (req, res, next) => {
    const { error, value } = schema.validate(req.body, {
      abortEarly: false,
      stripUnknown: true
    });

    if (error) {
      const details = error.details.reduce((acc, detail) => {
        acc[detail.path.join('.')] = detail.message;
        return acc;
      }, {});

      return next(new ValidationError('Validation failed', details));
    }

    req.body = value;
    next();
  };
};

/**
 * Validate query parameters against schema
 */
const validateQuery = (schema) => {
  return (req, res, next) => {
    const { error, value } = schema.validate(req.query, {
      abortEarly: false,
      stripUnknown: true
    });

    if (error) {
      const details = error.details.reduce((acc, detail) => {
        acc[detail.path.join('.')] = detail.message;
        return acc;
      }, {});

      return next(new ValidationError('Validation failed', details));
    }

    req.query = value;
    next();
  };
};

/**
 * Validate route parameters against schema
 */
const validateParams = (schema) => {
  return (req, res, next) => {
    const { error, value } = schema.validate(req.params, {
      abortEarly: false,
      stripUnknown: true
    });

    if (error) {
      const details = error.details.reduce((acc, detail) => {
        acc[detail.path.join('.')] = detail.message;
        return acc;
      }, {});

      return next(new ValidationError('Validation failed', details));
    }

    req.params = value;
    next();
  };
};

module.exports = {
  validateBody,
  validateQuery,
  validateParams
};
