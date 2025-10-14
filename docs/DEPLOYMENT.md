# Deployment Guide

## Quick Start

### Prerequisites
- Node.js v16 or higher
- npm or yarn
- Python 3.8+
- MetaMask or Web3-compatible wallet
- Ethereum node (local or remote)

### Installation Steps

1. **Clone and Install**
```bash
git clone https://github.com/thewriterben/ProjectBINGO.git
cd ProjectBINGO
npm install
```

2. **Configure Environment**
```bash
cp .env.example .env
```

Edit `.env` with your configuration:
- `PORT`: Backend server port (default: 3000)
- `BLOCKCHAIN_RPC_URL`: Your Ethereum node URL
- `CONTRACT_ADDRESS`: Deployed smart contract address
- `AI_API_KEY`: Your AI service API key (if using external AI)

3. **Start the Backend Server**
```bash
npm start
```

The server will start on http://localhost:3000

4. **Serve the Frontend**
```bash
# Option 1: Using Python
cd frontend
python3 -m http.server 8000

# Option 2: Using Node.js http-server
npx http-server frontend -p 8000

# Option 3: Using any web server of your choice
```

Access the application at http://localhost:8000

## Deployment Options

### Option 1: Local Development

Use the quick start guide above for local development and testing.

### Option 2: Cloud Deployment (Heroku)

1. **Prepare for Heroku**
```bash
# Create Procfile
echo "web: node backend/server.js" > Procfile
```

2. **Deploy to Heroku**
```bash
heroku create your-app-name
heroku config:set PORT=3000
heroku config:set BLOCKCHAIN_RPC_URL=your_rpc_url
git push heroku main
```

### Option 3: Docker Deployment

1. **Create Dockerfile**
```dockerfile
FROM node:16
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
EXPOSE 3000
CMD ["node", "backend/server.js"]
```

2. **Build and Run**
```bash
docker build -t manufacturing-marketplace .
docker run -p 3000:3000 manufacturing-marketplace
```

### Option 4: AWS/Azure/GCP

Deploy the backend as a Node.js application and host the frontend as static files on S3, Azure Blob Storage, or Google Cloud Storage.

## Smart Contract Deployment

### Using Hardhat

1. **Install Hardhat**
```bash
npm install --save-dev hardhat @nomicfoundation/hardhat-toolbox
```

2. **Initialize Hardhat**
```bash
npx hardhat init
```

3. **Configure Network**
Edit `hardhat.config.js`:
```javascript
module.exports = {
  solidity: "0.8.0",
  networks: {
    sepolia: {
      url: process.env.BLOCKCHAIN_RPC_URL,
      accounts: [process.env.PRIVATE_KEY]
    }
  }
};
```

4. **Deploy Contract**
```bash
npx hardhat run scripts/deploy.js --network sepolia
```

5. **Update Configuration**
Copy the deployed contract address to your `.env` file.

### Using Remix IDE

1. Open [Remix IDE](https://remix.ethereum.org/)
2. Create a new file and paste the contract code from `contracts/ManufacturingMarketplace.sol`
3. Compile the contract
4. Connect MetaMask
5. Deploy the contract
6. Copy the contract address to your `.env` file

## Frontend Configuration

If deploying frontend separately, update the API base URL in `frontend/app.js`:

```javascript
const API_BASE_URL = 'https://your-backend-domain.com/api';
```

## Production Considerations

### Security
- Use HTTPS for all connections
- Implement rate limiting
- Add authentication/authorization
- Secure environment variables
- Audit smart contracts before mainnet deployment

### Performance
- Enable caching
- Use CDN for static assets
- Implement connection pooling
- Optimize database queries (if added)

### Monitoring
- Set up logging (Winston, Morgan)
- Monitor API performance
- Track blockchain transactions
- Set up alerts for errors

### Scaling
- Use load balancer for multiple backend instances
- Implement Redis for session management
- Use message queues for async tasks
- Consider microservices architecture

## Testing in Production

1. **Test Backend API**
```bash
curl https://your-domain.com/api/health
```

2. **Test Smart Contract**
Use Web3.js or Ethers.js to interact with deployed contract

3. **Test Frontend**
Open browser and verify all features work

## Troubleshooting

### Common Issues

**Backend won't start:**
- Check if port is already in use
- Verify all dependencies are installed
- Check environment variables

**Frontend can't connect to backend:**
- Verify API_BASE_URL is correct
- Check CORS configuration
- Ensure backend is running

**Smart contract errors:**
- Verify contract address is correct
- Check you're on the right network
- Ensure wallet has sufficient funds

## Maintenance

### Regular Tasks
- Monitor server logs
- Update dependencies regularly
- Backup blockchain data
- Review and update smart contracts
- Monitor gas prices and optimize

### Updating the Application

1. **Backend Updates**
```bash
git pull origin main
npm install
npm start
```

2. **Frontend Updates**
```bash
git pull origin main
# Redeploy static files
```

3. **Smart Contract Updates**
- Deploy new contract version
- Update frontend with new ABI and address
- Migrate data if necessary

## Support

For issues or questions:
- GitHub Issues: https://github.com/thewriterben/ProjectBINGO/issues
- Email: support@manufacturingmarketplace.com
- Documentation: https://github.com/thewriterben/ProjectBINGO/docs
