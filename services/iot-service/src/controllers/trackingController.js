/**
 * Real-time Tracking Controller
 * Handles geolocation, real-time tracking, and alerts
 */

const Logger = require('../../../../shared/utils/logger');
const logger = new Logger('iot-tracking-controller');

// In-memory storage for demo (replace with database in production)
const locations = new Map();
const locationHistory = new Map();
const alerts = new Map();
const geofences = new Map();

/**
 * Update location for an order
 */
exports.updateLocation = async (req, res, next) => {
  try {
    const { orderId, latitude, longitude, altitude, accuracy, metadata } = req.body;
    
    if (!orderId || latitude === undefined || longitude === undefined) {
      return res.status(400).json({
        success: false,
        error: { message: 'Missing required fields: orderId, latitude, longitude' }
      });
    }
    
    const location = {
      orderId,
      latitude,
      longitude,
      altitude: altitude || null,
      accuracy: accuracy || null,
      metadata,
      timestamp: new Date().toISOString()
    };
    
    // Update current location
    locations.set(orderId, location);
    
    // Add to history
    const history = locationHistory.get(orderId) || [];
    history.push(location);
    
    // Keep only last 1000 locations
    if (history.length > 1000) {
      history.shift();
    }
    
    locationHistory.set(orderId, history);
    
    // Check geofence violations
    checkGeofenceViolations(orderId, latitude, longitude);
    
    logger.info(`Location updated for order: ${orderId}`);
    
    res.json({
      success: true,
      data: location
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Get current location for an order
 */
exports.getOrderLocation = async (req, res, next) => {
  try {
    const { orderId } = req.params;
    
    const location = locations.get(orderId);
    
    if (!location) {
      return res.status(404).json({
        success: false,
        error: { message: 'Location not found for this order' }
      });
    }
    
    res.json({
      success: true,
      data: location
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Get location history for an order
 */
exports.getLocationHistory = async (req, res, next) => {
  try {
    const { orderId } = req.params;
    const { limit = 100, startTime, endTime } = req.query;
    
    let history = locationHistory.get(orderId) || [];
    
    // Filter by time range
    if (startTime) {
      history = history.filter(l => new Date(l.timestamp) >= new Date(startTime));
    }
    
    if (endTime) {
      history = history.filter(l => new Date(l.timestamp) <= new Date(endTime));
    }
    
    // Limit results
    const limitNum = parseInt(limit);
    history = history.slice(-limitNum);
    
    res.json({
      success: true,
      data: history,
      total: history.length
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Get real-time data for an order
 */
exports.getRealtimeData = async (req, res, next) => {
  try {
    const { orderId } = req.params;
    
    const location = locations.get(orderId);
    const history = locationHistory.get(orderId) || [];
    const orderAlerts = Array.from(alerts.values()).filter(a => a.orderId === orderId);
    const orderGeofences = Array.from(geofences.values()).filter(g => g.orderId === orderId);
    
    res.json({
      success: true,
      data: {
        orderId,
        currentLocation: location || null,
        locationCount: history.length,
        activeAlerts: orderAlerts.filter(a => a.status === 'active').length,
        totalAlerts: orderAlerts.length,
        geofences: orderGeofences.length,
        lastUpdate: location ? location.timestamp : null
      }
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Create an alert
 */
exports.createAlert = async (req, res, next) => {
  try {
    const { orderId, type, message, severity, metadata } = req.body;
    
    if (!orderId || !type || !message) {
      return res.status(400).json({
        success: false,
        error: { message: 'Missing required fields: orderId, type, message' }
      });
    }
    
    const alertId = `alert-${orderId}-${Date.now()}`;
    
    const alert = {
      alertId,
      orderId,
      type,
      message,
      severity: severity || 'medium',
      metadata,
      status: 'active',
      createdAt: new Date().toISOString(),
      resolvedAt: null
    };
    
    alerts.set(alertId, alert);
    
    logger.info(`Alert created: ${alertId} for order ${orderId}`);
    
    res.status(201).json({
      success: true,
      data: alert
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Get alerts for an order
 */
exports.getAlerts = async (req, res, next) => {
  try {
    const { orderId } = req.params;
    const { status, severity, type } = req.query;
    
    let orderAlerts = Array.from(alerts.values()).filter(a => a.orderId === orderId);
    
    if (status) {
      orderAlerts = orderAlerts.filter(a => a.status === status);
    }
    
    if (severity) {
      orderAlerts = orderAlerts.filter(a => a.severity === severity);
    }
    
    if (type) {
      orderAlerts = orderAlerts.filter(a => a.type === type);
    }
    
    res.json({
      success: true,
      data: orderAlerts,
      total: orderAlerts.length
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Create a geofence
 */
exports.createGeofence = async (req, res, next) => {
  try {
    const { orderId, name, centerLatitude, centerLongitude, radius, action } = req.body;
    
    if (!orderId || !name || centerLatitude === undefined || centerLongitude === undefined || !radius) {
      return res.status(400).json({
        success: false,
        error: { message: 'Missing required fields: orderId, name, centerLatitude, centerLongitude, radius' }
      });
    }
    
    const geofenceId = `geofence-${orderId}-${Date.now()}`;
    
    const geofence = {
      geofenceId,
      orderId,
      name,
      centerLatitude,
      centerLongitude,
      radius, // in meters
      action: action || 'alert', // alert, notify, block
      isActive: true,
      createdAt: new Date().toISOString()
    };
    
    geofences.set(geofenceId, geofence);
    
    logger.info(`Geofence created: ${geofenceId} for order ${orderId}`);
    
    res.status(201).json({
      success: true,
      data: geofence
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Get geofences for an order
 */
exports.getGeofences = async (req, res, next) => {
  try {
    const { orderId } = req.params;
    
    const orderGeofences = Array.from(geofences.values()).filter(g => g.orderId === orderId);
    
    res.json({
      success: true,
      data: orderGeofences,
      total: orderGeofences.length
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Check for geofence violations
 */
function checkGeofenceViolations(orderId, latitude, longitude) {
  const orderGeofences = Array.from(geofences.values()).filter(
    g => g.orderId === orderId && g.isActive
  );
  
  orderGeofences.forEach(geofence => {
    const distance = calculateDistance(
      latitude,
      longitude,
      geofence.centerLatitude,
      geofence.centerLongitude
    );
    
    if (distance > geofence.radius) {
      // Create alert for geofence violation
      const alertId = `alert-${orderId}-geofence-${Date.now()}`;
      const alert = {
        alertId,
        orderId,
        type: 'geofence_violation',
        message: `Order left geofence: ${geofence.name}`,
        severity: 'high',
        metadata: {
          geofenceId: geofence.geofenceId,
          distance,
          latitude,
          longitude
        },
        status: 'active',
        createdAt: new Date().toISOString(),
        resolvedAt: null
      };
      
      alerts.set(alertId, alert);
      logger.warn(`Geofence violation detected for order ${orderId}`);
    }
  });
}

/**
 * Calculate distance between two points (Haversine formula)
 */
function calculateDistance(lat1, lon1, lat2, lon2) {
  const R = 6371e3; // Earth's radius in meters
  const φ1 = (lat1 * Math.PI) / 180;
  const φ2 = (lat2 * Math.PI) / 180;
  const Δφ = ((lat2 - lat1) * Math.PI) / 180;
  const Δλ = ((lon2 - lon1) * Math.PI) / 180;
  
  const a =
    Math.sin(Δφ / 2) * Math.sin(Δφ / 2) +
    Math.cos(φ1) * Math.cos(φ2) * Math.sin(Δλ / 2) * Math.sin(Δλ / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  
  return R * c;
}
