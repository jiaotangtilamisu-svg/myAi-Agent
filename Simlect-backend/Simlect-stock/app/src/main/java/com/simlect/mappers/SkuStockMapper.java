package com.simlect.mappers;

import com.simlect.domain.SkuStock;
import org.apache.ibatis.annotations.Param;

public interface SkuStockMapper {
    @org.apache.ibatis.annotations.Insert("INSERT IGNORE INTO sku_stock(product_id,property_value_id_hash,stock) VALUES(#{productId},#{propertyValueIdHash},#{stock})")
    int initializeIfAbsent(@Param("productId") String productId,@Param("propertyValueIdHash") String hash,@Param("stock") int stock);

    java.util.List<SkuStock> selectBatch(@Param("items") java.util.List<com.simlect.api.dto.SkuStockQueryDTO> items);

    SkuStock selectByKey(@Param("productId") String productId,
                         @Param("propertyValueIdHash") String propertyValueIdHash);

    SkuStock selectByKeyForUpdate(@Param("productId") String productId,
                                  @Param("propertyValueIdHash") String propertyValueIdHash);

    int changeStock(@Param("productId") String productId,
                    @Param("propertyValueIdHash") String propertyValueIdHash,
                    @Param("changeAmount") Integer changeAmount);

    Integer selectTotalStockByProductId(@Param("productId") String productId);

    int upsert(@Param("productId") String productId,
               @Param("propertyValueIdHash") String propertyValueIdHash,
               @Param("stock") Integer stock);

    Integer countLessThan(@Param("threshold") int threshold);

    java.util.List<SkuStock> selectLessThan(@Param("threshold") int threshold,
                                            @Param("offset") int offset,
                                            @Param("limit") int limit);

    int insertChangeOperation(@Param("operationId") String operationId);

    int insertCancelledChangeOperation(@Param("operationId") String operationId);

    Integer selectChangeOperationResult(@Param("operationId") String operationId);

    String selectChangeOperationIdForUpdate(@Param("operationId") String operationId);

    int completeChangeOperation(@Param("operationId") String operationId,
                                @Param("affectedRows") int affectedRows);
}
