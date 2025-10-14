/**
 * Authentication Routes
 */

const express = require('express');
const router = express.Router();
const authController = require('../controllers/authController');
const { validateBody } = require('../../../../shared/middleware/validation');
const authSchemas = require('../schemas/authSchemas');

/**
 * POST /api/v1/auth/register
 * Register a new user
 */
router.post(
  '/register',
  validateBody(authSchemas.registerSchema),
  authController.register
);

/**
 * POST /api/v1/auth/login
 * Login user
 */
router.post(
  '/login',
  validateBody(authSchemas.loginSchema),
  authController.login
);

/**
 * POST /api/v1/auth/refresh
 * Refresh access token
 */
router.post(
  '/refresh',
  validateBody(authSchemas.refreshSchema),
  authController.refresh
);

/**
 * POST /api/v1/auth/logout
 * Logout user (invalidate refresh token)
 */
router.post(
  '/logout',
  validateBody(authSchemas.logoutSchema),
  authController.logout
);

module.exports = router;
