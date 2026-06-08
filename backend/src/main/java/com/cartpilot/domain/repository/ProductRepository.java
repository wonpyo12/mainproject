package com.cartpilot.domain.repository;

import com.cartpilot.domain.entity.Product;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface ProductRepository extends JpaRepository<Product, Long> {
    Optional<Product> findByRfidTag(String rfidTag);
}
