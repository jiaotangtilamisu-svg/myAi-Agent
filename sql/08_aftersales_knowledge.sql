-- Apply explicitly to the Search database after review; never executed by application startup.
USE simlect_search;
CREATE TABLE IF NOT EXISTS knowledge_document (
  document_id varchar(36) NOT NULL PRIMARY KEY,
  title varchar(200) NOT NULL,
  filename varchar(200) NOT NULL,
  source varchar(1000) NOT NULL,
  revision bigint NOT NULL,
  approved boolean NOT NULL DEFAULT false,
  state varchar(20) NOT NULL DEFAULT 'DRAFT',
  indexed_revision bigint NOT NULL DEFAULT 0,
  updated_at datetime NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS knowledge_document_revision (
  document_id varchar(36) NOT NULL,
  revision bigint NOT NULL,
  chunks_json mediumtext NOT NULL,
  PRIMARY KEY(document_id, revision)
);
