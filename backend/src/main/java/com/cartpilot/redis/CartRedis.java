package com.cartpilot.redis;

import lombok.RequiredArgsConstructor;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.Map;
import java.util.stream.Collectors;

@Component
@RequiredArgsConstructor
public class CartRedis {

    private static final String KEY_PREFIX = "cart:";
    private static final Duration TTL = Duration.ofHours(3);
    private static final String FIELD_PREFIX = "product_id:";

    private final RedisTemplate<String, String> redisTemplate;

    private String key(Long userId, Long robotId) {
        return KEY_PREFIX + userId + ":" + robotId;
    }

    private String field(Long productId) {
        return FIELD_PREFIX + productId;
    }

    /**
     * 상품 수량 추가/증가. HINCRBY를 사용해 원자적으로 처리 (RFID 동시 스캔 대응).
     * 매 호출마다 TTL을 3시간으로 갱신 (슬라이딩 윈도우).
     */
    public void addItem(Long userId, Long robotId, Long productId, int quantity) {
        String k = key(userId, robotId);
        redisTemplate.opsForHash().increment(k, field(productId), quantity);
        redisTemplate.expire(k, TTL);
    }

    public void removeItem(Long userId, Long robotId, Long productId) {
        redisTemplate.opsForHash().delete(key(userId, robotId), field(productId));
    }

    public Map<Long, Integer> getCart(Long userId, Long robotId) {
        Map<Object, Object> raw = redisTemplate.opsForHash().entries(key(userId, robotId));
        return raw.entrySet().stream()
                .collect(Collectors.toMap(
                        e -> Long.parseLong(((String) e.getKey()).replace(FIELD_PREFIX, "")),
                        e -> Integer.parseInt((String) e.getValue())));
    }

    public void clearCart(Long userId, Long robotId) {
        redisTemplate.delete(key(userId, robotId));
    }
}
