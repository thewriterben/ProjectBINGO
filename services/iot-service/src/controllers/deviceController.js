/**
 * IoT Device Controller
 * Handles device registration, management, and data collection
 */

const Logger = require('../../../../shared/utils/logger');
const logger = new Logger('iot-device-controller');

// In-memory storage for demo (replace with database in production)
const devices = new Map();
const deviceData = new Map();

/**
 * Register a new IoT device
 */
exports.registerDevice = async (req, res, next) => {
  try {
    const { deviceId, name, type, orderId, metadata } = req.body;
    
    if (!deviceId || !name || !type) {
      return res.status(400).json({
        success: false,
        error: { message: 'Missing required fields: deviceId, name, type' }
      });
    }
    
    if (devices.has(deviceId)) {
      return res.status(409).json({
        success: false,
        error: { message: 'Device already registered' }
      });
    }
    
    const device = {
      deviceId,
      name,
      type,
      orderId,
      metadata,
      status: 'active',
      registeredAt: new Date().toISOString(),
      lastSeen: new Date().toISOString()
    };
    
    devices.set(deviceId, device);
    deviceData.set(deviceId, []);
    
    logger.info(`Device registered: ${deviceId}`);
    
    res.status(201).json({
      success: true,
      data: device
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Get device details
 */
exports.getDevice = async (req, res, next) => {
  try {
    const { deviceId } = req.params;
    
    const device = devices.get(deviceId);
    
    if (!device) {
      return res.status(404).json({
        success: false,
        error: { message: 'Device not found' }
      });
    }
    
    res.json({
      success: true,
      data: device
    });
  } catch (error) {
    next(error);
  }
};

/**
 * List all devices
 */
exports.listDevices = async (req, res, next) => {
  try {
    const { orderId, type, status } = req.query;
    
    let filteredDevices = Array.from(devices.values());
    
    if (orderId) {
      filteredDevices = filteredDevices.filter(d => d.orderId === orderId);
    }
    
    if (type) {
      filteredDevices = filteredDevices.filter(d => d.type === type);
    }
    
    if (status) {
      filteredDevices = filteredDevices.filter(d => d.status === status);
    }
    
    res.json({
      success: true,
      data: filteredDevices,
      total: filteredDevices.length
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Update device information
 */
exports.updateDevice = async (req, res, next) => {
  try {
    const { deviceId } = req.params;
    const updates = req.body;
    
    const device = devices.get(deviceId);
    
    if (!device) {
      return res.status(404).json({
        success: false,
        error: { message: 'Device not found' }
      });
    }
    
    const updatedDevice = {
      ...device,
      ...updates,
      deviceId: device.deviceId, // Prevent deviceId change
      updatedAt: new Date().toISOString()
    };
    
    devices.set(deviceId, updatedDevice);
    
    logger.info(`Device updated: ${deviceId}`);
    
    res.json({
      success: true,
      data: updatedDevice
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Remove a device
 */
exports.removeDevice = async (req, res, next) => {
  try {
    const { deviceId } = req.params;
    
    if (!devices.has(deviceId)) {
      return res.status(404).json({
        success: false,
        error: { message: 'Device not found' }
      });
    }
    
    devices.delete(deviceId);
    deviceData.delete(deviceId);
    
    logger.info(`Device removed: ${deviceId}`);
    
    res.json({
      success: true,
      message: 'Device removed successfully'
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Collect data from device
 */
exports.collectData = async (req, res, next) => {
  try {
    const { deviceId } = req.params;
    const { sensorType, value, unit, metadata } = req.body;
    
    const device = devices.get(deviceId);
    
    if (!device) {
      return res.status(404).json({
        success: false,
        error: { message: 'Device not found' }
      });
    }
    
    const dataPoint = {
      id: `${deviceId}-${Date.now()}`,
      deviceId,
      sensorType,
      value,
      unit,
      metadata,
      timestamp: new Date().toISOString()
    };
    
    const data = deviceData.get(deviceId) || [];
    data.push(dataPoint);
    
    // Keep only last 1000 data points per device
    if (data.length > 1000) {
      data.shift();
    }
    
    deviceData.set(deviceId, data);
    
    // Update device last seen
    device.lastSeen = new Date().toISOString();
    devices.set(deviceId, device);
    
    res.status(201).json({
      success: true,
      data: dataPoint
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Get device data
 */
exports.getDeviceData = async (req, res, next) => {
  try {
    const { deviceId } = req.params;
    const { sensorType, limit = 100, startTime, endTime } = req.query;
    
    if (!devices.has(deviceId)) {
      return res.status(404).json({
        success: false,
        error: { message: 'Device not found' }
      });
    }
    
    let data = deviceData.get(deviceId) || [];
    
    // Filter by sensor type
    if (sensorType) {
      data = data.filter(d => d.sensorType === sensorType);
    }
    
    // Filter by time range
    if (startTime) {
      data = data.filter(d => new Date(d.timestamp) >= new Date(startTime));
    }
    
    if (endTime) {
      data = data.filter(d => new Date(d.timestamp) <= new Date(endTime));
    }
    
    // Limit results
    const limitNum = parseInt(limit);
    data = data.slice(-limitNum);
    
    res.json({
      success: true,
      data,
      total: data.length
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Get device status
 */
exports.getDeviceStatus = async (req, res, next) => {
  try {
    const { deviceId } = req.params;
    
    const device = devices.get(deviceId);
    
    if (!device) {
      return res.status(404).json({
        success: false,
        error: { message: 'Device not found' }
      });
    }
    
    const lastSeenTime = new Date(device.lastSeen);
    const now = new Date();
    const minutesSinceLastSeen = (now - lastSeenTime) / 1000 / 60;
    
    const isOnline = minutesSinceLastSeen < 5; // Consider online if seen in last 5 minutes
    
    const data = deviceData.get(deviceId) || [];
    const latestData = data.length > 0 ? data[data.length - 1] : null;
    
    res.json({
      success: true,
      data: {
        deviceId,
        status: device.status,
        isOnline,
        lastSeen: device.lastSeen,
        minutesSinceLastSeen: Math.round(minutesSinceLastSeen),
        latestData,
        totalDataPoints: data.length
      }
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Device heartbeat
 */
exports.heartbeat = async (req, res, next) => {
  try {
    const { deviceId } = req.params;
    
    const device = devices.get(deviceId);
    
    if (!device) {
      return res.status(404).json({
        success: false,
        error: { message: 'Device not found' }
      });
    }
    
    device.lastSeen = new Date().toISOString();
    device.status = 'active';
    devices.set(deviceId, device);
    
    res.json({
      success: true,
      message: 'Heartbeat received',
      data: {
        deviceId,
        lastSeen: device.lastSeen
      }
    });
  } catch (error) {
    next(error);
  }
};
