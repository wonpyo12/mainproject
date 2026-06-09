// [MySQL] mysql2/promise 커넥션 풀 - Spring Boot와 동일한 cartpilot_db 공유
const mysql = require('mysql2/promise');
require('dotenv').config();

const pool = mysql.createPool({
  host:     process.env.DB_HOST     || 'localhost',
  port:     Number(process.env.DB_PORT) || 3306,
  database: process.env.DB_NAME     || 'cartpilot_db',
  user:     process.env.DB_USER     || 'root',
  password: process.env.DB_PASSWORD || '',
  waitForConnections: true,
  connectionLimit: 10,
  queueLimit: 0,
  timezone: '+09:00',
});

pool.getConnection()
  .then(conn => { console.log('[MySQL] Connected'); conn.release(); })
  .catch(err => console.error('[MySQL] Connection failed:', err.message));

module.exports = pool;
