package com.cartpilot.domain.entity;

import jakarta.persistence.*;
import lombok.*;

@Entity
@Table(name = "robots")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
public class Robot {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "serial_number", length = 50, nullable = false, unique = true)
    private String serialNumber;

    @Builder.Default
    @Column(name = "model", length = 50, nullable = false)
    private String model = "TurtleBot3";
}
