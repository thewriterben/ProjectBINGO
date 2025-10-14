/**
 * Vendor Controller
 * Handles vendor and supplier management
 */

const Logger = require('../../../../shared/utils/logger');
const logger = new Logger('vendor-controller');

const vendors = new Map();
const vendorRatings = new Map();

exports.registerVendor = async (req, res, next) => {
  try {
    const { name, type, contact, capabilities, location } = req.body;
    
    if (!name || !type) {
      return res.status(400).json({
        success: false,
        error: { message: 'Missing required fields' }
      });
    }
    
    const vendorId = `vendor-${Date.now()}`;
    const vendor = {
      vendorId,
      name,
      type,
      contact,
      capabilities: capabilities || [],
      location,
      status: 'active',
      rating: 5.0,
      totalOrders: 0,
      registeredAt: new Date().toISOString()
    };
    
    vendors.set(vendorId, vendor);
    vendorRatings.set(vendorId, []);
    
    logger.info(`Vendor registered: ${vendorId}`);
    res.status(201).json({ success: true, data: vendor });
  } catch (error) {
    next(error);
  }
};

exports.getVendor = async (req, res, next) => {
  try {
    const { vendorId } = req.params;
    const vendor = vendors.get(vendorId);
    
    if (!vendor) {
      return res.status(404).json({
        success: false,
        error: { message: 'Vendor not found' }
      });
    }
    
    res.json({ success: true, data: vendor });
  } catch (error) {
    next(error);
  }
};

exports.listVendors = async (req, res, next) => {
  try {
    const { type, status } = req.query;
    let vendorList = Array.from(vendors.values());
    
    if (type) vendorList = vendorList.filter(v => v.type === type);
    if (status) vendorList = vendorList.filter(v => v.status === status);
    
    res.json({ success: true, data: vendorList, total: vendorList.length });
  } catch (error) {
    next(error);
  }
};

exports.updateVendor = async (req, res, next) => {
  try {
    const { vendorId } = req.params;
    const vendor = vendors.get(vendorId);
    
    if (!vendor) {
      return res.status(404).json({
        success: false,
        error: { message: 'Vendor not found' }
      });
    }
    
    const updated = { ...vendor, ...req.body, vendorId, updatedAt: new Date().toISOString() };
    vendors.set(vendorId, updated);
    
    res.json({ success: true, data: updated });
  } catch (error) {
    next(error);
  }
};

exports.removeVendor = async (req, res, next) => {
  try {
    const { vendorId } = req.params;
    
    if (!vendors.has(vendorId)) {
      return res.status(404).json({
        success: false,
        error: { message: 'Vendor not found' }
      });
    }
    
    vendors.delete(vendorId);
    res.json({ success: true, message: 'Vendor removed' });
  } catch (error) {
    next(error);
  }
};

exports.getVendorPerformance = async (req, res, next) => {
  try {
    const { vendorId } = req.params;
    const vendor = vendors.get(vendorId);
    
    if (!vendor) {
      return res.status(404).json({
        success: false,
        error: { message: 'Vendor not found' }
      });
    }
    
    const ratings = vendorRatings.get(vendorId) || [];
    
    res.json({
      success: true,
      data: {
        vendorId,
        rating: vendor.rating,
        totalOrders: vendor.totalOrders,
        totalRatings: ratings.length,
        recentRatings: ratings.slice(-10)
      }
    });
  } catch (error) {
    next(error);
  }
};

exports.rateVendor = async (req, res, next) => {
  try {
    const { vendorId } = req.params;
    const { rating, comment, ratedBy } = req.body;
    
    const vendor = vendors.get(vendorId);
    if (!vendor) {
      return res.status(404).json({
        success: false,
        error: { message: 'Vendor not found' }
      });
    }
    
    const ratingEntry = {
      rating,
      comment,
      ratedBy,
      timestamp: new Date().toISOString()
    };
    
    const ratings = vendorRatings.get(vendorId) || [];
    ratings.push(ratingEntry);
    vendorRatings.set(vendorId, ratings);
    
    // Update average rating
    const avgRating = ratings.reduce((sum, r) => sum + r.rating, 0) / ratings.length;
    vendor.rating = Math.round(avgRating * 10) / 10;
    vendors.set(vendorId, vendor);
    
    res.json({ success: true, data: ratingEntry });
  } catch (error) {
    next(error);
  }
};
