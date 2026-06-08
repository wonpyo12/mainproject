package com.cartpilot.redis;

import lombok.RequiredArgsConstructor;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.Optional;

@Component
@RequiredArgsConstructor
public class QrSessionRedis {

    private static final String KEY_PREFIX = "qr:auth:";
    private static final Duration TTL = Duration.ofSeconds(180);

    private final StringRedisTemplate stringRedisTemplate;

    public void save(String token, Long userId) {
        stringRedisTemplate.opsForValue()
                .set(KEY_PREFIX + token, String.valueOf(userId), TTL);
    }

    public Optional<Long> findUserId(String token) {
        String value = stringRedisTemplate.opsForValue().get(KEY_PREFIX + token);
        return Optional.ofNullable(value).map(Long::parseLong);
    }

    public void delete(String token) {
        stringRedisTemplate.delete(KEY_PREFIX + token);
    }
}
