/**
 * Order Controller
 */

const { getPostgresPool } = require('../../../../shared/utils/database');
const { NotFoundError, ValidationError, AuthorizationError } = require('../../../../shared/utils/errors');
const Logger = require('../../../../shared/utils/logger');

const logger = new Logger('order-controller');

/**
 * Get all orders
 */
exports.getOrders = async (req, res, next) => {
  const client = getPostgresPool();
  
  try {
    const { status, limit = 50, offset = 0 } = req.query;
    
    let query = 'SELECT * FROM orders';
    const params = [];
    
    if (status) {
      query += ' WHERE status = $1';
      params.push(status);
    }
    
    // If authenticated, show user's orders first
    if (req.user) {
      if (status) {
        query += ' AND (client_id = $2 OR manufacturer_id = $2)';
      } else {
        query += ' WHERE (client_id = $1 OR manufacturer_id = $1)';
      }
      params.push(req.user.userId);
    }
    
    query += ` ORDER BY created_at DESC LIMIT $${params.length + 1} OFFSET $${params.length + 2}`;
    params.push(parseInt(limit), parseInt(offset));
    
    const result = await client.query(query, params);
    
    res.json({
      success: true,
      data: {
        orders: result.rows,
        count: result.rows.length
      }
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Create a new order
 */
exports.createOrder = async (req, res, next) => {
  const client = getPostgresPool();
  
  try {
    const {
      specifications,
      quantity,
      material,
      dimensions,
      deadline,
      manufacturerId
    } = req.body;
    
    const clientId = req.user.userId;
    
    // Insert order
    const result = await client.query(
      `INSERT INTO orders (
        client_id, manufacturer_id, specifications, quantity, 
        material, dimensions, deadline, status, created_at, updated_at
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())
      RETURNING *`,
      [
        clientId,
        manufacturerId || null,
        specifications,
        quantity,
        material,
        JSON.stringify(dimensions),
        deadline,
        manufacturerId ? 'assigned' : 'pending'
      ]
    );
    
    const order = result.rows[0];
    
    logger.info('Order created', { orderId: order.id, clientId });
    
    res.status(201).json({
      success: true,
      data: { order }
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Get order by ID
 */
exports.getOrderById = async (req, res, next) => {
  const client = getPostgresPool();
  
  try {
    const { orderId } = req.params;
    
    const result = await client.query(
      'SELECT * FROM orders WHERE id = $1',
      [orderId]
    );
    
    if (result.rows.length === 0) {
      throw new NotFoundError('Order');
    }
    
    const order = result.rows[0];
    
    // Check authorization
    if (req.user) {
      const canView = 
        order.client_id === req.user.userId ||
        order.manufacturer_id === req.user.userId ||
        req.user.role === 'admin';
      
      if (!canView) {
        throw new AuthorizationError();
      }
    }
    
    res.json({
      success: true,
      data: { order }
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Update order
 */
exports.updateOrder = async (req, res, next) => {
  const client = getPostgresPool();
  
  try {
    const { orderId } = req.params;
    const { status, manufacturerId, estimatedCompletion } = req.body;
    
    // Get current order
    const currentOrder = await client.query(
      'SELECT * FROM orders WHERE id = $1',
      [orderId]
    );
    
    if (currentOrder.rows.length === 0) {
      throw new NotFoundError('Order');
    }
    
    const order = currentOrder.rows[0];
    
    // Check authorization
    const canUpdate = 
      order.client_id === req.user.userId ||
      order.manufacturer_id === req.user.userId ||
      req.user.role === 'admin';
    
    if (!canUpdate) {
      throw new AuthorizationError();
    }
    
    // Update order
    const result = await client.query(
      `UPDATE orders 
       SET status = COALESCE($1, status),
           manufacturer_id = COALESCE($2, manufacturer_id),
           estimated_completion = COALESCE($3, estimated_completion),
           updated_at = NOW()
       WHERE id = $4
       RETURNING *`,
      [status, manufacturerId, estimatedCompletion, orderId]
    );
    
    logger.info('Order updated', { orderId, status });
    
    res.json({
      success: true,
      data: { order: result.rows[0] }
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Cancel order
 */
exports.cancelOrder = async (req, res, next) => {
  const client = getPostgresPool();
  
  try {
    const { orderId } = req.params;
    
    // Get current order
    const currentOrder = await client.query(
      'SELECT * FROM orders WHERE id = $1',
      [orderId]
    );
    
    if (currentOrder.rows.length === 0) {
      throw new NotFoundError('Order');
    }
    
    const order = currentOrder.rows[0];
    
    // Only client or admin can cancel
    if (order.client_id !== req.user.userId && req.user.role !== 'admin') {
      throw new AuthorizationError();
    }
    
    // Update status to cancelled
    const result = await client.query(
      `UPDATE orders SET status = 'cancelled', updated_at = NOW()
       WHERE id = $1 RETURNING *`,
      [orderId]
    );
    
    logger.info('Order cancelled', { orderId });
    
    res.json({
      success: true,
      data: { order: result.rows[0] }
    });
  } catch (error) {
    next(error);
  }
};
