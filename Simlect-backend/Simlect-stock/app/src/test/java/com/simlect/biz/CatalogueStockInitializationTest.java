package com.simlect.biz;
import com.simlect.api.dto.*;
import com.simlect.exception.BusinessException;
import com.simlect.mappers.SkuStockMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
@ExtendWith(MockitoExtension.class) class CatalogueStockInitializationTest {
 @Mock SkuStockMapper mapper; @InjectMocks SkuStockService service;
 SkuStockBatchChangeDTO batch(){var b=new SkuStockBatchChangeDTO();b.setOperationId("CATALOGUE_INIT_TEST");var r=new SkuStockChangeDTO();r.setProductId("ABOB0896KVCJY");r.setPropertyValueIdHash("8479ccd48da12bf8771c8538c16df615");r.setChangeAmount(100);b.setItems(List.of(r));return b;}
 @Test void createsOnlyMissingStock(){when(mapper.insertChangeOperation(anyString())).thenReturn(1);when(mapper.initializeIfAbsent(anyString(),anyString(),eq(100))).thenReturn(1);assertEquals(1,service.initializeCatalogue(batch()));verify(mapper,never()).upsert(anyString(),anyString(),anyInt());verify(mapper,never()).changeStock(anyString(),anyString(),anyInt());}
 @Test void existingStockIncludingZeroIsNotOverwritten(){when(mapper.insertChangeOperation(anyString())).thenReturn(1);assertEquals(0,service.initializeCatalogue(batch()));verify(mapper).initializeIfAbsent(anyString(),anyString(),eq(100));verify(mapper,never()).upsert(anyString(),anyString(),anyInt());}
 @Test void retryDoesNotIncreaseQuantity(){when(mapper.selectChangeOperationResult(anyString())).thenReturn(1);assertEquals(1,service.initializeCatalogue(batch()));verify(mapper,never()).initializeIfAbsent(anyString(),anyString(),anyInt());}
 @Test void inProgressOperationDoesNotPretendSuccess(){when(mapper.selectChangeOperationResult(anyString())).thenReturn(null);assertThrows(BusinessException.class,()->service.initializeCatalogue(batch()));verify(mapper,never()).initializeIfAbsent(anyString(),anyString(),anyInt());}
 @Test void ordinaryProductsCannotUseThisSetup(){var b=batch();b.getItems().get(0).setProductId("DEMO001");assertThrows(BusinessException.class,()->service.initializeCatalogue(b));verifyNoInteractions(mapper);}
 @Test void negativeInitialQuantityRejected(){var b=batch();b.getItems().get(0).setChangeAmount(-1);assertThrows(BusinessException.class,()->service.initializeCatalogue(b));verifyNoInteractions(mapper);}
 @Test void duplicateSkuRejected(){var b=batch();b.setItems(List.of(b.getItems().get(0),b.getItems().get(0)));assertThrows(BusinessException.class,()->service.initializeCatalogue(b));verifyNoInteractions(mapper);}
}
