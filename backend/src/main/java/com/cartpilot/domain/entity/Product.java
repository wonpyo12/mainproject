package com.cartpilot.domain.entity;

import jakarta.persistence.*;
import lombok.*;

@Entity
@Table(name = "products",
        indexes = @Index(name = "idx_rfid_tag", columnList = "rfid_tag"))
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "rfid_tag", length = 50, nullable = false, unique = true)
    private String rfidTag;

    @Column(name = "name", length = 100, nullable = false)
    private String name;

    @Column(name = "price", nullable = false)
    private Integer price;

    @Column(name = "category", length = 50)
    private String category;

    @Builder.Default
    @Column(name = "stock", nullable = false)
    private Integer stock = 0;
}
