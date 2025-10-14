/**
 * Multi-chain Configuration
 * Configuration for Ethereum, Polygon, and BSC support
 */

const chains = {
  ethereum: {
    chainId: '0x1',
    chainIdDecimal: 1,
    name: 'Ethereum Mainnet',
    rpcUrl: process.env.ETHEREUM_RPC_URL || 'https://eth-mainnet.g.alchemy.com/v2/',
    explorerUrl: 'https://etherscan.io',
    nativeCurrency: {
      name: 'Ether',
      symbol: 'ETH',
      decimals: 18
    }
  },
  
  polygon: {
    chainId: '0x89',
    chainIdDecimal: 137,
    name: 'Polygon Mainnet',
    rpcUrl: process.env.POLYGON_RPC_URL || 'https://polygon-rpc.com',
    explorerUrl: 'https://polygonscan.com',
    nativeCurrency: {
      name: 'MATIC',
      symbol: 'MATIC',
      decimals: 18
    }
  },
  
  bsc: {
    chainId: '0x38',
    chainIdDecimal: 56,
    name: 'Binance Smart Chain',
    rpcUrl: process.env.BSC_RPC_URL || 'https://bsc-dataseed.binance.org',
    explorerUrl: 'https://bscscan.com',
    nativeCurrency: {
      name: 'BNB',
      symbol: 'BNB',
      decimals: 18
    }
  },
  
  // Testnets
  sepolia: {
    chainId: '0xaa36a7',
    chainIdDecimal: 11155111,
    name: 'Sepolia Testnet',
    rpcUrl: process.env.SEPOLIA_RPC_URL || 'https://sepolia.infura.io/v3/',
    explorerUrl: 'https://sepolia.etherscan.io',
    nativeCurrency: {
      name: 'Sepolia Ether',
      symbol: 'ETH',
      decimals: 18
    }
  },
  
  polygonMumbai: {
    chainId: '0x13881',
    chainIdDecimal: 80001,
    name: 'Polygon Mumbai',
    rpcUrl: process.env.MUMBAI_RPC_URL || 'https://rpc-mumbai.maticvigil.com',
    explorerUrl: 'https://mumbai.polygonscan.com',
    nativeCurrency: {
      name: 'MATIC',
      symbol: 'MATIC',
      decimals: 18
    }
  },
  
  bscTestnet: {
    chainId: '0x61',
    chainIdDecimal: 97,
    name: 'BSC Testnet',
    rpcUrl: process.env.BSC_TESTNET_RPC_URL || 'https://data-seed-prebsc-1-s1.binance.org:8545',
    explorerUrl: 'https://testnet.bscscan.com',
    nativeCurrency: {
      name: 'BNB',
      symbol: 'BNB',
      decimals: 18
    }
  }
};

/**
 * Get chain configuration by chain ID
 */
function getChainConfig(chainId) {
  const chainIdNum = typeof chainId === 'string' ? parseInt(chainId, 16) : chainId;
  
  for (const [key, config] of Object.entries(chains)) {
    if (config.chainIdDecimal === chainIdNum || config.chainId === chainId) {
      return config;
    }
  }
  
  return null;
}

/**
 * Check if chain is supported
 */
function isChainSupported(chainId) {
  return getChainConfig(chainId) !== null;
}

/**
 * Get all supported mainnet chains
 */
function getMainnetChains() {
  return {
    ethereum: chains.ethereum,
    polygon: chains.polygon,
    bsc: chains.bsc
  };
}

/**
 * Get all supported testnet chains
 */
function getTestnetChains() {
  return {
    sepolia: chains.sepolia,
    polygonMumbai: chains.polygonMumbai,
    bscTestnet: chains.bscTestnet
  };
}

module.exports = {
  chains,
  getChainConfig,
  isChainSupported,
  getMainnetChains,
  getTestnetChains
};
