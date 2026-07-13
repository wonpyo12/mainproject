-- ===================================================================
-- CartPilot DB 스키마 (Node.js 백엔드용)
-- Spring Boot JPA(ddl-auto: create)와 동일한 테이블 구조
-- ===================================================================

CREATE DATABASE IF NOT EXISTS cartpilot_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE cartpilot_db;

-- ───────────────────────────────────────────────
-- users 테이블 (User.java 대응)
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
  id         BIGINT       NOT NULL AUTO_INCREMENT,
  email      VARCHAR(100) NOT NULL UNIQUE,
  password   VARCHAR(255) NOT NULL,
  name       VARCHAR(50)  NOT NULL,
  phone      VARCHAR(20)  DEFAULT NULL,
  user_type  VARCHAR(20)  NOT NULL DEFAULT 'GENERAL',  -- GENERAL | ELDERLY
  created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  INDEX idx_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ───────────────────────────────────────────────
-- products 테이블 (Product.java 대응)
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS products (
  id        BIGINT       NOT NULL AUTO_INCREMENT,
  rfid_tag  VARCHAR(50)  NOT NULL UNIQUE,
  name      VARCHAR(100) NOT NULL,
  price     INT          NOT NULL,
  category  VARCHAR(50)  DEFAULT NULL,
  stock     INT          NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  INDEX idx_rfid_tag (rfid_tag)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ───────────────────────────────────────────────
-- robots 테이블 (Robot.java 대응)
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS robots (
  id            BIGINT      NOT NULL AUTO_INCREMENT,
  serial_number VARCHAR(50) NOT NULL UNIQUE,
  model         VARCHAR(50) NOT NULL DEFAULT 'TurtleBot3',
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ───────────────────────────────────────────────
-- orders 테이블 (Order.java 대응)
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
  id             BIGINT      NOT NULL AUTO_INCREMENT,
  user_id        BIGINT      NOT NULL,
  robot_id       BIGINT      NOT NULL,
  total_price    INT         NOT NULL,
  payment_status VARCHAR(20) NOT NULL DEFAULT 'COMPLETED',  -- COMPLETED | CANCELED
  ordered_at     DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  INDEX idx_user_id (user_id),
  CONSTRAINT fk_orders_user  FOREIGN KEY (user_id)  REFERENCES users(id),
  CONSTRAINT fk_orders_robot FOREIGN KEY (robot_id) REFERENCES robots(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ───────────────────────────────────────────────
-- order_items 테이블 (OrderItem.java 대응)
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS order_items (
  id         BIGINT NOT NULL AUTO_INCREMENT,
  order_id   BIGINT NOT NULL,
  product_id BIGINT NOT NULL,
  quantity   INT    NOT NULL,
  price      INT    NOT NULL,  -- 구매 시점 단가
  PRIMARY KEY (id),
  CONSTRAINT fk_items_order   FOREIGN KEY (order_id)   REFERENCES orders(id)   ON DELETE CASCADE,
  CONSTRAINT fk_items_product FOREIGN KEY (product_id) REFERENCES products(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ───────────────────────────────────────────────
-- 샘플 데이터 (테스트용)
-- ───────────────────────────────────────────────
INSERT IGNORE INTO robots (serial_number, model) VALUES
  ('ROBOT-001', 'TurtleBot3'),
  ('ROBOT-002', 'TurtleBot3');

INSERT IGNORE INTO products (rfid_tag, name, price, category, stock) VALUES
  ('RFID-APPLE-001',  '사과',      1500, '과일',  100),
  ('RFID-BANANA-001', '바나나',     800, '과일',  150),
  ('RFID-WATER-001',  '생수 500ml', 600, '음료',  200),
  ('RFID-BREAD-001',  '식빵',      2200, '베이커리', 50);

-- ───────────────────────────────────────────────
-- inquiries 테이블 (앱 '문의하기' → 웹 관리자 문의 목록)
-- ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS inquiries (
  id         BIGINT       NOT NULL AUTO_INCREMENT,
  user_id    BIGINT       DEFAULT NULL,
  name       VARCHAR(50)  DEFAULT NULL,          -- 문의자 이름(스냅샷)
  email      VARCHAR(100) DEFAULT NULL,          -- 문의자 이메일(스냅샷)
  category   VARCHAR(30)  DEFAULT '일반',         -- 문의 유형
  content    TEXT         NOT NULL,              -- 문의 내용
  answer     TEXT         DEFAULT NULL,          -- 관리자 답변 (앱에 표시)
  status     VARCHAR(20)  NOT NULL DEFAULT 'PENDING',  -- PENDING | ANSWERED
  answered_at DATETIME    DEFAULT NULL,          -- 답변 등록 시각
  created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  INDEX idx_inq_created (created_at),
  CONSTRAINT fk_inq_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
