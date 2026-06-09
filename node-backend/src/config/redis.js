// [Redis] ioredis 클라이언트 - QR 세션, 실시간 장바구니, 로봇 상태 저장
const Redis = require('ioredis');
require('dotenv').config();

const redis = new Redis({
  host: process.env.REDIS_HOST || 'localhost',
  port: Number(process.env.REDIS_PORT) || 6379,
  retryStrategy: (times) => Math.min(times * 50, 2000),
  lazyConnect: false,
});

redis.on('connect', () => console.log('[Redis] Connected'));
redis.on('error',   (err) => console.error('[Redis] Error:', err.message || String(err)));

module.exports = redis;
