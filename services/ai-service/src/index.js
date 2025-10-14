const express = require('express');
const cors = require('cors');
const config = require('../../../shared/config');
const Logger = require('../../../shared/utils/logger');
const errorHandler = require('../../../shared/middleware/errorHandler');

const app = express();
const logger = new Logger('ai-service');
const PORT = process.env.AI_SERVICE_PORT || 3005;

app.use(cors(config.cors));
app.use(express.json());

app.get('/api/v1/health', (req, res) => {
  res.json({ status: 'healthy', service: 'ai-service', version: '1.0.0' });
});

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
