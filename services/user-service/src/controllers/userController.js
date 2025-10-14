/**
 * User Controller
 */

const { getPostgresPool } = require('../../../../shared/utils/database');
const { NotFoundError } = require('../../../../shared/utils/errors');
const Logger = require('../../../../shared/utils/logger');

const logger = new Logger('user-controller');

/**
 * Get current user profile
 */
exports.getProfile = async (req, res, next) => {
  const client = getPostgresPool();
  
  try {
    const userId = req.user.userId;
    
    const result = await client.query(
      `SELECT id, email, role, wallet_address, profile, created_at, updated_at
       FROM users WHERE id = $1`,
      [userId]
    );
    
    if (result.rows.length === 0) {
      throw new NotFoundError('User');
    }
    
    const user = result.rows[0];
    
    res.json({
      success: true,
      data: {
        id: user.id,
        email: user.email,
        role: user.role,
        walletAddress: user.wallet_address,
        profile: user.profile,
        createdAt: user.created_at,
        updatedAt: user.updated_at
      }
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Update current user profile
 */
exports.updateProfile = async (req, res, next) => {
  const client = getPostgresPool();
  
  try {
    const userId = req.user.userId;
    const { walletAddress, profile } = req.body;
    
    const result = await client.query(
      `UPDATE users
       SET wallet_address = COALESCE($1, wallet_address),
           profile = COALESCE($2, profile),
           updated_at = NOW()
       WHERE id = $3
       RETURNING id, email, role, wallet_address, profile, updated_at`,
      [walletAddress, JSON.stringify(profile), userId]
    );
    
    if (result.rows.length === 0) {
      throw new NotFoundError('User');
    }
    
    const user = result.rows[0];
    
    logger.info('User profile updated', { userId: user.id });
    
    res.json({
      success: true,
      data: {
        id: user.id,
        email: user.email,
        role: user.role,
        walletAddress: user.wallet_address,
        profile: user.profile,
        updatedAt: user.updated_at
      }
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Get user by ID
 */
exports.getUserById = async (req, res, next) => {
  const client = getPostgresPool();
  
  try {
    const { userId } = req.params;
    
    const result = await client.query(
      `SELECT id, email, role, wallet_address, profile, created_at
       FROM users WHERE id = $1`,
      [userId]
    );
    
    if (result.rows.length === 0) {
      throw new NotFoundError('User');
    }
    
    const user = result.rows[0];
    
    res.json({
      success: true,
      data: {
        id: user.id,
        email: user.email,
        role: user.role,
        walletAddress: user.wallet_address,
        profile: user.profile,
        createdAt: user.created_at
      }
    });
  } catch (error) {
    next(error);
  }
};
