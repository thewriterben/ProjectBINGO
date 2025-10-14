/**
 * Evidence Routes
 * Endpoints for evidence collection and management
 */

const express = require('express');
const router = express.Router();
const evidenceController = require('../controllers/evidenceController');

// Evidence management
router.post('/', evidenceController.submitEvidence);
router.get('/:evidenceId', evidenceController.getEvidence);
router.get('/dispute/:disputeId', evidenceController.getDisputeEvidence);
router.delete('/:evidenceId', evidenceController.deleteEvidence);

// Evidence verification
router.post('/:evidenceId/verify', evidenceController.verifyEvidence);
router.get('/:evidenceId/status', evidenceController.getEvidenceStatus);

module.exports = router;
