package com.simlect.mappers;

import com.simlect.entity.po.KnowledgeDocument;
import org.apache.ibatis.annotations.*;
import java.util.List;

public interface KnowledgeDocumentMapper {
    @Select("SELECT * FROM knowledge_document WHERE document_id=#{id} FOR UPDATE")
    KnowledgeDocument lock(String id);

    @Select("SELECT * FROM knowledge_document WHERE document_id=#{id}")
    KnowledgeDocument get(String id);

    @Select("SELECT * FROM knowledge_document ORDER BY updated_at DESC, document_id LIMIT #{limit} OFFSET #{offset}")
    List<KnowledgeDocument> list(@Param("offset") int offset, @Param("limit") int limit);
    @Select("SELECT * FROM knowledge_document WHERE (#{category} IS NULL OR category=#{category}) AND (#{state} IS NULL OR state=#{state}) ORDER BY updated_at DESC,document_id LIMIT #{limit} OFFSET #{offset}")
    List<KnowledgeDocument> filtered(@Param("offset") int offset,@Param("limit") int limit,@Param("category") String category,@Param("state") String state);

    @Insert("INSERT INTO knowledge_document(document_id,title,filename,source,revision,approved,state,indexed_revision) VALUES(#{documentId},#{title},#{filename},#{source},#{revision},#{approved},#{state},#{indexedRevision})")
    void insert(KnowledgeDocument row);

    @Update("UPDATE knowledge_document SET title=#{title},filename=#{filename},source=#{source},revision=#{revision},approved=#{approved},state=#{state},indexed_revision=#{indexedRevision},category=#{category},issuer=#{issuer},original_url=#{originalUrl},published_on=#{publishedOn},effective_from=#{effectiveFrom},effective_until=#{effectiveUntil},source_status=#{sourceStatus},reviewed_revision=#{reviewedRevision},reviewed_by=#{reviewedBy},index_state=#{indexState},updated_at=NOW() WHERE document_id=#{documentId}")
    void update(KnowledgeDocument row);

    @Insert("INSERT INTO knowledge_document_revision(document_id,revision,chunks_json) VALUES(#{id},#{revision},#{json})")
    void insertRevision(@Param("id") String id, @Param("revision") long revision, @Param("json") String json);

    @Select("SELECT chunks_json FROM knowledge_document_revision WHERE document_id=#{id} AND revision=#{revision}")
    String chunks(@Param("id") String id, @Param("revision") long revision);

    @Select("SELECT chunks_json FROM knowledge_document_revision WHERE document_id=#{id} ORDER BY revision")
    List<String> history(String id);

    @Insert("INSERT INTO knowledge_document_source(document_id,revision,original_bytes) VALUES(#{id},#{revision},#{bytes})")
    void saveOriginal(@Param("id") String id,@Param("revision") long revision,@Param("bytes") byte[] bytes);

    @Insert("INSERT INTO knowledge_policy_audit(document_id,revision,action,actor,from_state,to_state,snapshot_json) VALUES(#{id},#{revision},#{action},#{actor},#{from},#{to},#{snapshot})")
    void audit(@Param("id") String id,@Param("revision") long revision,@Param("action") String action,@Param("actor") String actor,@Param("from") String from,@Param("to") String to,@Param("snapshot") String snapshot);

    @Select("SELECT audit_id,revision,action,actor,from_state,to_state,snapshot_json,created_at FROM knowledge_policy_audit WHERE document_id=#{id} ORDER BY audit_id DESC LIMIT 200")
    List<java.util.Map<String,Object>> auditHistory(String id);

    @Select("SELECT revision FROM knowledge_document_revision WHERE document_id=#{id} ORDER BY revision DESC")
    List<Long> revisions(String id);

    @Select("SELECT original_bytes FROM knowledge_document_source WHERE document_id=#{id} AND revision=#{revision}")
    @Results(@Result(column="original_bytes",property="bytes",javaType=byte[].class,
            typeHandler=org.apache.ibatis.type.ByteArrayTypeHandler.class))
    OriginalContent originalContent(@Param("id") String id,@Param("revision") long revision);

    // A bare byte[] mapper return is interpreted as multiple scalar Byte rows.
    // Wrap the single BLOB row while retaining the service-facing contract.
    default byte[] original(String id,long revision) {
        OriginalContent row=originalContent(id,revision);
        return row==null?null:row.getBytes();
    }
    class OriginalContent {
        private byte[] bytes;
        public byte[] getBytes(){return bytes;}
        public void setBytes(byte[] value){bytes=value;}
    }
    @Select("SELECT snapshot_json FROM knowledge_policy_audit WHERE document_id=#{id} AND revision=#{revision} ORDER BY audit_id DESC LIMIT 1")
    String versionMetadata(@Param("id") String id,@Param("revision") long revision);
}
