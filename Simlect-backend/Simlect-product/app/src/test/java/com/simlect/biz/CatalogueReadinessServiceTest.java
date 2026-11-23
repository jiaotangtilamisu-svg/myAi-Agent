package com.simlect.biz;
import com.simlect.api.*;
import com.simlect.api.vo.StockChangeResultVO;
import com.simlect.entity.vo.ResponseVO;
import com.simlect.exception.BusinessException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
@ExtendWith(MockitoExtension.class) class CatalogueReadinessServiceTest {
 @Mock CataloguePublicationService publication; @Mock CatalogueOperationsClient stock; @Mock CatalogueSearchClient search; @InjectMocks CatalogueReadinessService service;
 Map<String,Object> plan(){return Map.of("products",List.of(Map.of("productId","ABOB0896KVCJY","skuHash","8479ccd48da12bf8771c8538c16df615","initialStock",50)));}
 <T> ResponseVO<T> ok(T data){var r=new ResponseVO<T>();r.setCode(200);r.setStatus("success");r.setData(data);return r;}
 @Test void sourceAndStockAndLexicalIndexMustAllSucceed(){when(publication.localize("p")).thenReturn(plan());when(stock.initialize(any())).thenReturn(ok(new StockChangeResultVO(1)));when(search.sync(any())).thenReturn(ok(Map.of("indexed",1)));assertEquals("READY",service.prepare("p").get("status"));var order=inOrder(publication,stock,search);order.verify(publication).localize("p");order.verify(stock).initialize(any());order.verify(search).sync(any());}
 @Test void stockFailureIsExplicitAndStopsIndex(){when(publication.localize("p")).thenReturn(plan());assertThrows(BusinessException.class,()->service.prepare("p"));verifyNoInteractions(search);}
 @Test void indexFailureCannotReturnSuccess(){when(publication.localize("p")).thenReturn(plan());when(stock.initialize(any())).thenReturn(ok(new StockChangeResultVO(1)));assertThrows(BusinessException.class,()->service.prepare("p"));}
}
