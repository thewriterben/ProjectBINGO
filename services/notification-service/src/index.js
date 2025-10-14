const express = require('express');
const cors = require('cors');
const config = require('../../../shared/config');
const Logger = require('../../../shared/utils/logger');
const errorHandler = require('../../../shared/middleware/errorHandler');

const app = express();
const logger = new Logger('notification-service');
const PORT = process.env.NOTIFICATION_SERVICE_PORT || 3006;

app.use(cors(config.cors));
app.use(express.json());

app.get('/api/v1/health', (req, res) => {
  res.json({ status: 'healthy', service: 'notification-service', version: '1.0.0' });
});

app.use(errorHandler('notification-service'));

app.listen(PORT, () => {
  logger.info(\`Notification Service started on port \${PORT}\`);
});

module.exports = app;
