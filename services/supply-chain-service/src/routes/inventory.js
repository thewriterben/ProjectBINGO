/**
 * Inventory Routes
 * Endpoints for inventory tracking and management
 */

const express = require('express');
const router = express.Router();
const inventoryController = require('../controllers/inventoryController');

// Inventory management
router.post('/items', inventoryController.addInventoryItem);
router.get('/items/:itemId', inventoryController.getInventoryItem);
router.get('/items', inventoryController.listInventoryItems);
router.put('/items/:itemId', inventoryController.updateInventoryItem);
router.delete('/items/:itemId', inventoryController.removeInventoryItem);

// Stock management
router.post('/items/:itemId/stock', inventoryController.updateStock);
router.get('/items/:itemId/stock-history', inventoryController.getStockHistory);

// Alerts
router.get('/alerts', inventoryController.getInventoryAlerts);

module.exports = router;
