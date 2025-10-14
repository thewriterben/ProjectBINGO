/**
 * Statistics Routes
 */

const express = require('express');
const router = express.Router();
const statsController = require('../controllers/statsController');

/**
 * GET /api/v1/stats
 * Get marketplace statistics
 */
router.get('/', statsController.getStats);

module.exports = router;
