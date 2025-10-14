const express = require('express');
const cors = require('cors');
const config = require('../../../shared/config');
const Logger = require('../../../shared/utils/logger');
const errorHandler = require('../../../shared/middleware/errorHandler');

const app = express();
const logger = new Logger('file-service');
const PORT = process.env.FILE_SERVICE_PORT || 3007;

app.use(cors(config.cors));
app.use(express.json());

app.get('/api/v1/health', (req, res) => {
  res.json({ status: 'healthy', service: 'file-service', version: '1.0.0' });
});

app.use(errorHandler('file-service'));

app.listen(PORT, () => {
  logger.info(\`File Service started on port \${PORT}\`);
});

module.exports = app;
