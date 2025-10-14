/**
 * Backend API Server for AI-Powered Decentralized Manufacturing Marketplace
 */

const express = require('express');
const cors = require('cors');
const { Web3 } = require('web3');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Web3 initialization
const web3 = new Web3(process.env.BLOCKCHAIN_RPC_URL || 'http://localhost:8545');

// Marketplace contract ABI (simplified)
const MARKETPLACE_ABI = [
    {
        "inputs": [],
        "name": "orderCounter",
        "outputs": [{"type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"type": "uint256"}],
        "name": "getOrder",
        "outputs": [{"type": "tuple"}],
        "stateMutability": "view",
        "type": "function"
    }
];

// Routes

/**
 * Health check endpoint
 */
app.get('/api/health', (req, res) => {
    res.json({
        status: 'healthy',
        timestamp: new Date().toISOString(),
        service: 'Manufacturing Marketplace API',
        version: '1.0.0'
    });
});

/**
 * Get all orders
 */
app.get('/api/orders', async (req, res) => {
    try {
        // Mock response for demonstration
        const orders = [
            {
                orderId: 1,
                client: '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb',
                manufacturer: '0x123d35Cc6634C0532925a3b844Bc9e7595f0bEb',
                productSpecifications: 'Custom metal brackets - 10x5x2cm',
                price: '500',
                quantity: 100,
                status: 'InProduction',
                createdAt: Date.now() - 86400000,
                estimatedCompletion: Date.now() + 172800000
            },
            {
                orderId: 2,
                client: '0x456d35Cc6634C0532925a3b844Bc9e7595f0bEb',
                manufacturer: null,
                productSpecifications: 'Plastic injection molded parts',
                price: '1000',
                quantity: 500,
                status: 'Pending',
                createdAt: Date.now() - 3600000,
                estimatedCompletion: null
            }
        ];
        
        res.json({
            success: true,
            orders: orders,
            count: orders.length
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * Get order by ID
 */
app.get('/api/orders/:orderId', async (req, res) => {
    try {
        const { orderId } = req.params;
        
        // Mock response
        const order = {
            orderId: parseInt(orderId),
            client: '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb',
            manufacturer: '0x123d35Cc6634C0532925a3b844Bc9e7595f0bEb',
            productSpecifications: 'Custom metal brackets - 10x5x2cm',
            price: '500',
            quantity: 100,
            status: 'InProduction',
            createdAt: Date.now() - 86400000,
            estimatedCompletion: Date.now() + 172800000,
            aiAnalysis: {
                complexity: 0.65,
                estimatedCost: 485.50,
                estimatedDays: 5
            }
        };
        
        res.json({
            success: true,
            order: order
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * Create new order
 */
app.post('/api/orders', async (req, res) => {
    try {
        const { specifications, quantity, material, dimensions } = req.body;
        
        if (!specifications || !quantity) {
            return res.status(400).json({
                success: false,
                error: 'Missing required fields'
            });
        }
        
        // Mock order creation
        const newOrder = {
            orderId: Math.floor(Math.random() * 10000),
            client: req.body.clientAddress || '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb',
            manufacturer: null,
            productSpecifications: specifications,
            quantity: quantity,
            material: material,
            dimensions: dimensions,
            status: 'Pending',
            createdAt: Date.now(),
            txHash: '0x' + Math.random().toString(16).substr(2, 64)
        };
        
        res.json({
            success: true,
            order: newOrder,
            message: 'Order created successfully'
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * Get registered manufacturers
 */
app.get('/api/manufacturers', async (req, res) => {
    try {
        const manufacturers = [
            {
                id: '1',
                address: '0x123d35Cc6634C0532925a3b844Bc9e7595f0bEb',
                name: 'Precision Manufacturing Co.',
                capabilities: ['CNC Machining', 'Metal Fabrication', 'Quality Control'],
                materials: ['steel', 'aluminum', 'brass'],
                capacity: 10000,
                rating: 4.8,
                location: 'Detroit, MI',
                completedOrders: 145,
                isActive: true
            },
            {
                id: '2',
                address: '0x789d35Cc6634C0532925a3b844Bc9e7595f0bEb',
                name: 'Advanced Plastics Inc.',
                capabilities: ['Injection Molding', 'Thermoforming', '3D Printing'],
                materials: ['plastic', 'abs', 'nylon'],
                capacity: 50000,
                rating: 4.6,
                location: 'San Jose, CA',
                completedOrders: 203,
                isActive: true
            },
            {
                id: '3',
                address: '0xABCd35Cc6634C0532925a3b844Bc9e7595f0bEb',
                name: 'Composite Solutions Ltd.',
                capabilities: ['Composite Layup', 'Autoclave Processing', 'NDT'],
                materials: ['composite', 'carbon fiber', 'fiberglass'],
                capacity: 5000,
                rating: 4.9,
                location: 'Seattle, WA',
                completedOrders: 87,
                isActive: true
            }
        ];
        
        res.json({
            success: true,
            manufacturers: manufacturers,
            count: manufacturers.length
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * Register new manufacturer
 */
app.post('/api/manufacturers/register', async (req, res) => {
    try {
        const { name, capabilities, materials, capacity, location } = req.body;
        
        if (!name || !capabilities || !materials) {
            return res.status(400).json({
                success: false,
                error: 'Missing required fields'
            });
        }
        
        const manufacturer = {
            id: Math.floor(Math.random() * 10000).toString(),
            address: '0x' + Math.random().toString(16).substr(2, 40),
            name: name,
            capabilities: capabilities,
            materials: materials,
            capacity: capacity || 1000,
            rating: 5.0,
            location: location || 'Unknown',
            completedOrders: 0,
            isActive: true,
            txHash: '0x' + Math.random().toString(16).substr(2, 64)
        };
        
        res.json({
            success: true,
            manufacturer: manufacturer,
            message: 'Manufacturer registered successfully'
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * AI-powered cost estimation
 */
app.post('/api/ai/estimate-cost', async (req, res) => {
    try {
        const { specifications, quantity, material, dimensions } = req.body;
        
        // Mock AI cost estimation
        const baseRate = material === 'steel' ? 5.0 : material === 'aluminum' ? 8.0 : 3.0;
        const volume = (dimensions?.length || 10) * (dimensions?.width || 5) * (dimensions?.height || 2);
        const materialCost = baseRate * volume * quantity;
        const laborCost = 50 * 2.5 * quantity;
        const overhead = (materialCost + laborCost) * 0.15;
        const totalCost = materialCost + laborCost + overhead;
        
        res.json({
            success: true,
            estimate: {
                totalCost: Math.round(totalCost * 100) / 100,
                materialCost: Math.round(materialCost * 100) / 100,
                laborCost: Math.round(laborCost * 100) / 100,
                overhead: Math.round(overhead * 100) / 100,
                costPerUnit: Math.round((totalCost / quantity) * 100) / 100,
                confidence: 0.85
            }
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * AI-powered manufacturer matching
 */
app.post('/api/ai/match-manufacturers', async (req, res) => {
    try {
        const { specifications, quantity, material, deadline } = req.body;
        
        // Mock AI matching
        const matches = [
            {
                manufacturerId: '1',
                manufacturerName: 'Precision Manufacturing Co.',
                matchScore: 0.92,
                estimatedCost: 485.50,
                estimatedDays: 5,
                rating: 4.8,
                recommendation: 'Excellent match - Highly recommended'
            },
            {
                manufacturerId: '3',
                manufacturerName: 'Composite Solutions Ltd.',
                matchScore: 0.78,
                estimatedCost: 520.00,
                estimatedDays: 7,
                rating: 4.9,
                recommendation: 'Good match - Recommended'
            }
        ];
        
        res.json({
            success: true,
            matches: matches,
            algorithm: 'AI-powered matching v1.0'
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

/**
 * Get marketplace statistics
 */
app.get('/api/stats', async (req, res) => {
    try {
        const stats = {
            totalOrders: 247,
            activeOrders: 45,
            completedOrders: 189,
            registeredManufacturers: 32,
            totalValueLocked: '1,245,000',
            avgOrderValue: '5,040',
            avgCompletionTime: 6.5,
            platformFeeCollected: '24,900'
        };
        
        res.json({
            success: true,
            stats: stats,
            timestamp: new Date().toISOString()
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// Error handling middleware
app.use((err, req, res, next) => {
    console.error(err.stack);
    res.status(500).json({
        success: false,
        error: 'Internal server error'
    });
});

// Start server
app.listen(PORT, () => {
    console.log(`\n╔════════════════════════════════════════════════╗`);
    console.log(`║  Manufacturing Marketplace API Server         ║`);
    console.log(`╚════════════════════════════════════════════════╝`);
    console.log(`\nServer running on port ${PORT}`);
    console.log(`Environment: ${process.env.NODE_ENV || 'development'}`);
    console.log(`\nAPI Endpoints:`);
    console.log(`  GET  /api/health`);
    console.log(`  GET  /api/orders`);
    console.log(`  POST /api/orders`);
    console.log(`  GET  /api/manufacturers`);
    console.log(`  POST /api/manufacturers/register`);
    console.log(`  POST /api/ai/estimate-cost`);
    console.log(`  POST /api/ai/match-manufacturers`);
    console.log(`  GET  /api/stats`);
    console.log(`\n${new Date().toISOString()} - Server ready\n`);
});

module.exports = app;
