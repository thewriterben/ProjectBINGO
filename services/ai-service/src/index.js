const express = require('express');
const cors = require('cors');
const config = require('../../../shared/config');
const Logger = require('../../../shared/utils/logger');
const errorHandler = require('../../../shared/middleware/errorHandler');
const {
  NLPEngine,
  FraudDetector,
  RecommendationEngine,
  PredictiveAnalytics
} = require('./models/deepLearning');

const app = express();
const logger = new Logger('ai-service');
const PORT = process.env.AI_SERVICE_PORT || 3005;

// Initialize AI models
const nlp = new NLPEngine();
const fraudDetector = new FraudDetector();
const recommender = new RecommendationEngine();
const analytics = new PredictiveAnalytics();

app.use(cors(config.cors));
app.use(express.json());

app.get('/api/v1/health', (req, res) => {
  res.json({ status: 'healthy', service: 'ai-service', version: '2.0.0' });
});

// NLP endpoint
app.post('/api/v1/ai/parse-requirements', (req, res) => {
  const { text } = req.body;
  const parsed = nlp.parseRequirements(text);
  res.json({ success: true, data: parsed });
});

// Fraud detection endpoint
app.post('/api/v1/ai/detect-fraud', (req, res) => {
  const analysis = fraudDetector.analyzeOrder(req.body);
  res.json({ success: true, data: analysis });
});

// Recommendation endpoint
app.post('/api/v1/ai/recommend-manufacturers', (req, res) => {
  const { requirements, userHistory, manufacturers } = req.body;
  const recommendations = recommender.recommendManufacturers(
    requirements || {},
    userHistory || [],
    manufacturers || []
  );
  res.json({ success: true, data: recommendations });
});

// Predictive analytics endpoints
app.post('/api/v1/ai/predict-demand', (req, res) => {
  const { historicalData, timeframe } = req.body;
  const prediction = analytics.predictDemand(historicalData || [], timeframe);
  res.json({ success: true, data: prediction });
});

app.post('/api/v1/ai/predict-completion', (req, res) => {
  const { orderSpecs, manufacturerData } = req.body;
  const prediction = analytics.predictCompletionTime(orderSpecs, manufacturerData);
  res.json({ success: true, data: prediction });
});

// Legacy endpoints (for backward compatibility)
app.post('/api/v1/ai/estimate-cost', (req, res) => {
  res.json({ success: true, data: { estimatedCost: 1000, estimatedDays: 7 } });
});

app.post('/api/v1/ai/match-manufacturers', (req, res) => {
  res.json({ success: true, data: { matches: [] } });
});

app.use(errorHandler('ai-service'));

app.listen(PORT, () => {
  logger.info(\`AI Service started on port \${PORT}\`);
});

module.exports = app;
