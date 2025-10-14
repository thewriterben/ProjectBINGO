/**
 * User Routes
 */

const express = require('express');
const router = express.Router();
const userController = require('../controllers/userController');
const { authenticate } = require('../../../../shared/middleware/auth');
const { validateBody } = require('../../../../shared/middleware/validation');
const userSchemas = require('../schemas/userSchemas');

/**
 * GET /api/v1/users/profile
 * Get current user profile
 */
router.get(
  '/profile',
  authenticate,
  userController.getProfile
);

/**
 * PUT /api/v1/users/profile
 * Update current user profile
 */
router.put(
  '/profile',
  authenticate,
  validateBody(userSchemas.updateProfileSchema),
  userController.updateProfile
);

/**
 * GET /api/v1/users/:userId
 * Get user by ID (admin only in production)
 */
router.get(
  '/:userId',
  authenticate,
  userController.getUserById
);

module.exports = router;
