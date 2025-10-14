/**
 * IoT Device Routes
 * Endpoints for device registration, management, and data collection
 */

const express = require('express');
const router = express.Router();
const deviceController = require('../controllers/deviceController');

// Device registration and management
router.post('/register', deviceController.registerDevice);
router.get('/:deviceId', deviceController.getDevice);
router.get('/', deviceController.listDevices);
router.put('/:deviceId', deviceController.updateDevice);
router.delete('/:deviceId', deviceController.removeDevice);

// Device data collection
router.post('/:deviceId/data', deviceController.collectData);
router.get('/:deviceId/data', deviceController.getDeviceData);

// Device status and monitoring
router.get('/:deviceId/status', deviceController.getDeviceStatus);
router.post('/:deviceId/heartbeat', deviceController.heartbeat);

module.exports = router;
