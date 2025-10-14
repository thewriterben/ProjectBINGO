/**
 * User Validation Schemas
 */

const Joi = require('joi');

const updateProfileSchema = Joi.object({
  walletAddress: Joi.string()
    .pattern(/^0x[a-fA-F0-9]{40}$/)
    .allow(null, '')
    .messages({
      'string.pattern.base': 'Invalid wallet address format'
    }),
  
  profile: Joi.object({
    firstName: Joi.string().max(50),
    lastName: Joi.string().max(50),
    phone: Joi.string().max(20),
    company: Joi.string().max(100),
    location: Joi.string().max(200),
    bio: Joi.string().max(500)
  }).unknown(true)
});

module.exports = {
  updateProfileSchema
};
