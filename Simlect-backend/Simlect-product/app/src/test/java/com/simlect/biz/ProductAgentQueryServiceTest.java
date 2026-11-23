package com.simlect.biz;

import com.simlect.api.StockFeignClient;
import com.simlect.api.dto.*;
import com.simlect.entity.po.*;
import com.simlect.entity.query.*;
import com.simlect.entity.vo.ResponseVO;
import com.simlect.mappers.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import java.math.BigDecimal;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class ProductAgentQueryServiceTest {
    @Mock ProductInfoMapper<ProductInfo, ProductInfoQuery> productInfoMapper;
    @Mock ProductSkuMapper<ProductSku, ProductSkuQuery> productSkuMapper;
    @Mock ProductPropertyValueMapper<ProductPropertyValue, ProductPropertyValueQuery> productPropertyValueMapper;
    @Mock StockFeignClient stockFeignClient;
    @Mock SysCategoryMapper<SysCategory, SysCategoryQuery> sysCategoryMapper;
    @InjectMocks ProductAgentQueryService service;
    ProductInfo p;
    ProductSku sku(String hash) {
        ProductSku s = new ProductSku(); s.setProductId("P1"); s.setPropertyValueIdHash(hash);
        s.setPropertyValueIds("v1"); s.setPrice(new BigDecimal("19.90")); return s;
    }
    ResponseVO<List<SkuStockDTO>> stocks(Integer count) {
        ResponseVO<List<SkuStockDTO>> r = new ResponseVO<>(); r.setCode(200); r.setStatus("success");
        r.setData(List.of(new SkuStockDTO("P1", "h1", count))); return r;
    }
    @BeforeEach void setup() {
        p = new ProductInfo(); p.setProductId("P1"); p.setProductName("真实商品"); p.setStatus(1);
        p.setMinPrice(new BigDecimal("19.90")); p.setMaxPrice(new BigDecimal("19.90"));
    }
    void data(List<ProductSku> skus) {
        when(productInfoMapper.selectList(any())).thenReturn(List.of(p));
        when(productSkuMapper.selectList(any())).thenReturn(skus);
        when(productPropertyValueMapper.selectList(any())).thenReturn(List.of());
    }
    @SuppressWarnings("unchecked") Map<String, Object> result() {
        return ((List<Map<String,Object>>)service.queryBatch(List.of("P1")).get("products")).get(0);
    }
    @Test void singleSkuZeroIsKnownAndUsesOneBatch() {
        data(List.of(sku("h1"))); when(stockFeignClient.queryBatch(any())).thenReturn(stocks(0));
        Map<String,Object> r=result(); assertEquals(0L,r.get("totalStock")); assertEquals("OUT_OF_STOCK",r.get("availability"));
        verify(stockFeignClient,times(1)).queryBatch(argThat(d -> d.getItems().size()==1));
    }
    @Test void categoryNamesComeFromOneBoundedDatabaseRead() {
        p.setCategoryId("C1");p.setpCategoryId("C0");data(List.of(sku("h1")));
        when(stockFeignClient.queryBatch(any())).thenReturn(stocks(4));
        when(sysCategoryMapper.selectAgentNames(any())).thenReturn(List.of(Map.of("categoryId","C1","categoryName","手机"),Map.of("categoryId","C0","categoryName","数码")));
        Map<String,Object> row=result();assertEquals("手机",row.get("categoryName"));assertEquals("数码",row.get("parentCategoryName"));
        verify(sysCategoryMapper,times(1)).selectAgentNames(argThat(ids->ids.containsAll(List.of("C1","C0"))&&ids.size()==2));
        verify(stockFeignClient,times(1)).queryBatch(any());
    }
    @Test void multipleSkusUseOneRpcAndKeepAllPrices() {
        data(List.of(sku("h1"),sku("h2"))); ResponseVO<List<SkuStockDTO>> r=stocks(3);
        r.setData(List.of(new SkuStockDTO("P1","h1",3),new SkuStockDTO("P1","h2",5)));
        when(stockFeignClient.queryBatch(any())).thenReturn(r);
        assertEquals(8L,result().get("totalStock")); verify(stockFeignClient,times(1)).queryBatch(argThat(d->d.getItems().size()==2));
    }
    @Test void serviceFailureIsUnknown() {
        data(List.of(sku("h1"))); when(stockFeignClient.queryBatch(any())).thenThrow(new RuntimeException("offline"));
        Map<String,Object> r=result(); assertNull(r.get("totalStock")); assertEquals("UNKNOWN",r.get("availability"));
    }
    @Test void nullStockIsNotZero() {
        data(List.of(sku("h1"))); when(stockFeignClient.queryBatch(any())).thenReturn(stocks(null));
        assertNull(result().get("totalStock"));
    }
    @Test void missingStockRowIsNotZero() {
        data(List.of(sku("h1"))); ResponseVO<List<SkuStockDTO>> r=stocks(0);r.setData(List.of());when(stockFeignClient.queryBatch(any())).thenReturn(r);
        assertNull(result().get("totalStock"));
    }
    @Test void contradictoryResponseIsUnknown() {
        data(List.of(sku("h1"))); ResponseVO<List<SkuStockDTO>> r=stocks(10);r.setStatus("error");when(stockFeignClient.queryBatch(any())).thenReturn(r);
        assertNull(result().get("totalStock"));
    }
    @Test void wrongStockKeyIsRejected() {
        data(List.of(sku("h1")));ResponseVO<List<SkuStockDTO>> r=stocks(10);r.setData(List.of(new SkuStockDTO("OTHER","h1",10)));when(stockFeignClient.queryBatch(any())).thenReturn(r);
        assertNull(result().get("totalStock"));
    }
    @Test void offShelfRemainsNotSaleable() {
        data(List.of());p.setStatus(0);assertEquals("OFF_SHELF",result().get("productStatus"));verifyNoInteractions(stockFeignClient);
    }
    @Test void absentPriceRemainsNull() {
        data(List.of());p.setMinPrice(null);Map<String,Object> r=result();assertNull(r.get("minPrice"));assertEquals("UNKNOWN",r.get("priceStatus"));
    }
    @Test void notFoundHasExplicitStatus() {
        when(productInfoMapper.selectList(any())).thenReturn(List.of());
        when(productSkuMapper.selectList(any())).thenReturn(List.of());
        when(productPropertyValueMapper.selectList(any())).thenReturn(List.of());
        assertEquals("NOT_FOUND",result().get("queryStatus"));verifyNoInteractions(stockFeignClient);
    }
    @Test void boundsAreEnforced() {
        assertThrows(RuntimeException.class,()->service.queryBatch(Collections.nCopies(51,"P1")));verifyNoInteractions(productInfoMapper,stockFeignClient);
    }
}
