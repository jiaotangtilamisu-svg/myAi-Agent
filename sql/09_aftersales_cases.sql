-- Review and apply explicitly; application startup never executes this migration.
-- Additive tables only. No existing orders, FAQ, payment or refund records are changed.
USE simlect_order;
CREATE TABLE IF NOT EXISTS aftersales_case (
  case_id varchar(36) NOT NULL PRIMARY KEY,
  user_id varchar(64) NOT NULL,
  order_id varchar(64) NOT NULL,
  source_message_id bigint NOT NULL,
  request_hash char(64) NOT NULL,
  state varchar(32) NOT NULL,
  version bigint NOT NULL,
  plan_version bigint NOT NULL,
  risk varchar(8) NOT NULL,
  diagnosis_json mediumtext NOT NULL,
  created_at datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  UNIQUE KEY uk_aftersales_source(user_id,source_message_id),
  KEY ix_aftersales_owner(user_id,updated_at),
  KEY ix_aftersales_state(state,updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS aftersales_plan (
  case_id varchar(36) NOT NULL,
  version bigint NOT NULL,
  risk varchar(8) NOT NULL,
  content_json mediumtext NOT NULL,
  created_at datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY(case_id,version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS aftersales_manual_task (
  task_id varchar(36) NOT NULL PRIMARY KEY,
  case_id varchar(36) NOT NULL,
  plan_version bigint NOT NULL,
  attempt int NOT NULL,
  state varchar(24) NOT NULL,
  handler varchar(200),
  result_note varchar(2000),
  started_at datetime(3),
  finished_at datetime(3),
  created_at datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  UNIQUE KEY uk_aftersales_attempt(case_id,plan_version,attempt)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS aftersales_audit (
  event_id varchar(36) NOT NULL PRIMARY KEY,
  case_id varchar(36) NOT NULL,
  case_version bigint NOT NULL,
  plan_version bigint NOT NULL,
  request_id varchar(80) NOT NULL,
  request_hash char(64) NOT NULL,
  actor_type varchar(12) NOT NULL,
  actor_id varchar(200) NOT NULL,
  action varchar(24) NOT NULL,
  from_state varchar(32),
  to_state varchar(32) NOT NULL,
  note varchar(2000) NOT NULL,
  created_at datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  UNIQUE KEY uk_aftersales_version(case_id,case_version),
  UNIQUE KEY uk_aftersales_request(case_id,request_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
