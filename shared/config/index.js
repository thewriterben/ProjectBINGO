/**
 * Shared Configuration Module
 * Centralized configuration management for all microservices
 */

require('dotenv').config();

const config = {
  // Environment
  env: process.env.NODE_ENV || 'development',
  isDevelopment: process.env.NODE_ENV !== 'production',
  isProduction: process.env.NODE_ENV === 'production',

  // Server Configuration
  port: process.env.PORT || 3000,
  apiVersion: process.env.API_VERSION || 'v1',

  // Database Configuration
  database: {
    postgres: {
      host: process.env.POSTGRES_HOST || 'localhost',
      port: process.env.POSTGRES_PORT || 5432,
      database: process.env.POSTGRES_DB || 'manufacturing_marketplace',
      user: process.env.POSTGRES_USER || 'postgres',
      password: process.env.POSTGRES_PASSWORD || 'postgres',
      maxPoolSize: parseInt(process.env.POSTGRES_MAX_POOL || '20'),
      ssl: process.env.POSTGRES_SSL === 'true'
    },
    redis: {
      host: process.env.REDIS_HOST || 'localhost',
      port: process.env.REDIS_PORT || 6379,
      password: process.env.REDIS_PASSWORD || '',
      db: parseInt(process.env.REDIS_DB || '0'),
      ttl: parseInt(process.env.REDIS_TTL || '3600')
    },
    mongodb: {
      uri: process.env.MONGODB_URI || 'mongodb://localhost:27017',
      database: process.env.MONGODB_DB || 'manufacturing_files'
    }
  },

  // JWT Configuration
  jwt: {
    secret: process.env.JWT_SECRET || 'your-secret-key-change-in-production',
    accessTokenExpiry: process.env.JWT_ACCESS_EXPIRY || '15m',
    refreshTokenExpiry: process.env.JWT_REFRESH_EXPIRY || '7d'
  },

  // Blockchain Configuration
  blockchain: {
    rpcUrl: process.env.BLOCKCHAIN_RPC_URL || 'http://localhost:8545',
    contractAddress: process.env.CONTRACT_ADDRESS || '',
    chainId: parseInt(process.env.CHAIN_ID || '1'),
    gasLimit: parseInt(process.env.GAS_LIMIT || '6000000')
  },

  // AI Service Configuration
  ai: {
    apiKey: process.env.AI_API_KEY || '',
    serviceUrl: process.env.AI_SERVICE_URL || 'http://localhost:5000'
  },

  // Email Configuration
  email: {
    provider: process.env.EMAIL_PROVIDER || 'sendgrid',
    apiKey: process.env.EMAIL_API_KEY || '',
    fromEmail: process.env.EMAIL_FROM || 'noreply@projectbingo.com',
    fromName: process.env.EMAIL_FROM_NAME || 'ProjectBINGO'
  },

  // SMS Configuration
  sms: {
    provider: process.env.SMS_PROVIDER || 'twilio',
    accountSid: process.env.TWILIO_ACCOUNT_SID || '',
    authToken: process.env.TWILIO_AUTH_TOKEN || '',
    fromNumber: process.env.TWILIO_FROM_NUMBER || ''
  },

  // File Storage Configuration
  storage: {
    provider: process.env.STORAGE_PROVIDER || 'local',
    s3: {
      bucket: process.env.S3_BUCKET || '',
      region: process.env.S3_REGION || 'us-east-1',
      accessKeyId: process.env.S3_ACCESS_KEY_ID || '',
      secretAccessKey: process.env.S3_SECRET_ACCESS_KEY || ''
    },
    local: {
      uploadDir: process.env.UPLOAD_DIR || './uploads'
    }
  },

  // Rate Limiting
  rateLimit: {
    windowMs: parseInt(process.env.RATE_LIMIT_WINDOW || '900000'), // 15 minutes
    maxRequests: parseInt(process.env.RATE_LIMIT_MAX || '100')
  },

  // CORS Configuration
  cors: {
    origin: process.env.CORS_ORIGIN || '*',
    credentials: true
  },

  // Monitoring Configuration
  monitoring: {
    prometheus: {
      enabled: process.env.PROMETHEUS_ENABLED === 'true',
      port: parseInt(process.env.PROMETHEUS_PORT || '9090')
    },
    jaeger: {
      enabled: process.env.JAEGER_ENABLED === 'true',
      host: process.env.JAEGER_HOST || 'localhost',
      port: parseInt(process.env.JAEGER_PORT || '6831')
    }
  },

  // Service URLs
  services: {
    userService: process.env.USER_SERVICE_URL || 'http://localhost:3001',
    manufacturerService: process.env.MANUFACTURER_SERVICE_URL || 'http://localhost:3002',
    orderService: process.env.ORDER_SERVICE_URL || 'http://localhost:3003',
    paymentService: process.env.PAYMENT_SERVICE_URL || 'http://localhost:3004',
    aiService: process.env.AI_SERVICE_URL || 'http://localhost:3005',
    notificationService: process.env.NOTIFICATION_SERVICE_URL || 'http://localhost:3006',
    fileService: process.env.FILE_SERVICE_URL || 'http://localhost:3007'
  },

  // Logging Configuration
  logging: {
    level: process.env.LOG_LEVEL || 'info',
    format: process.env.LOG_FORMAT || 'json'
  }
};

module.exports = config;
