// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/**
 * @title MultiChainMarketplace
 * @dev Enhanced marketplace with multi-chain support (Ethereum, Polygon, BSC)
 */
contract MultiChainMarketplace {
    
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
        uint256 chainId;
    }
    
    struct Manufacturer {
        address manufacturerAddress;
        string name;
        string[] capabilities;
        uint256 rating;
        uint256 completedOrders;
        bool isActive;
        uint256[] supportedChains;
    }
    
    struct Dispute {
        uint256 disputeId;
        uint256 orderId;
        address initiator;
        string reason;
        DisputeStatus status;
        uint256 createdAt;
        uint256 resolvedAt;
        address arbitrator;
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
    
    enum DisputeStatus {
        Open,
        UnderReview,
        Resolved,
        Rejected
    }
    
    mapping(uint256 => ManufacturingOrder) public orders;
    mapping(address => Manufacturer) public manufacturers;
    mapping(address => uint256[]) public clientOrders;
    mapping(address => uint256[]) public manufacturerOrders;
    mapping(uint256 => Dispute) public disputes;
    mapping(uint256 => uint256[]) public orderDisputes;
    
    uint256 public orderCounter;
    uint256 public disputeCounter;
    uint256 public platformFeePercent = 2;
    address public owner;
    uint256 public currentChainId;
    
    // Supported chain IDs
    uint256 public constant ETH_MAINNET = 1;
    uint256 public constant POLYGON_MAINNET = 137;
    uint256 public constant BSC_MAINNET = 56;
    
    event OrderCreated(uint256 indexed orderId, address indexed client, uint256 price, uint256 chainId);
    event OrderAccepted(uint256 indexed orderId, address indexed manufacturer);
    event OrderStatusUpdated(uint256 indexed orderId, OrderStatus status);
    event ManufacturerRegistered(address indexed manufacturer, string name);
    event PaymentReleased(uint256 indexed orderId, address indexed manufacturer, uint256 amount);
    event DisputeCreated(uint256 indexed disputeId, uint256 indexed orderId, address indexed initiator);
    event DisputeResolved(uint256 indexed disputeId, uint256 indexed orderId, DisputeStatus status);
    event ChainSupported(uint256 chainId);
    
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
    
    modifier validChain(uint256 _chainId) {
        require(
            _chainId == ETH_MAINNET || _chainId == POLYGON_MAINNET || _chainId == BSC_MAINNET,
            "Unsupported chain"
        );
        _;
    }
    
    constructor() {
        owner = msg.sender;
        currentChainId = block.chainid;
        emit ChainSupported(currentChainId);
    }
    
    /**
     * @dev Register as a manufacturer with multi-chain support
     */
    function registerManufacturer(
        string memory _name, 
        string[] memory _capabilities,
        uint256[] memory _supportedChains
    ) public {
        require(!manufacturers[msg.sender].isActive, "Already registered");
        
        manufacturers[msg.sender] = Manufacturer({
            manufacturerAddress: msg.sender,
            name: _name,
            capabilities: _capabilities,
            rating: 5,
            completedOrders: 0,
            isActive: true,
            supportedChains: _supportedChains
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
            completedAt: 0,
            chainId: currentChainId
        });
        
        clientOrders[msg.sender].push(orderCounter);
        
        emit OrderCreated(orderCounter, msg.sender, msg.value, currentChainId);
        
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
     * @dev Create a dispute for an order
     */
    function createDispute(uint256 _orderId, string memory _reason) public returns (uint256) {
        require(
            orders[_orderId].client == msg.sender || orders[_orderId].manufacturer == msg.sender,
            "Not authorized"
        );
        require(orders[_orderId].status != OrderStatus.Completed, "Order already completed");
        
        disputeCounter++;
        
        disputes[disputeCounter] = Dispute({
            disputeId: disputeCounter,
            orderId: _orderId,
            initiator: msg.sender,
            reason: _reason,
            status: DisputeStatus.Open,
            createdAt: block.timestamp,
            resolvedAt: 0,
            arbitrator: address(0)
        });
        
        orders[_orderId].status = OrderStatus.Disputed;
        orderDisputes[_orderId].push(disputeCounter);
        
        emit DisputeCreated(disputeCounter, _orderId, msg.sender);
        emit OrderStatusUpdated(_orderId, OrderStatus.Disputed);
        
        return disputeCounter;
    }
    
    /**
     * @dev Resolve a dispute (owner/arbitrator only)
     */
    function resolveDispute(
        uint256 _disputeId, 
        DisputeStatus _resolution,
        bool _refundClient
    ) public onlyOwner {
        require(disputes[_disputeId].status == DisputeStatus.Open, "Dispute not open");
        
        disputes[_disputeId].status = _resolution;
        disputes[_disputeId].resolvedAt = block.timestamp;
        disputes[_disputeId].arbitrator = msg.sender;
        
        uint256 orderId = disputes[_disputeId].orderId;
        
        if (_refundClient) {
            payable(orders[orderId].client).transfer(orders[orderId].price);
            orders[orderId].status = OrderStatus.Cancelled;
        } else {
            orders[orderId].status = OrderStatus.Accepted;
        }
        
        emit DisputeResolved(_disputeId, orderId, _resolution);
        emit OrderStatusUpdated(orderId, orders[orderId].status);
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
    
    /**
     * @dev Get disputes for an order
     */
    function getOrderDisputes(uint256 _orderId) public view returns (uint256[] memory) {
        return orderDisputes[_orderId];
    }
    
    /**
     * @dev Get dispute details
     */
    function getDispute(uint256 _disputeId) public view returns (Dispute memory) {
        return disputes[_disputeId];
    }
    
    /**
     * @dev Get current chain ID
     */
    function getChainId() public view returns (uint256) {
        return currentChainId;
    }
}
