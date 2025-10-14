/**
 * Dispute Controller
 * Handles dispute management, arbitration, and resolution workflows
 */

const Logger = require('../../../../shared/utils/logger');
const logger = new Logger('dispute-controller');

// In-memory storage for demo (replace with database in production)
const disputes = new Map();
const resolutionHistory = new Map();

/**
 * Create a new dispute
 */
exports.createDispute = async (req, res, next) => {
  try {
    const { orderId, initiator, respondent, reason, category, priority } = req.body;
    
    if (!orderId || !initiator || !respondent || !reason) {
      return res.status(400).json({
        success: false,
        error: { message: 'Missing required fields: orderId, initiator, respondent, reason' }
      });
    }
    
    const disputeId = `dispute-${orderId}-${Date.now()}`;
    
    const dispute = {
      disputeId,
      orderId,
      initiator,
      respondent,
      reason,
      category: category || 'general',
      priority: priority || 'medium',
      status: 'open',
      resolution: null,
      arbitrator: null,
      mediator: null,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      resolvedAt: null,
      timeline: [
        {
          action: 'created',
          actor: initiator,
          timestamp: new Date().toISOString(),
          note: 'Dispute created'
        }
      ]
    };
    
    disputes.set(disputeId, dispute);
    resolutionHistory.set(disputeId, []);
    
    logger.info(`Dispute created: ${disputeId} for order ${orderId}`);
    
    res.status(201).json({
      success: true,
      data: dispute
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Get dispute details
 */
exports.getDispute = async (req, res, next) => {
  try {
    const { disputeId } = req.params;
    
    const dispute = disputes.get(disputeId);
    
    if (!dispute) {
      return res.status(404).json({
        success: false,
        error: { message: 'Dispute not found' }
      });
    }
    
    const history = resolutionHistory.get(disputeId) || [];
    
    res.json({
      success: true,
      data: {
        ...dispute,
        resolutionHistory: history
      }
    });
  } catch (error) {
    next(error);
  }
};

/**
 * List disputes
 */
exports.listDisputes = async (req, res, next) => {
  try {
    const { orderId, status, priority, category, initiator } = req.query;
    
    let filteredDisputes = Array.from(disputes.values());
    
    if (orderId) {
      filteredDisputes = filteredDisputes.filter(d => d.orderId === orderId);
    }
    
    if (status) {
      filteredDisputes = filteredDisputes.filter(d => d.status === status);
    }
    
    if (priority) {
      filteredDisputes = filteredDisputes.filter(d => d.priority === priority);
    }
    
    if (category) {
      filteredDisputes = filteredDisputes.filter(d => d.category === category);
    }
    
    if (initiator) {
      filteredDisputes = filteredDisputes.filter(d => d.initiator === initiator);
    }
    
    res.json({
      success: true,
      data: filteredDisputes,
      total: filteredDisputes.length
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Update dispute status
 */
exports.updateDisputeStatus = async (req, res, next) => {
  try {
    const { disputeId } = req.params;
    const { status, note, actor } = req.body;
    
    const dispute = disputes.get(disputeId);
    
    if (!dispute) {
      return res.status(404).json({
        success: false,
        error: { message: 'Dispute not found' }
      });
    }
    
    const oldStatus = dispute.status;
    dispute.status = status;
    dispute.updatedAt = new Date().toISOString();
    
    // Add to timeline
    dispute.timeline.push({
      action: 'status_updated',
      actor: actor || 'system',
      timestamp: new Date().toISOString(),
      note: note || `Status changed from ${oldStatus} to ${status}`
    });
    
    disputes.set(disputeId, dispute);
    
    logger.info(`Dispute ${disputeId} status updated to ${status}`);
    
    res.json({
      success: true,
      data: dispute
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Assign arbitrator to dispute
 */
exports.assignArbitrator = async (req, res, next) => {
  try {
    const { disputeId } = req.params;
    const { arbitratorId, arbitratorName } = req.body;
    
    const dispute = disputes.get(disputeId);
    
    if (!dispute) {
      return res.status(404).json({
        success: false,
        error: { message: 'Dispute not found' }
      });
    }
    
    dispute.arbitrator = {
      id: arbitratorId,
      name: arbitratorName,
      assignedAt: new Date().toISOString()
    };
    dispute.status = 'under_review';
    dispute.updatedAt = new Date().toISOString();
    
    // Add to timeline
    dispute.timeline.push({
      action: 'arbitrator_assigned',
      actor: arbitratorId,
      timestamp: new Date().toISOString(),
      note: `Arbitrator ${arbitratorName} assigned`
    });
    
    disputes.set(disputeId, dispute);
    
    logger.info(`Arbitrator assigned to dispute ${disputeId}`);
    
    res.json({
      success: true,
      data: dispute
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Initiate mediation
 */
exports.initiateMediation = async (req, res, next) => {
  try {
    const { disputeId } = req.params;
    const { mediatorId, mediatorName, terms } = req.body;
    
    const dispute = disputes.get(disputeId);
    
    if (!dispute) {
      return res.status(404).json({
        success: false,
        error: { message: 'Dispute not found' }
      });
    }
    
    dispute.mediator = {
      id: mediatorId,
      name: mediatorName,
      terms,
      initiatedAt: new Date().toISOString()
    };
    dispute.status = 'mediation';
    dispute.updatedAt = new Date().toISOString();
    
    // Add to timeline
    dispute.timeline.push({
      action: 'mediation_initiated',
      actor: mediatorId,
      timestamp: new Date().toISOString(),
      note: `Mediation initiated by ${mediatorName}`
    });
    
    disputes.set(disputeId, dispute);
    
    logger.info(`Mediation initiated for dispute ${disputeId}`);
    
    res.json({
      success: true,
      data: dispute
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Resolve dispute
 */
exports.resolveDispute = async (req, res, next) => {
  try {
    const { disputeId } = req.params;
    const { resolution, decision, compensationAmount, notes, resolvedBy } = req.body;
    
    const dispute = disputes.get(disputeId);
    
    if (!dispute) {
      return res.status(404).json({
        success: false,
        error: { message: 'Dispute not found' }
      });
    }
    
    const resolutionData = {
      resolution,
      decision,
      compensationAmount: compensationAmount || 0,
      notes,
      resolvedBy,
      resolvedAt: new Date().toISOString()
    };
    
    dispute.resolution = resolutionData;
    dispute.status = 'resolved';
    dispute.resolvedAt = new Date().toISOString();
    dispute.updatedAt = new Date().toISOString();
    
    // Add to timeline
    dispute.timeline.push({
      action: 'resolved',
      actor: resolvedBy,
      timestamp: new Date().toISOString(),
      note: `Dispute resolved: ${resolution}`
    });
    
    // Add to resolution history
    const history = resolutionHistory.get(disputeId) || [];
    history.push(resolutionData);
    resolutionHistory.set(disputeId, history);
    
    disputes.set(disputeId, dispute);
    
    logger.info(`Dispute ${disputeId} resolved: ${resolution}`);
    
    res.json({
      success: true,
      data: dispute
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Escalate dispute
 */
exports.escalateDispute = async (req, res, next) => {
  try {
    const { disputeId } = req.params;
    const { reason, escalatedBy } = req.body;
    
    const dispute = disputes.get(disputeId);
    
    if (!dispute) {
      return res.status(404).json({
        success: false,
        error: { message: 'Dispute not found' }
      });
    }
    
    dispute.priority = 'high';
    dispute.status = 'escalated';
    dispute.updatedAt = new Date().toISOString();
    
    // Add to timeline
    dispute.timeline.push({
      action: 'escalated',
      actor: escalatedBy,
      timestamp: new Date().toISOString(),
      note: `Dispute escalated: ${reason}`
    });
    
    disputes.set(disputeId, dispute);
    
    logger.warn(`Dispute ${disputeId} escalated`);
    
    res.json({
      success: true,
      data: dispute
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Appeal decision
 */
exports.appealDecision = async (req, res, next) => {
  try {
    const { disputeId } = req.params;
    const { reason, appealedBy } = req.body;
    
    const dispute = disputes.get(disputeId);
    
    if (!dispute) {
      return res.status(404).json({
        success: false,
        error: { message: 'Dispute not found' }
      });
    }
    
    if (dispute.status !== 'resolved') {
      return res.status(400).json({
        success: false,
        error: { message: 'Can only appeal resolved disputes' }
      });
    }
    
    dispute.status = 'appealed';
    dispute.updatedAt = new Date().toISOString();
    
    // Add to timeline
    dispute.timeline.push({
      action: 'appealed',
      actor: appealedBy,
      timestamp: new Date().toISOString(),
      note: `Decision appealed: ${reason}`
    });
    
    disputes.set(disputeId, dispute);
    
    logger.info(`Dispute ${disputeId} decision appealed`);
    
    res.json({
      success: true,
      data: dispute
    });
  } catch (error) {
    next(error);
  }
};
