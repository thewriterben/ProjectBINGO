/**
 * Real-time Tracking Routes
 * Endpoints for geolocation and real-time tracking
 */

const express = require('express');
const router = express.Router();
const trackingController = require('../controllers/trackingController');

// Location tracking
router.post('/location', trackingController.updateLocation);
router.get('/location/:orderId', trackingController.getOrderLocation);
router.get('/location/:orderId/history', trackingController.getLocationHistory);

// Real-time monitoring
router.get('/realtime/:orderId', trackingController.getRealtimeData);
router.post('/alert', trackingController.createAlert);
router.get('/alerts/:orderId', trackingController.getAlerts);

// Geofencing
router.post('/geofence', trackingController.createGeofence);
router.get('/geofence/:orderId', trackingController.getGeofences);

module.exports = router;
