-- tw-invest-suite MySQL Schema
-- Target: MySQL 8.0+
-- Database: tw_elec

CREATE DATABASE IF NOT EXISTS tw_elec
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE tw_elec;

-- ============================================================
-- Table 1: daily_data2_full
-- 個股每日 OHLCV + 三大法人 + 融資融券 + 技術指標
-- ============================================================
CREATE TABLE IF NOT EXISTS daily_data2_full (
    Ticker           VARCHAR(6)    NOT NULL,
    Date             DATE          NOT NULL,
    Open             DECIMAL(10,2),
    High             DECIMAL(10,2),
    Low              DECIMAL(10,2),
    Close            DECIMAL(10,2),
    Volume           BIGINT        COMMENT '成交量（張）',
    ForeignNet       BIGINT        COMMENT '外資買賣超（股）',
    InvestmentNet    BIGINT        COMMENT '投信買賣超（股）',
    DealerNet        BIGINT        COMMENT '自營買賣超（股）',
    ThreeNet         BIGINT        COMMENT '三大法人合計（股）',
    MarginBalance    BIGINT        COMMENT '融資餘額（張）',
    ShortBalance     BIGINT        COMMENT '融券餘額（張）',
    sma_13           DECIMAL(10,2),
    sma_27           DECIMAL(10,2),
    sma_54           DECIMAL(10,2),
    rsi_14           DECIMAL(5,2),
    atr_14           DECIMAL(10,2),
    macd             DECIMAL(10,4),
    macd_signal      DECIMAL(10,4),
    macd_hist        DECIMAL(10,4),
    bb_upper         DECIMAL(10,2),
    bb_middle        DECIMAL(10,2),
    bb_lower         DECIMAL(10,2),
    kd_k             DECIMAL(5,2),
    kd_d             DECIMAL(5,2),
    PRIMARY KEY (Ticker, Date),
    INDEX idx_date (Date),
    INDEX idx_ticker_date (Ticker, Date DESC)
) ENGINE=InnoDB;

-- ============================================================
-- Table 2: stock_news
-- 新聞（含 sentiment 標記）
-- ============================================================
CREATE TABLE IF NOT EXISTS stock_news (
    id               BIGINT        AUTO_INCREMENT PRIMARY KEY,
    ticker           VARCHAR(6)    NOT NULL,
    title            TEXT,
    source           VARCHAR(64),
    url              TEXT,
    published_at     DATETIME,
    sentiment_label  VARCHAR(16)   COMMENT 'pos / neg / neutral',
    body             TEXT,
    INDEX idx_ticker_time (ticker, published_at DESC),
    INDEX idx_time (published_at DESC)
) ENGINE=InnoDB;

-- ============================================================
-- Table 3: industry_type
-- ============================================================
CREATE TABLE IF NOT EXISTS industry_type (
    ticker           VARCHAR(6)    PRIMARY KEY,
    industry         VARCHAR(64)
) ENGINE=InnoDB;

-- ============================================================
-- Table 4: market_screen_runs
-- ============================================================
CREATE TABLE IF NOT EXISTS market_screen_runs (
    id               INT           AUTO_INCREMENT PRIMARY KEY,
    run_at           DATETIME,
    total_tickers    INT,
    notes            TEXT
) ENGINE=InnoDB;

-- ============================================================
-- Table 5: market_screen_picks
-- ============================================================
CREATE TABLE IF NOT EXISTS market_screen_picks (
    id               INT           AUTO_INCREMENT PRIMARY KEY,
    run_id           INT           NOT NULL,
    ticker           VARCHAR(6)    NOT NULL,
    direction        ENUM('long', 'short') NOT NULL,
    price_bucket     ENUM('small', 'mid', 'large', 'mega') NOT NULL,
    score            DECIMAL(10,4),
    rank_in_bucket   TINYINT,
    reasoning        TEXT,
    FOREIGN KEY (run_id) REFERENCES market_screen_runs(id),
    INDEX idx_run (run_id)
) ENGINE=InnoDB;
