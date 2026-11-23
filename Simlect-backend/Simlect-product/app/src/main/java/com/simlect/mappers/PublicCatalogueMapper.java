package com.simlect.mappers;

import org.apache.ibatis.annotations.*;
import java.util.*;

/** Preserve original public records; explicit administrator publication can bind a separate Product row. */
public interface PublicCatalogueMapper {
    @Update("UPDATE product_property_value SET property_value=#{value} WHERE product_id=#{id} AND property_value_id='ABO_STD'")
    int updateLocalSpecification(@Param("id") String id,@Param("value") String value);
    @Update("UPDATE ${catalogueSchema}.source_record SET field_sources=JSON_SET(field_sources,'$.catalogueStatus','LOCAL_STORE','$.stock','SYNTHETIC','$.name','MANUAL') WHERE target_service='product' AND target_id=#{id} AND entity_type='public_product' AND batch_id='ABO31_b4ef2d61d164a322b29e1596e9e82cd3'")
    int markLocalCatalogue(@Param("id") String id);
    @Select({"<script>SELECT target_id AS productId,original_id AS sourceId,batch_id AS batchId,source_type AS sourceType,source_name AS sourceName FROM ${catalogueSchema}.source_record WHERE target_service='product' AND JSON_UNQUOTE(JSON_EXTRACT(field_sources,'$.catalogueStatus'))='LOCAL_STORE' AND target_id IN <foreach collection='ids' item='id' open='(' separator=',' close=')'>#{id}</foreach></script>"})
    List<Map<String,Object>> localBindings(@Param("ids") List<String> ids);
    @Select("SELECT status FROM ${catalogueSchema}.etl_batch WHERE batch_id='ABO31_b4ef2d61d164a322b29e1596e9e82cd3' FOR UPDATE")
    String lockAboBatch();
    @Update("UPDATE ${catalogueSchema}.source_record SET target_service='product',target_id=#{productId},currency='CNY',field_sources=JSON_SET(field_sources,'$.price','MANUAL_LOCAL_STORE_PRICE','$.sku','LOCAL_STORE_SPECIFICATION','$.stock','UNKNOWN','$.image','PUBLIC_DATASET') WHERE batch_id='ABO31_b4ef2d61d164a322b29e1596e9e82cd3' AND entity_type='public_product' AND original_id=#{sourceId} AND target_id IS NULL")
    int bindAboProduct(@Param("sourceId") String sourceId,@Param("productId") String productId);
    String FILTER=" FROM ${catalogueSchema}.source_record s JOIN ${catalogueSchema}.historical_record h ON h.record_key=s.record_key JOIN ${catalogueSchema}.etl_batch b ON b.batch_id=s.batch_id WHERE s.source_type='PUBLIC_DATASET' AND s.entity_type='public_product' AND b.status='COMMITTED' AND (#{category}='' OR JSON_UNQUOTE(JSON_EXTRACT(h.payload,'$.category'))=#{category}) AND (#{keyword}='' OR JSON_UNQUOTE(JSON_EXTRACT(h.payload,'$.productName')) LIKE CONCAT('%',#{keyword},'%')) ";
    @Select("SELECT h.payload"+FILTER+" ORDER BY s.original_id LIMIT #{size} OFFSET #{offset}")
    @Results(@Result(column="payload",property="payload",javaType=String.class,typeHandler=org.apache.ibatis.type.StringTypeHandler.class))
    List<Map<String,Object>> list(@Param("keyword") String keyword,@Param("category") String category,@Param("offset") int offset,@Param("size") int size);
    @Select("SELECT COUNT(*)"+FILTER)
    long count(@Param("keyword") String keyword,@Param("category") String category);
    @Select("SELECT b.batch_id AS batchId,b.dataset,b.source_version AS sourceVersion,b.status,b.created_at AS createdAt,COUNT(s.record_key) AS records FROM ${catalogueSchema}.etl_batch b LEFT JOIN ${catalogueSchema}.source_record s ON s.batch_id=b.batch_id WHERE b.batch_id LIKE 'WD31_%' OR b.batch_id LIKE 'ABO31_%' OR b.batch_id LIKE 'REF31_%' GROUP BY b.batch_id,b.dataset,b.source_version,b.status,b.created_at ORDER BY b.created_at DESC LIMIT 50")
    List<Map<String,Object>> batches();
}
