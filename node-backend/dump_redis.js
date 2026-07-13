const redis = require('./src/config/redis');

async function dump() {
  try {
    const keys = await redis.keys('*');
    console.log('--- Redis Keys ---');
    for (const key of keys) {
      const type = await redis.type(key);
      let val;
      if (type === 'hash') {
        val = await redis.hgetall(key);
      } else if (type === 'string') {
        val = await redis.get(key);
      } else if (type === 'list') {
        val = await redis.lrange(key, 0, -1);
      } else {
        val = 'unsupported type';
      }
      console.log(`${key} (${type}):`, val);
    }
    console.log('------------------');
    await redis.quit();
  } catch (err) {
    console.error('Error dumping Redis:', err);
  }
}

dump();
