/**
 * Supply Chain Controller
 * Handles supply chain tracking, quality assurance, and compliance
 */

const Logger = require('../../../../shared/utils/logger');
const logger = new Logger('supply-chain-controller');

// In-memory storage for demo
const trackingEntries = new Map();
const qualityChecks = new Map();
const complianceRecords = new Map();

/**
 * Create tracking entry
 */
exports.createTrackingEntry = async (req, res, next) => {
  try {
    const { orderId, stage, location, status, notes, metadata } = req.body;
    
    if (!orderId || !stage || !location || !status) {
      return res.status(400).json({
        success: false,
        error: { message: 'Missing required fields' }
      });
    }
    
    const entryId = `track-${orderId}-${Date.now()}`;
    const entry = {
      entryId,
      orderId,
      stage,
      location,
      status,
      notes,
      metadata,
      timestamp: new Date().toISOString()
    };
    
    if (!trackingEntries.has(orderId)) {
      trackingEntries.set(orderId, []);
    }
    
    trackingEntries.get(orderId).push(entry);
    logger.info(`Tracking entry created for order ${orderId}`);
    
    res.status(201).json({ success: true, data: entry });
  } catch (error) {
    next(error);
  }
};

/**
 * Get tracking info
 */
exports.getTrackingInfo = async (req, res, next) => {
  try {
    const { orderId } = req.params;
    const entries = trackingEntries.get(orderId) || [];
    const latest = entries.length > 0 ? entries[entries.length - 1] : null;
    
    res.json({
      success: true,
      data: {
        orderId,
        currentStage: latest ? latest.stage : null,
        currentStatus: latest ? latest.status : null,
        totalEntries: entries.length,
        latestUpdate: latest
      }
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Get tracking history
 */
exports.getTrackingHistory = async (req, res, next) => {
  try {
    const { orderId } = req.params;
    const entries = trackingEntries.get(orderId) || [];
    
    res.json({
      success: true,
      data: entries,
      total: entries.length
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Create quality check
 */
exports.createQualityCheck = async (req, res, next) => {
  try {
    const { orderId, inspector, checkType, result, score, notes } = req.body;
    
    const checkId = `qc-${orderId}-${Date.now()}`;
    const check = {
      checkId,
      orderId,
      inspector,
      checkType,
      result,
      score,
      notes,
      timestamp: new Date().toISOString()
    };
    
    if (!qualityChecks.has(orderId)) {
      qualityChecks.set(orderId, []);
    }
    
    qualityChecks.get(orderId).push(check);
    logger.info(`Quality check created for order ${orderId}`);
    
    res.status(201).json({ success: true, data: check });
  } catch (error) {
    next(error);
  }
};

/**
 * Get quality checks
 */
exports.getQualityChecks = async (req, res, next) => {
  try {
    const { orderId } = req.params;
    const checks = qualityChecks.get(orderId) || [];
    
    res.json({ success: true, data: checks, total: checks.length });
  } catch (error) {
    next(error);
  }
};

/**
 * Record compliance
 */
exports.recordCompliance = async (req, res, next) => {
  try {
    const { orderId, standard, status, certificationId, notes } = req.body;
    
    const recordId = `compliance-${orderId}-${Date.now()}`;
    const record = {
      recordId,
      orderId,
      standard,
      status,
      certificationId,
      notes,
      timestamp: new Date().toISOString()
    };
    
    if (!complianceRecords.has(orderId)) {
      complianceRecords.set(orderId, []);
    }
    
    complianceRecords.get(orderId).push(record);
    logger.info(`Compliance recorded for order ${orderId}`);
    
    res.status(201).json({ success: true, data: record });
  } catch (error) {
    next(error);
  }
};

/**
 * Get compliance records
 */
exports.getComplianceRecords = async (req, res, next) => {
  try {
    const { orderId } = req.params;
    const records = complianceRecords.get(orderId) || [];
    
    res.json({ success: true, data: records, total: records.length });
  } catch (error) {
    next(error);
  }
};

/**
 * Trace item
 */
exports.traceItem = async (req, res, next) => {
  try {
    const { itemId } = req.params;
    
    const trace = {
      itemId,
      tracking: Array.from(trackingEntries.values()).flat().filter(e => e.metadata?.itemId === itemId),
      qualityChecks: Array.from(qualityChecks.values()).flat().filter(q => q.metadata?.itemId === itemId),
      compliance: Array.from(complianceRecords.values()).flat().filter(c => c.metadata?.itemId === itemId)
    };
    
    res.json({ success: true, data: trace });
  } catch (error) {
    next(error);
  }
};
