/**
 * Evidence Controller
 * Handles evidence collection, verification, and management
 */

const Logger = require('../../../../shared/utils/logger');
const logger = new Logger('evidence-controller');

// In-memory storage for demo (replace with database in production)
const evidence = new Map();

/**
 * Submit evidence for a dispute
 */
exports.submitEvidence = async (req, res, next) => {
  try {
    const { disputeId, submittedBy, type, description, fileUrl, metadata } = req.body;
    
    if (!disputeId || !submittedBy || !type || !description) {
      return res.status(400).json({
        success: false,
        error: { message: 'Missing required fields: disputeId, submittedBy, type, description' }
      });
    }
    
    const evidenceId = `evidence-${disputeId}-${Date.now()}`;
    
    const evidenceRecord = {
      evidenceId,
      disputeId,
      submittedBy,
      type, // document, image, video, audio, testimony, transaction_log
      description,
      fileUrl: fileUrl || null,
      metadata: metadata || {},
      status: 'pending_verification',
      verifiedBy: null,
      verifiedAt: null,
      submittedAt: new Date().toISOString()
    };
    
    evidence.set(evidenceId, evidenceRecord);
    
    logger.info(`Evidence submitted: ${evidenceId} for dispute ${disputeId}`);
    
    res.status(201).json({
      success: true,
      data: evidenceRecord
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Get evidence details
 */
exports.getEvidence = async (req, res, next) => {
  try {
    const { evidenceId } = req.params;
    
    const evidenceRecord = evidence.get(evidenceId);
    
    if (!evidenceRecord) {
      return res.status(404).json({
        success: false,
        error: { message: 'Evidence not found' }
      });
    }
    
    res.json({
      success: true,
      data: evidenceRecord
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Get all evidence for a dispute
 */
exports.getDisputeEvidence = async (req, res, next) => {
  try {
    const { disputeId } = req.params;
    const { type, status } = req.query;
    
    let disputeEvidence = Array.from(evidence.values()).filter(
      e => e.disputeId === disputeId
    );
    
    if (type) {
      disputeEvidence = disputeEvidence.filter(e => e.type === type);
    }
    
    if (status) {
      disputeEvidence = disputeEvidence.filter(e => e.status === status);
    }
    
    res.json({
      success: true,
      data: disputeEvidence,
      total: disputeEvidence.length
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Delete evidence
 */
exports.deleteEvidence = async (req, res, next) => {
  try {
    const { evidenceId } = req.params;
    
    if (!evidence.has(evidenceId)) {
      return res.status(404).json({
        success: false,
        error: { message: 'Evidence not found' }
      });
    }
    
    evidence.delete(evidenceId);
    
    logger.info(`Evidence deleted: ${evidenceId}`);
    
    res.json({
      success: true,
      message: 'Evidence deleted successfully'
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Verify evidence
 */
exports.verifyEvidence = async (req, res, next) => {
  try {
    const { evidenceId } = req.params;
    const { verifiedBy, verificationNotes, isValid } = req.body;
    
    const evidenceRecord = evidence.get(evidenceId);
    
    if (!evidenceRecord) {
      return res.status(404).json({
        success: false,
        error: { message: 'Evidence not found' }
      });
    }
    
    evidenceRecord.status = isValid ? 'verified' : 'rejected';
    evidenceRecord.verifiedBy = verifiedBy;
    evidenceRecord.verifiedAt = new Date().toISOString();
    evidenceRecord.verificationNotes = verificationNotes;
    
    evidence.set(evidenceId, evidenceRecord);
    
    logger.info(`Evidence ${evidenceId} ${isValid ? 'verified' : 'rejected'}`);
    
    res.json({
      success: true,
      data: evidenceRecord
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Get evidence status
 */
exports.getEvidenceStatus = async (req, res, next) => {
  try {
    const { evidenceId } = req.params;
    
    const evidenceRecord = evidence.get(evidenceId);
    
    if (!evidenceRecord) {
      return res.status(404).json({
        success: false,
        error: { message: 'Evidence not found' }
      });
    }
    
    res.json({
      success: true,
      data: {
        evidenceId,
        status: evidenceRecord.status,
        submittedAt: evidenceRecord.submittedAt,
        verifiedAt: evidenceRecord.verifiedAt,
        verifiedBy: evidenceRecord.verifiedBy
      }
    });
  } catch (error) {
    next(error);
  }
};
