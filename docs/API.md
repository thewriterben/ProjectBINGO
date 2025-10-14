# API Documentation

## Base URL
```
http://localhost:3000/api
```

## Authentication
Currently, the API uses wallet addresses for authentication. Future versions will implement JWT tokens.

## Endpoints

### Health Check

**GET** `/health`

Check if the API is running.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-10-14T05:54:06.679Z",
  "service": "Manufacturing Marketplace API",
  "version": "1.0.0"
}
```

---

### Orders

#### Get All Orders

**GET** `/orders`

Retrieve all manufacturing orders.

**Response:**
```json
{
  "success": true,
  "orders": [
    {
      "orderId": 1,
      "client": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
      "manufacturer": "0x123d35Cc6634C0532925a3b844Bc9e7595f0bEb",
      "productSpecifications": "Custom metal brackets - 10x5x2cm",
      "price": "500",
      "quantity": 100,
      "status": "InProduction",
      "createdAt": 1728876806679,
      "estimatedCompletion": 1729049606679
    }
  ],
  "count": 1
}
```

#### Get Order by ID

**GET** `/orders/:orderId`

Retrieve a specific order by ID.

**Parameters:**
- `orderId` (path): The order ID

**Response:**
```json
{
  "success": true,
  "order": {
    "orderId": 1,
    "client": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
    "manufacturer": "0x123d35Cc6634C0532925a3b844Bc9e7595f0bEb",
    "productSpecifications": "Custom metal brackets - 10x5x2cm",
    "price": "500",
    "quantity": 100,
    "status": "InProduction",
    "aiAnalysis": {
      "complexity": 0.65,
      "estimatedCost": 485.50,
      "estimatedDays": 5
    }
  }
}
```

#### Create Order

**POST** `/orders`

Create a new manufacturing order.

**Request Body:**
```json
{
  "specifications": "Custom metal brackets with precision holes",
  "quantity": 100,
  "material": "steel",
  "dimensions": {
    "length": 10,
    "width": 5,
    "height": 2
  },
  "clientAddress": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"
}
```

**Response:**
```json
{
  "success": true,
  "order": {
    "orderId": 123,
    "client": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
    "manufacturer": null,
    "productSpecifications": "Custom metal brackets with precision holes",
    "quantity": 100,
    "material": "steel",
    "status": "Pending",
    "createdAt": 1728876806679,
    "txHash": "0x..."
  },
  "message": "Order created successfully"
}
```

---

### Manufacturers

#### Get All Manufacturers

**GET** `/manufacturers`

Retrieve all registered manufacturers.

**Response:**
```json
{
  "success": true,
  "manufacturers": [
    {
      "id": "1",
      "address": "0x123d35Cc6634C0532925a3b844Bc9e7595f0bEb",
      "name": "Precision Manufacturing Co.",
      "capabilities": ["CNC Machining", "Metal Fabrication", "Quality Control"],
      "materials": ["steel", "aluminum", "brass"],
      "capacity": 10000,
      "rating": 4.8,
      "location": "Detroit, MI",
      "completedOrders": 145,
      "isActive": true
    }
  ],
  "count": 1
}
```

#### Register Manufacturer

**POST** `/manufacturers/register`

Register as a new manufacturer.

**Request Body:**
```json
{
  "name": "Advanced Manufacturing Inc.",
  "capabilities": ["3D Printing", "CNC", "Laser Cutting"],
  "materials": ["plastic", "metal", "composite"],
  "capacity": 5000,
  "location": "San Francisco, CA"
}
```

**Response:**
```json
{
  "success": true,
  "manufacturer": {
    "id": "456",
    "address": "0x...",
    "name": "Advanced Manufacturing Inc.",
    "capabilities": ["3D Printing", "CNC", "Laser Cutting"],
    "materials": ["plastic", "metal", "composite"],
    "capacity": 5000,
    "rating": 5.0,
    "location": "San Francisco, CA",
    "completedOrders": 0,
    "isActive": true,
    "txHash": "0x..."
  },
  "message": "Manufacturer registered successfully"
}
```

---

### AI Services

#### AI Cost Estimation

**POST** `/ai/estimate-cost`

Get AI-powered cost estimation for manufacturing.

**Request Body:**
```json
{
  "specifications": "Custom metal brackets with precision holes",
  "quantity": 100,
  "material": "steel",
  "dimensions": {
    "length": 10,
    "width": 5,
    "height": 2
  }
}
```

**Response:**
```json
{
  "success": true,
  "estimate": {
    "totalCost": 485.50,
    "materialCost": 250.00,
    "laborCost": 200.00,
    "overhead": 35.50,
    "costPerUnit": 4.86,
    "confidence": 0.85
  }
}
```

#### AI Manufacturer Matching

**POST** `/ai/match-manufacturers`

Get AI-powered manufacturer recommendations.

**Request Body:**
```json
{
  "specifications": "Custom metal brackets",
  "quantity": 100,
  "material": "steel",
  "deadline": "2025-12-01"
}
```

**Response:**
```json
{
  "success": true,
  "matches": [
    {
      "manufacturerId": "1",
      "manufacturerName": "Precision Manufacturing Co.",
      "matchScore": 0.92,
      "estimatedCost": 485.50,
      "estimatedDays": 5,
      "rating": 4.8,
      "recommendation": "Excellent match - Highly recommended"
    }
  ],
  "algorithm": "AI-powered matching v1.0"
}
```

---

### Statistics

#### Get Marketplace Statistics

**GET** `/stats`

Get overall marketplace statistics.

**Response:**
```json
{
  "success": true,
  "stats": {
    "totalOrders": 247,
    "activeOrders": 45,
    "completedOrders": 189,
    "registeredManufacturers": 32,
    "totalValueLocked": "1,245,000",
    "avgOrderValue": "5,040",
    "avgCompletionTime": 6.5,
    "platformFeeCollected": "24,900"
  },
  "timestamp": "2025-10-14T05:54:06.679Z"
}
```

---

## Error Responses

All endpoints return error responses in the following format:

```json
{
  "success": false,
  "error": "Error message describing what went wrong"
}
```

Common HTTP status codes:
- `200` - Success
- `400` - Bad Request (invalid parameters)
- `404` - Not Found
- `500` - Internal Server Error

## Rate Limiting

Currently, there are no rate limits. Future versions will implement rate limiting to prevent abuse.

## WebSocket Support

WebSocket support for real-time order updates is planned for future releases.
