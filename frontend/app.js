/**
 * Frontend Application Logic for Manufacturing Marketplace
 */

const API_BASE_URL = 'http://localhost:3000/api';
let currentAccount = null;

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    loadOrders();
    loadManufacturers();
    setupEventListeners();
});

// Setup event listeners
function setupEventListeners() {
    const orderForm = document.getElementById('orderForm');
    if (orderForm) {
        orderForm.addEventListener('submit', handleOrderSubmit);
    }
    
    const connectWalletBtn = document.getElementById('connectWallet');
    if (connectWalletBtn) {
        connectWalletBtn.addEventListener('click', connectWallet);
    }
}

// Show/hide sections
function showSection(sectionId) {
    document.querySelectorAll('.section').forEach(section => {
        section.classList.add('hidden');
    });
    
    const targetSection = document.getElementById(sectionId);
    if (targetSection) {
        targetSection.classList.remove('hidden');
        targetSection.scrollIntoView({ behavior: 'smooth' });
    }
}

// Connect wallet
async function connectWallet() {
    if (typeof window.ethereum !== 'undefined') {
        try {
            const accounts = await window.ethereum.request({ 
                method: 'eth_requestAccounts' 
            });
            currentAccount = accounts[0];
            
            document.getElementById('connectWallet').textContent = 
                `${currentAccount.substring(0, 6)}...${currentAccount.substring(38)}`;
            
            showNotification('Wallet connected successfully!', 'success');
        } catch (error) {
            console.error('Error connecting wallet:', error);
            showNotification('Failed to connect wallet', 'error');
        }
    } else {
        showNotification('Please install MetaMask!', 'warning');
    }
}

// Load marketplace stats
async function loadStats() {
    try {
        const response = await fetch(`${API_BASE_URL}/stats`);
        const data = await response.json();
        
        if (data.success) {
            const stats = data.stats;
            document.getElementById('totalOrders').textContent = stats.totalOrders;
            document.getElementById('activeManufacturers').textContent = stats.registeredManufacturers;
            document.getElementById('totalValue').textContent = `$${stats.totalValueLocked}`;
            document.getElementById('avgCompletion').textContent = `${stats.avgCompletionTime} days`;
        }
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

// Load orders
async function loadOrders() {
    try {
        const response = await fetch(`${API_BASE_URL}/orders`);
        const data = await response.json();
        
        if (data.success) {
            displayOrders(data.orders);
        }
    } catch (error) {
        console.error('Error loading orders:', error);
        document.getElementById('ordersList').innerHTML = 
            '<p>Unable to load orders. Please ensure the backend server is running.</p>';
    }
}

// Display orders
function displayOrders(orders) {
    const ordersList = document.getElementById('ordersList');
    
    if (orders.length === 0) {
        ordersList.innerHTML = '<p>No orders found.</p>';
        return;
    }
    
    ordersList.innerHTML = orders.map(order => `
        <div class="order-card">
            <div class="order-header">
                <span class="order-id">Order #${order.orderId}</span>
                <span class="order-status status-${order.status.toLowerCase().replace(' ', '')}">${order.status}</span>
            </div>
            <div class="order-details">
                <p><strong>Specifications:</strong> ${order.productSpecifications}</p>
                <p><strong>Quantity:</strong> ${order.quantity} units</p>
                <p><strong>Price:</strong> ${order.price} ETH</p>
                <p><strong>Client:</strong> ${formatAddress(order.client)}</p>
                ${order.manufacturer ? `<p><strong>Manufacturer:</strong> ${formatAddress(order.manufacturer)}</p>` : ''}
                <p><strong>Created:</strong> ${formatDate(order.createdAt)}</p>
            </div>
        </div>
    `).join('');
}

// Load manufacturers
async function loadManufacturers() {
    try {
        const response = await fetch(`${API_BASE_URL}/manufacturers`);
        const data = await response.json();
        
        if (data.success) {
            displayManufacturers(data.manufacturers);
        }
    } catch (error) {
        console.error('Error loading manufacturers:', error);
        document.getElementById('manufacturersList').innerHTML = 
            '<p>Unable to load manufacturers. Please ensure the backend server is running.</p>';
    }
}

// Display manufacturers
function displayManufacturers(manufacturers) {
    const manufacturersList = document.getElementById('manufacturersList');
    
    if (manufacturers.length === 0) {
        manufacturersList.innerHTML = '<p>No manufacturers found.</p>';
        return;
    }
    
    manufacturersList.innerHTML = manufacturers.map(mfr => `
        <div class="manufacturer-card">
            <div class="manufacturer-header">
                <h3 class="manufacturer-name">${mfr.name}</h3>
                <p class="manufacturer-rating">⭐ ${mfr.rating.toFixed(1)}/5.0</p>
            </div>
            <div class="manufacturer-info">
                <p><strong>Location:</strong> ${mfr.location}</p>
                <p><strong>Completed Orders:</strong> ${mfr.completedOrders}</p>
                <p><strong>Capacity:</strong> ${mfr.capacity.toLocaleString()} units/month</p>
                <p><strong>Address:</strong> ${formatAddress(mfr.address)}</p>
            </div>
            <div class="capabilities">
                ${mfr.capabilities.map(cap => 
                    `<span class="capability-tag">${cap}</span>`
                ).join('')}
            </div>
        </div>
    `).join('');
}

// Get AI cost estimate
async function getAIEstimate() {
    const specifications = document.getElementById('specifications').value;
    const quantity = document.getElementById('quantity').value;
    const material = document.getElementById('material').value;
    const length = document.getElementById('length').value;
    const width = document.getElementById('width').value;
    const height = document.getElementById('height').value;
    
    if (!specifications || !quantity || !material || !length || !width || !height) {
        showNotification('Please fill in all fields first', 'warning');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/ai/estimate-cost`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                specifications,
                quantity: parseInt(quantity),
                material,
                dimensions: {
                    length: parseFloat(length),
                    width: parseFloat(width),
                    height: parseFloat(height)
                }
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            const estimate = data.estimate;
            document.getElementById('estimatedCost').textContent = estimate.totalCost.toFixed(2);
            document.getElementById('estimatedTime').textContent = '5-7';
            document.getElementById('confidence').textContent = (estimate.confidence * 100).toFixed(0);
            document.getElementById('aiEstimate').style.display = 'block';
            
            showNotification('AI estimate generated successfully!', 'success');
        }
    } catch (error) {
        console.error('Error getting AI estimate:', error);
        showNotification('Failed to get AI estimate', 'error');
    }
}

// Handle order form submission
async function handleOrderSubmit(e) {
    e.preventDefault();
    
    const specifications = document.getElementById('specifications').value;
    const quantity = document.getElementById('quantity').value;
    const material = document.getElementById('material').value;
    const length = document.getElementById('length').value;
    const width = document.getElementById('width').value;
    const height = document.getElementById('height').value;
    
    try {
        const response = await fetch(`${API_BASE_URL}/orders`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                specifications,
                quantity: parseInt(quantity),
                material,
                dimensions: {
                    length: parseFloat(length),
                    width: parseFloat(width),
                    height: parseFloat(height)
                },
                clientAddress: currentAccount
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification('Order created successfully!', 'success');
            document.getElementById('orderForm').reset();
            document.getElementById('aiEstimate').style.display = 'none';
            loadOrders();
            showSection('orders');
        }
    } catch (error) {
        console.error('Error creating order:', error);
        showNotification('Failed to create order', 'error');
    }
}

// Match manufacturers
async function matchManufacturers() {
    const specifications = 'Sample manufacturing requirements';
    const quantity = 100;
    const material = 'steel';
    
    try {
        const response = await fetch(`${API_BASE_URL}/ai/match-manufacturers`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                specifications,
                quantity,
                material,
                deadline: '2025-12-01'
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            console.log('Manufacturer matches:', data.matches);
            showNotification('AI matching completed! Check console for results.', 'success');
        }
    } catch (error) {
        console.error('Error matching manufacturers:', error);
        showNotification('Failed to match manufacturers', 'error');
    }
}

// Utility functions
function formatAddress(address) {
    if (!address) return 'N/A';
    return `${address.substring(0, 6)}...${address.substring(38)}`;
}

function formatDate(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleDateString('en-US', { 
        year: 'numeric', 
        month: 'short', 
        day: 'numeric' 
    });
}

function showNotification(message, type = 'info') {
    // Simple notification (can be enhanced with a proper notification library)
    alert(message);
}

// Export functions for global use
window.showSection = showSection;
window.getAIEstimate = getAIEstimate;
window.matchManufacturers = matchManufacturers;
