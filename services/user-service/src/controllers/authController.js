/**
 * Authentication Controller
 */

const { hashPassword, comparePassword, generateToken } = require('../../../../shared/utils/crypto');
const { generateAccessToken, generateRefreshToken } = require('../../../../shared/utils/jwt');
const { getPostgresPool, getRedisClient } = require('../../../../shared/utils/database');
const { ValidationError, AuthenticationError } = require('../../../../shared/utils/errors');
const Logger = require('../../../../shared/utils/logger');

const logger = new Logger('auth-controller');

/**
 * Register a new user
 */
exports.register = async (req, res, next) => {
  const client = getPostgresPool();
  
  try {
    const { email, password, role, walletAddress, profile } = req.body;
    
    // Check if user already exists
    const existingUser = await client.query(
      'SELECT id FROM users WHERE email = $1',
      [email]
    );
    
    if (existingUser.rows.length > 0) {
      throw new ValidationError('Email already registered');
    }
    
    // Hash password
    const passwordHash = await hashPassword(password);
    
    // Insert user
    const result = await client.query(
      `INSERT INTO users (email, password_hash, role, wallet_address, profile, created_at, updated_at)
       VALUES ($1, $2, $3, $4, $5, NOW(), NOW())
       RETURNING id, email, role, wallet_address, created_at`,
      [email, passwordHash, role || 'buyer', walletAddress, JSON.stringify(profile || {})]
    );
    
    const user = result.rows[0];
    
    // Generate tokens
    const accessToken = generateAccessToken({
      userId: user.id,
      email: user.email,
      role: user.role
    });
    
    const refreshToken = generateRefreshToken({
      userId: user.id
    });
    
    // Store refresh token in Redis
    const redisClient = await getRedisClient();
    await redisClient.setEx(
      `refresh_token:${user.id}`,
      7 * 24 * 60 * 60, // 7 days
      refreshToken
    );
    
    logger.info('User registered successfully', { userId: user.id, email: user.email });
    
    res.status(201).json({
      success: true,
      data: {
        user: {
          id: user.id,
          email: user.email,
          role: user.role,
          walletAddress: user.wallet_address,
          createdAt: user.created_at
        },
        accessToken,
        refreshToken
      }
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Login user
 */
exports.login = async (req, res, next) => {
  const client = getPostgresPool();
  
  try {
    const { email, password } = req.body;
    
    // Find user
    const result = await client.query(
      'SELECT id, email, password_hash, role, wallet_address FROM users WHERE email = $1',
      [email]
    );
    
    if (result.rows.length === 0) {
      throw new AuthenticationError('Invalid credentials');
    }
    
    const user = result.rows[0];
    
    // Verify password
    const isValid = await comparePassword(password, user.password_hash);
    
    if (!isValid) {
      throw new AuthenticationError('Invalid credentials');
    }
    
    // Generate tokens
    const accessToken = generateAccessToken({
      userId: user.id,
      email: user.email,
      role: user.role
    });
    
    const refreshToken = generateRefreshToken({
      userId: user.id
    });
    
    // Store refresh token in Redis
    const redisClient = await getRedisClient();
    await redisClient.setEx(
      `refresh_token:${user.id}`,
      7 * 24 * 60 * 60,
      refreshToken
    );
    
    logger.info('User logged in successfully', { userId: user.id, email: user.email });
    
    res.json({
      success: true,
      data: {
        user: {
          id: user.id,
          email: user.email,
          role: user.role,
          walletAddress: user.wallet_address
        },
        accessToken,
        refreshToken
      }
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Refresh access token
 */
exports.refresh = async (req, res, next) => {
  try {
    const { refreshToken } = req.body;
    const { verifyToken } = require('../../../../shared/utils/jwt');
    
    // Verify refresh token
    const decoded = verifyToken(refreshToken);
    
    // Check if token exists in Redis
    const redisClient = await getRedisClient();
    const storedToken = await redisClient.get(`refresh_token:${decoded.userId}`);
    
    if (storedToken !== refreshToken) {
      throw new AuthenticationError('Invalid refresh token');
    }
    
    // Get user data
    const client = getPostgresPool();
    const result = await client.query(
      'SELECT id, email, role FROM users WHERE id = $1',
      [decoded.userId]
    );
    
    if (result.rows.length === 0) {
      throw new AuthenticationError('User not found');
    }
    
    const user = result.rows[0];
    
    // Generate new access token
    const accessToken = generateAccessToken({
      userId: user.id,
      email: user.email,
      role: user.role
    });
    
    res.json({
      success: true,
      data: {
        accessToken
      }
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Logout user
 */
exports.logout = async (req, res, next) => {
  try {
    const { refreshToken } = req.body;
    const { verifyToken } = require('../../../../shared/utils/jwt');
    
    // Verify token to get user ID
    const decoded = verifyToken(refreshToken);
    
    // Remove refresh token from Redis
    const redisClient = await getRedisClient();
    await redisClient.del(`refresh_token:${decoded.userId}`);
    
    logger.info('User logged out successfully', { userId: decoded.userId });
    
    res.json({
      success: true,
      message: 'Logged out successfully'
    });
  } catch (error) {
    next(error);
  }
};
