-- Stage 26. Apply explicitly after backup; existing business rows are untouched.
USE simlect_search;
ALTER TABLE knowledge_document ADD COLUMN category varchar(32) NOT NULL DEFAULT 'PLATFORM_DEMO';
ALTER TABLE knowledge_document ADD COLUMN issuer varchar(200) NOT NULL DEFAULT '';
ALTER TABLE knowledge_document ADD COLUMN original_url varchar(1000) NOT NULL DEFAULT '';
ALTER TABLE knowledge_document ADD COLUMN published_on date NULL;
ALTER TABLE knowledge_document ADD COLUMN effective_from datetime NULL;
ALTER TABLE knowledge_document ADD COLUMN effective_until datetime NULL;
ALTER TABLE knowledge_document ADD COLUMN source_status varchar(24) NOT NULL DEFAULT 'UNVERIFIED';
ALTER TABLE knowledge_document ADD COLUMN reviewed_revision bigint NOT NULL DEFAULT 0;
ALTER TABLE knowledge_document ADD COLUMN reviewed_by varchar(80) NOT NULL DEFAULT '';
ALTER TABLE knowledge_document ADD COLUMN index_state varchar(24) NOT NULL DEFAULT 'NOT_INDEXED';
CREATE TABLE IF NOT EXISTS knowledge_document_source (
 document_id varchar(36) NOT NULL,
 revision bigint NOT NULL,
 original_bytes mediumblob NOT NULL,
 PRIMARY KEY(document_id,revision)
);
CREATE TABLE IF NOT EXISTS knowledge_policy_audit (
 audit_id bigint NOT NULL AUTO_INCREMENT PRIMARY KEY,
 document_id varchar(36) NOT NULL,
 revision bigint NOT NULL,
 action varchar(32) NOT NULL,
 actor varchar(80) NOT NULL,
 from_state varchar(20) NOT NULL,
 to_state varchar(20) NOT NULL,
 snapshot_json mediumtext NOT NULL,
 created_at datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
 KEY policy_timeline(document_id,audit_id)
);
