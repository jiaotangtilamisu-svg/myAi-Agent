package com.simlect.mappers;

import org.apache.ibatis.annotations.*;
import java.util.Map;

/** Uses the existing isolated source ledger; never changes schemas. */
public interface ReferenceCatalogueMapper {
    @Insert("INSERT IGNORE INTO ${catalogueSchema}.etl_batch(batch_id,dataset,source_version,status,report_json,created_at) VALUES(#{id},'Simlect public catalogue','2026-11-04','PROCESSING','{}',NOW(6))")
    int claim(String id);
    @Select("SELECT status FROM ${catalogueSchema}.etl_batch WHERE batch_id=#{id} FOR UPDATE")
    String lock(String id);
    @Select("SELECT content_sha256 FROM ${catalogueSchema}.source_record WHERE batch_id=#{batch} AND target_service='product' AND target_id=#{id}")
    String boundHash(@Param("batch") String batch,@Param("id") String id);
    @Insert("INSERT INTO ${catalogueSchema}.source_record(record_key,source_type,source_name,entity_type,original_id,source_version,batch_id,content_sha256,source_url,license_code,currency,observed_at,field_sources,target_service,target_id) VALUES(#{key},'MANUAL','Simlect public catalogue','reference_product',#{id},'2026-11-04',#{batch},#{hash},CONCAT('https://www.simlect.com/product/',#{id}),'REFERENCE_SITE_NO_CC_CLAIM','CNY',NOW(6),'{\"catalogueStatus\":\"LOCAL_STORE\",\"name\":\"MANUAL\",\"price\":\"MANUAL\",\"sku\":\"MANUAL\",\"stock\":\"MANUAL\"}','product',#{id})")
    int bind(@Param("key") String key,@Param("id") String id,@Param("batch") String batch,@Param("hash") String hash);
    @Update("UPDATE ${catalogueSchema}.etl_batch SET status=#{state},report_json=#{report},completed_at=IF(#{state}='COMMITTED',NOW(6),NULL) WHERE batch_id=#{id}")
    int progress(@Param("id") String id,@Param("state") String state,@Param("report") String report);
}
