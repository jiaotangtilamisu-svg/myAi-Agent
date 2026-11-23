package com.simlect.biz.impl;

import com.simlect.biz.ProductAgentQueryService;
import com.simlect.component.ProductBloomFilterComponent;
import com.simlect.entity.po.*;
import com.simlect.entity.query.*;
import com.simlect.mappers.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

@ExtendWith(MockitoExtension.class)
class ProductReadContractTest {
    @Mock ProductInfoMapper<ProductInfo,ProductInfoQuery> productInfoMapper;
    @Mock ProductPropertyValueMapper productPropertyValueMapper;
    @Mock ProductSkuMapper productSkuMapper;
    @Mock ProductBloomFilterComponent productBloomFilterComponent;
    @Mock ProductAgentQueryService productAgentQueryService;
    @InjectMocks ProductInfoServiceImpl service;
    @Test void detailKeepsUnknownPriceAndStockAndUsesOneBatch(){check(null,"MISSING");}
    @Test void detailKeepsUnavailableDistinct(){check(null,"UNAVAILABLE");}
    @Test void detailKeepsRealZeroStock(){check(0,"SUCCESS");}
    void check(Integer stock,String status){
        when(productBloomFilterComponent.mightExist("p")).thenReturn(true);
        ProductInfo p=new ProductInfo();p.setProductId("p");when(productInfoMapper.selectByProductId("p")).thenReturn(p);
        when(productPropertyValueMapper.selectList(any())).thenReturn(List.of());
        ProductSku a=new ProductSku();a.setProductId("p");a.setPropertyValueIdHash("a");
        ProductSku b=new ProductSku();b.setProductId("p");b.setPropertyValueIdHash("b");
        when(productSkuMapper.selectList(any())).thenReturn(List.of(a,b));
        Map<String,Object> row=new HashMap<>();row.put("skuId","a");row.put("stock",stock);row.put("stockQueryStatus",status);
        Map<String,Object> row2=new HashMap<>(row);row2.put("skuId","b");
        when(productAgentQueryService.queryBatch(List.of("p"))).thenReturn(Map.of("products",List.of(Map.of("skus",List.of(row,row2)))));
        var result=service.getProduct4VOByProductId("p");
        assertNull(result.getProductInfo().getMinPrice());assertNull(result.getSkuList().get(0).getPrice());
        assertEquals(stock,result.getSkuList().get(0).getStock());assertEquals(status,result.getSkuList().get(0).getStockQueryStatus());
        verify(productAgentQueryService,times(1)).queryBatch(List.of("p"));
    }
}
