package com.simlect.biz;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.simlect.entity.po.*;
import com.simlect.entity.query.*;
import com.simlect.mappers.*;
import com.simlect.exception.BusinessException;
import org.junit.jupiter.api.*;
import org.mockito.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class ReferenceCatalogueServiceTest {
    ReferenceCatalogueService service=new ReferenceCatalogueService();
    ProductInfoMapper<ProductInfo,ProductInfoQuery> products=mock(ProductInfoMapper.class);
    ProductSkuMapper<ProductSku,ProductSkuQuery> skus=mock(ProductSkuMapper.class);
    ProductPropertyValueMapper<ProductPropertyValue,ProductPropertyValueQuery> values=mock(ProductPropertyValueMapper.class);
    ReferenceCatalogueMapper ledger=mock(ReferenceCatalogueMapper.class);
    @BeforeEach void setup(){
        org.springframework.test.util.ReflectionTestUtils.setField(service,"products",products);
        org.springframework.test.util.ReflectionTestUtils.setField(service,"skus",skus);
        org.springframework.test.util.ReflectionTestUtils.setField(service,"values",values);
        org.springframework.test.util.ReflectionTestUtils.setField(service,"ledger",ledger);
    }
    @AfterEach void close(){service.close();}
    @Test void fullBundledPublicSnapshotCanBeDecodedWithoutInventingSkuFacts(){
        var plan=service.preview();var rows=(List<Map<String,Object>>)plan.get("products");
        assertEquals(718,rows.size());assertEquals(9,((List<?>)plan.get("categories")).size());
        int expectedSkus=0;
        for(var row:rows){service.insertProduct(plan.get("planId").toString(),row);expectedSkus+=((List<?>)row.get("skuList")).size();}
        assertEquals(3701,expectedSkus);verify(products,times(718)).insert(any(ProductInfo.class));verify(skus,times(3701)).insert(any(ProductSku.class));
        verify(ledger,times(718)).bind(anyString(),anyString(),anyString(),anyString());
    }
    @Test void categoryTreeAndPropertyDefinitionsDecodeUsingExistingEntities(){
        var c=mock(SysCategoryMapper.class);var p=mock(SysProductPropertyMapper.class);
        org.springframework.test.util.ReflectionTestUtils.setField(service,"categories",c);
        org.springframework.test.util.ReflectionTestUtils.setField(service,"propertyDefinitions",p);
        for(var root:(List<Map<String,Object>>)service.preview().get("categories")){
            service.ensureCategory(root);for(var child:(List<Map<String,Object>>)root.get("children"))service.ensureCategory(child);
        }
        verify(c,atLeast(9)).insert(any(SysCategory.class));verify(p,atLeastOnce()).insert(any(SysProductProperty.class));
    }
    @Test void existingUnrelatedProductIsNeverOverwritten(){
        var plan=service.preview();var row=((List<Map<String,Object>>)plan.get("products")).get(0);
        var info=(Map<String,Object>)row.get("productInfo");when(products.selectByProductId(info.get("productId").toString())).thenReturn(new ProductInfo());
        assertThrows(BusinessException.class,()->service.insertProduct(plan.get("planId").toString(),row));
        verify(products,never()).insert(any());verifyNoInteractions(skus,values);
    }
    @Test void retrySkipsPreviouslyCommittedProductAndDoesNotAddStock(){
        var plan=service.preview();var row=((List<Map<String,Object>>)plan.get("products")).get(0);
        var info=(Map<String,Object>)row.get("productInfo");when(products.selectByProductId(info.get("productId").toString())).thenReturn(new ProductInfo());
        when(ledger.boundHash(anyString(),anyString())).thenReturn(row.get("sourceSha256").toString());
        service.insertProduct(plan.get("planId").toString(),row);verify(products,never()).insert(any());verifyNoInteractions(skus,values);
    }
    @Test void invalidPlanRejected(){assertThrows(IllegalArgumentException.class,()->ReferenceCatalogueService.validate(Map.of("planId","forged")));}
    @Test void serviceFailureCannotBecomeSuccess(){assertThrows(BusinessException.class,()->ReferenceCatalogueService.ok(null));}
}
