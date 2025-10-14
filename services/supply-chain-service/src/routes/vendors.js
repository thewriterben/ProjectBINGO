/**
 * Vendor Routes
 * Endpoints for vendor and supplier management
 */

const express = require('express');
const router = express.Router();
const vendorController = require('../controllers/vendorController');

// Vendor management
router.post('/', vendorController.registerVendor);
router.get('/:vendorId', vendorController.getVendor);
router.get('/', vendorController.listVendors);
router.put('/:vendorId', vendorController.updateVendor);
router.delete('/:vendorId', vendorController.removeVendor);

// Vendor performance
router.get('/:vendorId/performance', vendorController.getVendorPerformance);
router.post('/:vendorId/rating', vendorController.rateVendor);

module.exports = router;
