// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/**
 * @title ManufacturingMarketplace
 * @dev Decentralized marketplace for manufacturing services
 */
contract ManufacturingMarketplace {
    
    struct ManufacturingOrder {
        uint256 orderId;
        address client;
        address manufacturer;
        string productSpecifications;
        uint256 price;
        uint256 quantity;
        OrderStatus status;
        uint256 createdAt;
        uint256 completedAt;
    }
    
    struct Manufacturer {
        address manufacturerAddress;
        string name;
        string[] capabilities;
        uint256 rating;
        uint256 completedOrders;
        bool isActive;
    }
    
    enum OrderStatus {
        Pending,
        Accepted,
        InProduction,
        QualityCheck,
        Completed,
        Cancelled,
        Disputed
    }
    
    mapping(uint256 => ManufacturingOrder) public orders;
    mapping(address => Manufacturer) public manufacturers;
    mapping(address => uint256[]) public clientOrders;
    mapping(address => uint256[]) public manufacturerOrders;
    
    uint256 public orderCounter;
    uint256 public platformFeePercent = 2; // 2% platform fee
    address public owner;
    
    event OrderCreated(uint256 indexed orderId, address indexed client, uint256 price);
    event OrderAccepted(uint256 indexed orderId, address indexed manufacturer);
    event OrderStatusUpdated(uint256 indexed orderId, OrderStatus status);
    event ManufacturerRegistered(address indexed manufacturer, string name);
    event PaymentReleased(uint256 indexed orderId, address indexed manufacturer, uint256 amount);
    
    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner can call this function");
        _;
    }
    
    modifier onlyClient(uint256 _orderId) {
        require(orders[_orderId].client == msg.sender, "Only client can call this function");
        _;
    }
    
    modifier onlyManufacturer(uint256 _orderId) {
        require(orders[_orderId].manufacturer == msg.sender, "Only manufacturer can call this function");
        _;
    }
    
    constructor() {
        owner = msg.sender;
    }
    
    /**
     * @dev Register as a manufacturer
     */
    function registerManufacturer(string memory _name, string[] memory _capabilities) public {
        require(!manufacturers[msg.sender].isActive, "Already registered");
        
        manufacturers[msg.sender] = Manufacturer({
            manufacturerAddress: msg.sender,
            name: _name,
            capabilities: _capabilities,
            rating: 5,
            completedOrders: 0,
            isActive: true
        });
        
        emit ManufacturerRegistered(msg.sender, _name);
    }
    
    /**
     * @dev Create a new manufacturing order
     */
    function createOrder(
        string memory _productSpecifications,
        uint256 _quantity
    ) public payable returns (uint256) {
        require(msg.value > 0, "Must send payment");
        require(_quantity > 0, "Quantity must be greater than 0");
        
        orderCounter++;
        
        orders[orderCounter] = ManufacturingOrder({
            orderId: orderCounter,
            client: msg.sender,
            manufacturer: address(0),
            productSpecifications: _productSpecifications,
            price: msg.value,
            quantity: _quantity,
            status: OrderStatus.Pending,
            createdAt: block.timestamp,
            completedAt: 0
        });
        
        clientOrders[msg.sender].push(orderCounter);
        
        emit OrderCreated(orderCounter, msg.sender, msg.value);
        
        return orderCounter;
    }
    
    /**
     * @dev Manufacturer accepts an order
     */
    function acceptOrder(uint256 _orderId) public {
        require(manufacturers[msg.sender].isActive, "Not a registered manufacturer");
        require(orders[_orderId].status == OrderStatus.Pending, "Order not pending");
        require(orders[_orderId].manufacturer == address(0), "Order already accepted");
        
        orders[_orderId].manufacturer = msg.sender;
        orders[_orderId].status = OrderStatus.Accepted;
        manufacturerOrders[msg.sender].push(_orderId);
        
        emit OrderAccepted(_orderId, msg.sender);
    }
    
    /**
     * @dev Update order status
     */
    function updateOrderStatus(uint256 _orderId, OrderStatus _status) public onlyManufacturer(_orderId) {
        require(orders[_orderId].status != OrderStatus.Completed, "Order already completed");
        require(orders[_orderId].status != OrderStatus.Cancelled, "Order cancelled");
        
        orders[_orderId].status = _status;
        
        if (_status == OrderStatus.Completed) {
            orders[_orderId].completedAt = block.timestamp;
        }
        
        emit OrderStatusUpdated(_orderId, _status);
    }
    
    /**
     * @dev Client confirms order completion and releases payment
     */
    function confirmCompletion(uint256 _orderId) public onlyClient(_orderId) {
        require(orders[_orderId].status == OrderStatus.Completed, "Order not completed");
        
        uint256 totalAmount = orders[_orderId].price;
        uint256 platformFee = (totalAmount * platformFeePercent) / 100;
        uint256 manufacturerPayment = totalAmount - platformFee;
        
        payable(orders[_orderId].manufacturer).transfer(manufacturerPayment);
        payable(owner).transfer(platformFee);
        
        manufacturers[orders[_orderId].manufacturer].completedOrders++;
        
        emit PaymentReleased(_orderId, orders[_orderId].manufacturer, manufacturerPayment);
    }
    
    /**
     * @dev Cancel order
     */
    function cancelOrder(uint256 _orderId) public onlyClient(_orderId) {
        require(
            orders[_orderId].status == OrderStatus.Pending || 
            orders[_orderId].status == OrderStatus.Accepted,
            "Cannot cancel order in current status"
        );
        
        orders[_orderId].status = OrderStatus.Cancelled;
        payable(orders[_orderId].client).transfer(orders[_orderId].price);
        
        emit OrderStatusUpdated(_orderId, OrderStatus.Cancelled);
    }
    
    /**
     * @dev Get order details
     */
    function getOrder(uint256 _orderId) public view returns (ManufacturingOrder memory) {
        return orders[_orderId];
    }
    
    /**
     * @dev Get manufacturer details
     */
    function getManufacturer(address _manufacturer) public view returns (Manufacturer memory) {
        return manufacturers[_manufacturer];
    }
    
    /**
     * @dev Get client's orders
     */
    function getClientOrders(address _client) public view returns (uint256[] memory) {
        return clientOrders[_client];
    }
    
    /**
     * @dev Get manufacturer's orders
     */
    function getManufacturerOrders(address _manufacturer) public view returns (uint256[] memory) {
        return manufacturerOrders[_manufacturer];
    }
}
