/**
 * Dispute Routes
 * Endpoints for dispute management, arbitration, and mediation
 */

const express = require('express');
const router = express.Router();
const disputeController = require('../controllers/disputeController');

// Dispute management
router.post('/', disputeController.createDispute);
router.get('/:disputeId', disputeController.getDispute);
router.get('/', disputeController.listDisputes);
router.put('/:disputeId/status', disputeController.updateDisputeStatus);

// Arbitration and mediation
router.post('/:disputeId/assign-arbitrator', disputeController.assignArbitrator);
router.post('/:disputeId/mediate', disputeController.initiateMediation);
router.post('/:disputeId/resolve', disputeController.resolveDispute);

// Dispute actions
router.post('/:disputeId/escalate', disputeController.escalateDispute);
router.post('/:disputeId/appeal', disputeController.appealDecision);

module.exports = router;
