/**
 * Database Utilities
 * Connection management for PostgreSQL, Redis, and MongoDB
 */

const { Pool } = require('pg');
const redis = require('redis');
const { MongoClient } = require('mongodb');
const config = require('../config');
const Logger = require('./logger');

const logger = new Logger('database');

// PostgreSQL connection pool
let pgPool = null;

const getPostgresPool = () => {
  if (!pgPool) {
    pgPool = new Pool({
      host: config.database.postgres.host,
      port: config.database.postgres.port,
      database: config.database.postgres.database,
      user: config.database.postgres.user,
      password: config.database.postgres.password,
      max: config.database.postgres.maxPoolSize,
      ssl: config.database.postgres.ssl ? { rejectUnauthorized: false } : false
    });

    pgPool.on('error', (err) => {
      logger.error('PostgreSQL pool error', { error: err.message });
    });

    logger.info('PostgreSQL connection pool created');
  }

  return pgPool;
};

// Redis client
let redisClient = null;

const getRedisClient = async () => {
  if (!redisClient) {
    redisClient = redis.createClient({
      socket: {
        host: config.database.redis.host,
        port: config.database.redis.port
      },
      password: config.database.redis.password || undefined,
      database: config.database.redis.db
    });

    redisClient.on('error', (err) => {
      logger.error('Redis client error', { error: err.message });
    });

    await redisClient.connect();
    logger.info('Redis client connected');
  }

  return redisClient;
};

// MongoDB client
let mongoClient = null;
let mongoDb = null;

const getMongoDb = async () => {
  if (!mongoDb) {
    mongoClient = new MongoClient(config.database.mongodb.uri);
    await mongoClient.connect();
    mongoDb = mongoClient.db(config.database.mongodb.database);
    logger.info('MongoDB client connected');
  }

  return mongoDb;
};

// Cleanup function
const closeConnections = async () => {
  if (pgPool) {
    await pgPool.end();
    logger.info('PostgreSQL pool closed');
  }

  if (redisClient) {
    await redisClient.quit();
    logger.info('Redis client closed');
  }

  if (mongoClient) {
    await mongoClient.close();
    logger.info('MongoDB client closed');
  }
};

module.exports = {
  getPostgresPool,
  getRedisClient,
  getMongoDb,
  closeConnections
};
