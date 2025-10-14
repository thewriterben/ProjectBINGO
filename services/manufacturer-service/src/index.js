const express = require('express');
const cors = require('cors');
const config = require('../../../shared/config');
const Logger = require('../../../shared/utils/logger');
const errorHandler = require('../../../shared/middleware/errorHandler');

const app = express();
const logger = new Logger('manufacturer-service');
const PORT = process.env.MANUFACTURER_SERVICE_PORT || 3002;

app.use(cors(config.cors));
app.use(express.json());

app.get('/api/v1/health', (req, res) => {
  res.json({ status: 'healthy', service: 'manufacturer-service', version: '1.0.0' });
});

app.get('/api/v1/manufacturers', (req, res) => {
  res.json({ success: true, data: { manufacturers: [], count: 0 } });
});

app.use(errorHandler('manufacturer-service'));

app.listen(PORT, () => {
  logger.info(\`Manufacturer Service started on port \${PORT}\`);
});

module.exports = app;
