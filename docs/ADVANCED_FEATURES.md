# Advanced Features Documentation

## Overview

This document describes the advanced features implemented in ProjectBINGO, including multi-chain support, AI capabilities, IoT integration, dispute resolution, and supply chain management.

## 1. Multi-Chain Support

### Description
Support for multiple blockchain networks including Ethereum, Polygon, and Binance Smart Chain (BSC).

### Smart Contract
- **File**: `contracts/MultiChainMarketplace.sol`
- **Supported Chains**:
  - Ethereum Mainnet (Chain ID: 1)
  - Polygon Mainnet (Chain ID: 137)
  - Binance Smart Chain (Chain ID: 56)

### Features
- Cross-chain order creation and management
- Multi-chain manufacturer registration
- Chain-specific configuration
- Unified marketplace interface across chains

### Configuration
Chain configurations are managed in `shared/config/chains.js`:

```javascript
const { chains, getChainConfig, isChainSupported } = require('./shared/config/chains');

// Get configuration for a specific chain
const polygonConfig = getChainConfig(137);

// Check if chain is supported
if (isChainSupported(chainId)) {
  // Proceed with transaction
}
```

### Usage Example
```javascript
// Register manufacturer with multi-chain support
await contract.registerManufacturer(
  "Acme Manufacturing",
  ["CNC", "3D Printing"],
  [1, 137, 56] // Support ETH, Polygon, BSC
);
```

## 2. Advanced AI Features

### Description
Deep learning models for natural language processing, fraud detection, recommendations, and predictive analytics.

### AI Service Endpoints

#### NLP - Parse Requirements
**POST** `/api/v1/ai/parse-requirements`

Parse natural language manufacturing requirements.

```json
{
  "text": "I need 100 aluminum parts with CNC machining, high precision required"
}
```

Response:
```json
{
  "success": true,
  "data": {
    "materials": ["aluminum"],
    "processes": ["cnc"],
    "quantities": [100],
    "isUrgent": false,
    "complexity": "high",
    "confidence": 0.85
  }
}
```

#### Fraud Detection
**POST** `/api/v1/ai/detect-fraud`

Analyze orders for fraud indicators.

```json
{
  "price": 150000,
  "quantity": 500,
  "clientHistory": { "orderCount": 2 },
  "rushOrder": true
}
```

Response:
```json
{
  "success": true,
  "data": {
    "riskScore": 0.75,
    "riskLevel": "high",
    "isSuspicious": true,
    "indicators": ["high_value_transaction", "new_client", "rush_high_value"],
    "recommendations": [
      "Require additional verification",
      "Request payment guarantee",
      "Verify client identity"
    ]
  }
}
```

#### Manufacturer Recommendations
**POST** `/api/v1/ai/recommend-manufacturers`

Get personalized manufacturer recommendations.

```json
{
  "requirements": {
    "capabilities": ["CNC", "3D Printing"]
  },
  "userHistory": [],
  "manufacturers": [
    {
      "id": "mfg1",
      "name": "Acme Corp",
      "capabilities": ["CNC", "3D Printing"],
      "rating": 4.8
    }
  ]
}
```

#### Predictive Analytics
**POST** `/api/v1/ai/predict-demand`

Forecast manufacturing demand.

**POST** `/api/v1/ai/predict-completion`

Predict order completion time.

## 3. IoT Integration

### Description
Real-time device tracking, sensor data collection, and geolocation monitoring.

### IoT Service Endpoints

#### Device Management
**POST** `/api/v1/devices/register` - Register IoT device
**GET** `/api/v1/devices/:deviceId` - Get device details
**GET** `/api/v1/devices` - List all devices
**POST** `/api/v1/devices/:deviceId/data` - Collect sensor data
**GET** `/api/v1/devices/:deviceId/status` - Get device status

#### Real-time Tracking
**POST** `/api/v1/tracking/location` - Update location
**GET** `/api/v1/tracking/location/:orderId` - Get current location
**GET** `/api/v1/tracking/location/:orderId/history` - Get location history
**POST** `/api/v1/tracking/alert` - Create alert
**POST** `/api/v1/tracking/geofence` - Create geofence

### Usage Example

Register IoT device:
```javascript
POST /api/v1/devices/register
{
  "deviceId": "sensor-001",
  "name": "Temperature Sensor",
  "type": "temperature",
  "orderId": "order-123",
  "metadata": {
    "location": "warehouse-A"
  }
}
```

Track location:
```javascript
POST /api/v1/tracking/location
{
  "orderId": "order-123",
  "latitude": 37.7749,
  "longitude": -122.4194,
  "accuracy": 10,
  "metadata": {
    "carrier": "DHL"
  }
}
```

Create geofence:
```javascript
POST /api/v1/tracking/geofence
{
  "orderId": "order-123",
  "name": "Delivery Zone",
  "centerLatitude": 37.7749,
  "centerLongitude": -122.4194,
  "radius": 5000,
  "action": "alert"
}
```

## 4. Dispute Resolution System

### Description
Comprehensive dispute management with arbitration, mediation, and evidence collection.

### Dispute Service Endpoints

#### Dispute Management
**POST** `/api/v1/disputes` - Create dispute
**GET** `/api/v1/disputes/:disputeId` - Get dispute details
**GET** `/api/v1/disputes` - List disputes
**PUT** `/api/v1/disputes/:disputeId/status` - Update status
**POST** `/api/v1/disputes/:disputeId/resolve` - Resolve dispute

#### Evidence Management
**POST** `/api/v1/evidence` - Submit evidence
**GET** `/api/v1/evidence/dispute/:disputeId` - Get dispute evidence
**POST** `/api/v1/evidence/:evidenceId/verify` - Verify evidence

### Dispute Workflow

1. **Create Dispute**
```javascript
POST /api/v1/disputes
{
  "orderId": "order-123",
  "initiator": "client-address",
  "respondent": "manufacturer-address",
  "reason": "Product does not meet specifications",
  "category": "quality",
  "priority": "high"
}
```

2. **Submit Evidence**
```javascript
POST /api/v1/evidence
{
  "disputeId": "dispute-123",
  "submittedBy": "client-address",
  "type": "image",
  "description": "Photos showing defects",
  "fileUrl": "https://storage.example.com/evidence.jpg"
}
```

3. **Assign Arbitrator**
```javascript
POST /api/v1/disputes/:disputeId/assign-arbitrator
{
  "arbitratorId": "arb-001",
  "arbitratorName": "John Doe"
}
```

4. **Resolve Dispute**
```javascript
POST /api/v1/disputes/:disputeId/resolve
{
  "resolution": "partial_refund",
  "decision": "Client receives 50% refund",
  "compensationAmount": 5000,
  "notes": "Product partially met specifications",
  "resolvedBy": "arbitrator-001"
}
```

## 5. Supply Chain Integration

### Description
End-to-end supply chain tracking, vendor management, and inventory control.

### Supply Chain Service Endpoints

#### Supply Chain Tracking
**POST** `/api/v1/supply-chain/track` - Create tracking entry
**GET** `/api/v1/supply-chain/track/:orderId` - Get tracking info
**GET** `/api/v1/supply-chain/track/:orderId/history` - Get tracking history
**POST** `/api/v1/supply-chain/quality-check` - Create quality check
**POST** `/api/v1/supply-chain/compliance` - Record compliance

#### Vendor Management
**POST** `/api/v1/vendors` - Register vendor
**GET** `/api/v1/vendors` - List vendors
**GET** `/api/v1/vendors/:vendorId/performance` - Get performance metrics
**POST** `/api/v1/vendors/:vendorId/rating` - Rate vendor

#### Inventory Management
**POST** `/api/v1/inventory/items` - Add inventory item
**GET** `/api/v1/inventory/items` - List inventory
**POST** `/api/v1/inventory/items/:itemId/stock` - Update stock
**GET** `/api/v1/inventory/alerts` - Get inventory alerts

### Usage Examples

Track order progress:
```javascript
POST /api/v1/supply-chain/track
{
  "orderId": "order-123",
  "stage": "production",
  "location": "Factory Floor 2",
  "status": "in_progress",
  "notes": "50% complete"
}
```

Register vendor:
```javascript
POST /api/v1/vendors
{
  "name": "Steel Supplier Inc",
  "type": "material_supplier",
  "contact": {
    "email": "contact@steelsupplier.com",
    "phone": "+1-555-0100"
  },
  "capabilities": ["steel", "aluminum", "bulk_supply"],
  "location": "Chicago, IL"
}
```

Add inventory item:
```javascript
POST /api/v1/inventory/items
{
  "sku": "ALU-6061-001",
  "name": "Aluminum 6061 Sheet",
  "category": "raw_materials",
  "quantity": 500,
  "unit": "sheets",
  "reorderLevel": 50,
  "location": "Warehouse A"
}
```

## Integration Guide

### Starting Services

All services can be started individually or together:

```bash
# Start individual services
npm run start:iot
npm run start:dispute
npm run start:supply-chain
npm run start:ai

# Or use Docker
docker-compose up iot-service dispute-service supply-chain-service ai-service
```

### API Gateway Integration

All services are accessible through the API gateway at their respective endpoints.

### Environment Variables

```env
# IoT Service
IOT_SERVICE_PORT=3007

# Dispute Service
DISPUTE_SERVICE_PORT=3008

# Supply Chain Service
SUPPLY_CHAIN_SERVICE_PORT=3009

# AI Service
AI_SERVICE_PORT=3005

# Multi-chain Support
ETHEREUM_RPC_URL=your_ethereum_rpc_url
POLYGON_RPC_URL=your_polygon_rpc_url
BSC_RPC_URL=your_bsc_rpc_url
```

## Security Considerations

- All services implement proper error handling and logging
- Evidence files should be stored securely with encryption
- IoT device authentication should use secure tokens
- Smart contract interactions require proper access control
- Fraud detection data should be kept confidential

## Testing

Each service includes comprehensive endpoint testing. Run tests with:

```bash
npm test
```

## Support

For issues or questions about advanced features:
- Create an issue on GitHub
- Refer to individual service documentation
- Contact the development team

---

**Version**: 2.0.0
**Last Updated**: October 14, 2025
