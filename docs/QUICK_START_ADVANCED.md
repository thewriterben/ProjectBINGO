# Quick Start Guide - Advanced Features

This guide will help you quickly get started with ProjectBINGO's advanced features.

## Prerequisites

- Node.js v16+
- npm or yarn
- MetaMask or Web3 wallet
- Basic understanding of blockchain and REST APIs

## Starting the Services

### Option 1: Start Individual Services

```bash
# Terminal 1 - AI Service (Port 3005)
npm run start:ai

# Terminal 2 - IoT Service (Port 3007)
npm run start:iot

# Terminal 3 - Dispute Service (Port 3008)
npm run start:dispute

# Terminal 4 - Supply Chain Service (Port 3009)
npm run start:supply-chain
```

### Option 2: Using Docker

```bash
docker-compose up -d
```

## Quick Examples

### 1. Multi-Chain Support

#### Deploy to Multiple Chains
```bash
npm run deploy:multichain
```

#### Check Supported Chains
```javascript
const { chains, getChainConfig } = require('./shared/config/chains');

// Get Polygon configuration
const polygon = getChainConfig(137);
console.log(polygon.name); // "Polygon Mainnet"
```

### 2. AI Features

#### Parse Natural Language Requirements
```bash
curl -X POST http://localhost:3005/api/v1/ai/parse-requirements \
  -H "Content-Type: application/json" \
  -d '{
    "text": "I need 100 aluminum CNC machined parts with high precision"
  }'
```

Response:
```json
{
  "success": true,
  "data": {
    "materials": ["aluminum"],
    "processes": ["cnc"],
    "quantities": [100],
    "complexity": "high",
    "confidence": 0.85
  }
}
```

#### Detect Fraud
```bash
curl -X POST http://localhost:3005/api/v1/ai/detect-fraud \
  -H "Content-Type: application/json" \
  -d '{
    "price": 150000,
    "quantity": 500,
    "clientHistory": { "orderCount": 1 },
    "rushOrder": true
  }'
```

#### Get Recommendations
```bash
curl -X POST http://localhost:3005/api/v1/ai/recommend-manufacturers \
  -H "Content-Type: application/json" \
  -d '{
    "requirements": {
      "capabilities": ["CNC", "3D Printing"]
    },
    "manufacturers": [
      {
        "id": "mfg1",
        "name": "Acme Manufacturing",
        "capabilities": ["CNC", "3D Printing", "Welding"],
        "rating": 4.8
      }
    ]
  }'
```

### 3. IoT Device Tracking

#### Register an IoT Device
```bash
curl -X POST http://localhost:3007/api/v1/devices/register \
  -H "Content-Type: application/json" \
  -d '{
    "deviceId": "temp-sensor-001",
    "name": "Temperature Sensor",
    "type": "temperature",
    "orderId": "order-123"
  }'
```

#### Update Location
```bash
curl -X POST http://localhost:3007/api/v1/tracking/location \
  -H "Content-Type: application/json" \
  -d '{
    "orderId": "order-123",
    "latitude": 37.7749,
    "longitude": -122.4194,
    "accuracy": 10
  }'
```

#### Create Geofence Alert
```bash
curl -X POST http://localhost:3007/api/v1/tracking/geofence \
  -H "Content-Type: application/json" \
  -d '{
    "orderId": "order-123",
    "name": "Delivery Zone",
    "centerLatitude": 37.7749,
    "centerLongitude": -122.4194,
    "radius": 5000
  }'
```

#### Collect Sensor Data
```bash
curl -X POST http://localhost:3007/api/v1/devices/temp-sensor-001/data \
  -H "Content-Type: application/json" \
  -d '{
    "sensorType": "temperature",
    "value": 22.5,
    "unit": "celsius"
  }'
```

### 4. Dispute Resolution

#### Create a Dispute
```bash
curl -X POST http://localhost:3008/api/v1/disputes \
  -H "Content-Type: application/json" \
  -d '{
    "orderId": "order-123",
    "initiator": "client-address",
    "respondent": "manufacturer-address",
    "reason": "Product does not meet specifications",
    "category": "quality",
    "priority": "high"
  }'
```

#### Submit Evidence
```bash
curl -X POST http://localhost:3008/api/v1/evidence \
  -H "Content-Type: application/json" \
  -d '{
    "disputeId": "dispute-123",
    "submittedBy": "client-address",
    "type": "image",
    "description": "Photos showing defects",
    "fileUrl": "https://example.com/evidence.jpg"
  }'
```

#### Resolve Dispute
```bash
curl -X POST http://localhost:3008/api/v1/disputes/dispute-123/resolve \
  -H "Content-Type: application/json" \
  -d '{
    "resolution": "partial_refund",
    "decision": "Client receives 50% refund",
    "compensationAmount": 5000,
    "resolvedBy": "arbitrator-001"
  }'
```

### 5. Supply Chain Management

#### Track Order Progress
```bash
curl -X POST http://localhost:3009/api/v1/supply-chain/track \
  -H "Content-Type: application/json" \
  -d '{
    "orderId": "order-123",
    "stage": "production",
    "location": "Factory Floor 2",
    "status": "in_progress",
    "notes": "50% complete"
  }'
```

#### Register a Vendor
```bash
curl -X POST http://localhost:3009/api/v1/vendors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Steel Supplier Inc",
    "type": "material_supplier",
    "contact": {
      "email": "contact@steelsupplier.com",
      "phone": "+1-555-0100"
    },
    "capabilities": ["steel", "aluminum"],
    "location": "Chicago, IL"
  }'
```

#### Add Inventory Item
```bash
curl -X POST http://localhost:3009/api/v1/inventory/items \
  -H "Content-Type: application/json" \
  -d '{
    "sku": "ALU-6061-001",
    "name": "Aluminum 6061 Sheet",
    "category": "raw_materials",
    "quantity": 500,
    "unit": "sheets",
    "reorderLevel": 50
  }'
```

#### Create Quality Check
```bash
curl -X POST http://localhost:3009/api/v1/supply-chain/quality-check \
  -H "Content-Type: application/json" \
  -d '{
    "orderId": "order-123",
    "inspector": "John Doe",
    "checkType": "dimensional",
    "result": "passed",
    "score": 95,
    "notes": "All dimensions within tolerance"
  }'
```

## Health Checks

Verify all services are running:

```bash
# AI Service
curl http://localhost:3005/api/v1/health

# IoT Service
curl http://localhost:3007/api/v1/health

# Dispute Service
curl http://localhost:3008/api/v1/health

# Supply Chain Service
curl http://localhost:3009/api/v1/health
```

All should respond with:
```json
{
  "status": "healthy",
  "service": "service-name",
  "version": "1.0.0",
  "timestamp": "2025-10-14T18:42:37.376Z"
}
```

## Environment Configuration

Add these to your `.env` file:

```bash
# Service Ports
AI_SERVICE_PORT=3005
IOT_SERVICE_PORT=3007
DISPUTE_SERVICE_PORT=3008
SUPPLY_CHAIN_SERVICE_PORT=3009

# Multi-chain Configuration
ETHEREUM_RPC_URL=your_ethereum_rpc_url
POLYGON_RPC_URL=your_polygon_rpc_url
BSC_RPC_URL=your_bsc_rpc_url

# Testnet URLs
SEPOLIA_RPC_URL=your_sepolia_rpc_url
MUMBAI_RPC_URL=your_mumbai_rpc_url
BSC_TESTNET_RPC_URL=your_bsc_testnet_rpc_url
```

## Next Steps

1. Read the [Advanced Features Documentation](./ADVANCED_FEATURES.md) for detailed information
2. Check the [API Documentation](./API.md) for complete endpoint reference
3. Review the [Deployment Guide](./DEPLOYMENT.md) for production setup
4. Explore example integrations in the `examples/` directory

## Troubleshooting

### Service won't start
- Check if the port is already in use
- Verify all dependencies are installed: `npm install`
- Check logs for error messages

### Can't connect to service
- Verify the service is running
- Check firewall settings
- Ensure correct port numbers in configuration

### Multi-chain deployment fails
- Verify RPC URLs are correct
- Check wallet has sufficient gas
- Ensure correct network configuration

## Getting Help

- 📖 Documentation: `docs/` directory
- 🐛 Issues: [GitHub Issues](https://github.com/thewriterben/ProjectBINGO/issues)
- 💬 Discussions: [GitHub Discussions](https://github.com/thewriterben/ProjectBINGO/discussions)

---

**Happy Building! 🚀**
