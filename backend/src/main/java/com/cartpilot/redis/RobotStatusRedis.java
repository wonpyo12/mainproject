package com.cartpilot.redis;

import lombok.RequiredArgsConstructor;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Component;

import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;

@Component
@RequiredArgsConstructor
public class RobotStatusRedis {

    private static final String KEY_PREFIX = "robot:status:";

    public static final String FIELD_CURRENT_USER_ID = "current_user_id";
    public static final String FIELD_STATUS = "status";
    public static final String FIELD_POS_X = "pos_x";
    public static final String FIELD_POS_Y = "pos_y";
    public static final String FIELD_BATTERY = "battery";
    public static final String FIELD_LAST_PING = "last_ping";

    private final RedisTemplate<String, String> redisTemplate;

    private String key(Long robotId) {
        return KEY_PREFIX + robotId;
    }

    /**
     * 여러 필드를 한 번에 갱신 (HMSET). ROS2 노드에서 주기적으로 전체 상태를 업데이트할 때 사용.
     */
    public void updateFields(Long robotId, Map<String, String> fields) {
        redisTemplate.opsForHash().putAll(key(robotId), fields);
    }

    public void updateField(Long robotId, String field, String value) {
        redisTemplate.opsForHash().put(key(robotId), field, value);
    }

    public Optional<Map<String, String>> getStatus(Long robotId) {
        Map<Object, Object> raw = redisTemplate.opsForHash().entries(key(robotId));
        if (raw.isEmpty())
            return Optional.empty();
        Map<String, String> result = raw.entrySet().stream()
                .collect(Collectors.toMap(
                        e -> (String) e.getKey(),
                        e -> (String) e.getValue()));
        return Optional.of(result);
    }

    public Optional<String> getField(Long robotId, String field) {
        Object value = redisTemplate.opsForHash().get(key(robotId), field);
        return Optional.ofNullable((String) value);
    }

    public void delete(Long robotId) {
        redisTemplate.delete(key(robotId));
    }
}
