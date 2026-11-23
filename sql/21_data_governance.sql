-- Additive, isolated historical layer only. No ALTER/DROP/TRUNCATE or business table writes.
CREATE DATABASE IF NOT EXISTS simlect_data_governance CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
USE simlect_data_governance;
CREATE TABLE IF NOT EXISTS etl_batch (
 batch_id varchar(64) PRIMARY KEY, dataset varchar(160) NOT NULL, source_version varchar(100) NOT NULL,
 status varchar(24) NOT NULL, report_json JSON NOT NULL, created_at datetime(6) NOT NULL,
 completed_at datetime(6) NULL
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS source_record (
 record_key char(64) PRIMARY KEY, source_type varchar(24) NOT NULL, source_name varchar(160) NOT NULL,
 entity_type varchar(40) NOT NULL, original_id varchar(512) NOT NULL, source_version varchar(100) NOT NULL,
 batch_id varchar(64) NOT NULL, content_sha256 char(64) NOT NULL, source_url varchar(500) NOT NULL,
 license_code varchar(100) NOT NULL, currency char(3) NULL, observed_at datetime(6) NOT NULL,
 field_sources JSON NOT NULL,
 target_service varchar(40) NULL, target_id varchar(160) NULL,
 INDEX idx_source_batch(batch_id), INDEX idx_source_target(target_service,target_id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS historical_record (
 record_key char(64) PRIMARY KEY, entity_type varchar(40) NOT NULL, payload JSON NOT NULL,
 INDEX idx_historical_entity(entity_type)
) ENGINE=InnoDB;
