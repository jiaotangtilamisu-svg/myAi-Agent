-- Additive widening only. Apply with tools.data_governance.message_migration.
-- Existing rows, JSON strings and NULL values are preserved.
ALTER TABLE simlect_agent.agent_message
    MODIFY COLUMN biz_data MEDIUMTEXT NULL COMMENT '业务数据及完整证据JSON';
