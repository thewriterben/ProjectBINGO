/**
 * Inventory Controller
 * Handles inventory tracking and management
 */

const Logger = require('../../../../shared/utils/logger');
const logger = new Logger('inventory-controller');

const inventory = new Map();
const stockHistory = new Map();

exports.addInventoryItem = async (req, res, next) => {
  try {
    const { sku, name, category, quantity, unit, reorderLevel, location } = req.body;
    
    if (!sku || !name || quantity === undefined) {
      return res.status(400).json({
        success: false,
        error: { message: 'Missing required fields' }
      });
    }
    
    const itemId = `item-${Date.now()}`;
    const item = {
      itemId,
      sku,
      name,
      category,
      quantity,
      unit: unit || 'units',
      reorderLevel: reorderLevel || 10,
      location,
      status: 'active',
      createdAt: new Date().toISOString()
    };
    
    inventory.set(itemId, item);
    stockHistory.set(itemId, []);
    
    logger.info(`Inventory item added: ${itemId}`);
    res.status(201).json({ success: true, data: item });
  } catch (error) {
    next(error);
  }
};

exports.getInventoryItem = async (req, res, next) => {
  try {
    const { itemId } = req.params;
    const item = inventory.get(itemId);
    
    if (!item) {
      return res.status(404).json({
        success: false,
        error: { message: 'Item not found' }
      });
    }
    
    res.json({ success: true, data: item });
  } catch (error) {
    next(error);
  }
};

exports.listInventoryItems = async (req, res, next) => {
  try {
    const { category, status } = req.query;
    let items = Array.from(inventory.values());
    
    if (category) items = items.filter(i => i.category === category);
    if (status) items = items.filter(i => i.status === status);
    
    res.json({ success: true, data: items, total: items.length });
  } catch (error) {
    next(error);
  }
};

exports.updateInventoryItem = async (req, res, next) => {
  try {
    const { itemId } = req.params;
    const item = inventory.get(itemId);
    
    if (!item) {
      return res.status(404).json({
        success: false,
        error: { message: 'Item not found' }
      });
    }
    
    const updated = { ...item, ...req.body, itemId, updatedAt: new Date().toISOString() };
    inventory.set(itemId, updated);
    
    res.json({ success: true, data: updated });
  } catch (error) {
    next(error);
  }
};

exports.removeInventoryItem = async (req, res, next) => {
  try {
    const { itemId } = req.params;
    
    if (!inventory.has(itemId)) {
      return res.status(404).json({
        success: false,
        error: { message: 'Item not found' }
      });
    }
    
    inventory.delete(itemId);
    res.json({ success: true, message: 'Item removed' });
  } catch (error) {
    next(error);
  }
};

exports.updateStock = async (req, res, next) => {
  try {
    const { itemId } = req.params;
    const { quantity, type, notes } = req.body;
    
    const item = inventory.get(itemId);
    if (!item) {
      return res.status(404).json({
        success: false,
        error: { message: 'Item not found' }
      });
    }
    
    const entry = {
      type: type || 'adjustment',
      quantity,
      previousQuantity: item.quantity,
      newQuantity: type === 'add' ? item.quantity + quantity : item.quantity - quantity,
      notes,
      timestamp: new Date().toISOString()
    };
    
    item.quantity = entry.newQuantity;
    inventory.set(itemId, item);
    
    const history = stockHistory.get(itemId) || [];
    history.push(entry);
    stockHistory.set(itemId, history);
    
    res.json({ success: true, data: entry });
  } catch (error) {
    next(error);
  }
};

exports.getStockHistory = async (req, res, next) => {
  try {
    const { itemId } = req.params;
    const history = stockHistory.get(itemId) || [];
    
    res.json({ success: true, data: history, total: history.length });
  } catch (error) {
    next(error);
  }
};

exports.getInventoryAlerts = async (req, res, next) => {
  try {
    const items = Array.from(inventory.values());
    const alerts = items
      .filter(item => item.quantity <= item.reorderLevel)
      .map(item => ({
        itemId: item.itemId,
        sku: item.sku,
        name: item.name,
        currentQuantity: item.quantity,
        reorderLevel: item.reorderLevel,
        severity: item.quantity === 0 ? 'critical' : 'warning'
      }));
    
    res.json({ success: true, data: alerts, total: alerts.length });
  } catch (error) {
    next(error);
  }
};
