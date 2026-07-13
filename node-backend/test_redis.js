const redis = require('./src/config/redis');

async function test() {
  try {
    console.log('Testing Redis connection...');
    await redis.ping();
    console.log('Ping successful!');

    const robotStatusKey = 'robot:status:test-robot';
    console.log('Testing hmset...');
    await redis.hmset(robotStatusKey, {
      userId: '1',
      status: 'SHOPPING',
      startedAt: new Date().toISOString(),
    });
    console.log('hset successful!');

    console.log('Reading back hgetall...');
    const data = await redis.hgetall(robotStatusKey);
    console.log('Data:', data);

    await redis.quit();
    console.log('Done!');
  } catch (err) {
    console.error('Error during Redis test:', err);
    process.exit(1);
  }
}

test();
