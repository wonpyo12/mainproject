package com.cartpilot.domain.repository;

import com.cartpilot.domain.entity.Robot;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface RobotRepository extends JpaRepository<Robot, Long> {
    Optional<Robot> findBySerialNumber(String serialNumber);
}
