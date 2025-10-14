/**
 * Order Routes
 */

const express = require('express');
const router = express.Router();
const orderController = require('../controllers/orderController');
const { authenticate, optionalAuth } = require('../../../../shared/middleware/auth');

/**
 * GET /api/v1/orders
 * Get all orders (optionally filtered)
 */
router.get('/', optionalAuth, orderController.getOrders);

/**
 * POST /api/v1/orders
 * Create a new order
 */
router.post('/', authenticate, orderController.createOrder);

/**
 * GET /api/v1/orders/:orderId
 * Get order by ID
 */
router.get('/:orderId', optionalAuth, orderController.getOrderById);

/**
 * PUT /api/v1/orders/:orderId
 * Update order status
 */
router.put('/:orderId', authenticate, orderController.updateOrder);

/**
 * DELETE /api/v1/orders/:orderId
 * Cancel order
 */
router.delete('/:orderId', authenticate, orderController.cancelOrder);

module.exports = router;
