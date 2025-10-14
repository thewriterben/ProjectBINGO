/**
 * Supply Chain Routes
 * Endpoints for supply chain tracking and traceability
 */

const express = require('express');
const router = express.Router();
const supplyChainController = require('../controllers/supplyChainController');

// Supply chain tracking
router.post('/track', supplyChainController.createTrackingEntry);
router.get('/track/:orderId', supplyChainController.getTrackingInfo);
router.get('/track/:orderId/history', supplyChainController.getTrackingHistory);

// Quality assurance
router.post('/quality-check', supplyChainController.createQualityCheck);
router.get('/quality-check/:orderId', supplyChainController.getQualityChecks);

// Compliance monitoring
router.post('/compliance', supplyChainController.recordCompliance);
router.get('/compliance/:orderId', supplyChainController.getComplianceRecords);

// Traceability
router.get('/trace/:itemId', supplyChainController.traceItem);

module.exports = router;
