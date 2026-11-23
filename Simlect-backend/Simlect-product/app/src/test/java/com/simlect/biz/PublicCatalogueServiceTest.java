package com.simlect.biz;
import com.simlect.exception.BusinessException;
import com.simlect.mappers.PublicCatalogueMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class PublicCatalogueServiceTest {
 @Mock PublicCatalogueMapper mapper;
 @InjectMocks PublicCatalogueService service;
 @Test void noRecordsIsNotAnException(){assertEquals(0L,service.list("","",1).get("totalCount"));}
 @Test void queryBoundsFailBeforeMapper(){assertThrows(BusinessException.class,()->service.list("","",0));verifyNoInteractions(mapper);}
 @Test void invalidPayloadCannotBeReportedAsSuccess(){when(mapper.list("","",0,20)).thenReturn(List.of(Map.of("payload","invalid")));assertThrows(BusinessException.class,()->service.list("","",1));}
 @Test void nonPublicRecordCannotLeakIntoPublicCatalogue(){when(mapper.list("","",0,20)).thenReturn(List.of(Map.of("payload","{\"sourceType\":\"LIVE_API\",\"purchasable\":false}")));assertThrows(BusinessException.class,()->service.list("","",1));}
 @Test void publicDataCannotBecomePurchasable(){when(mapper.list("","",0,20)).thenReturn(List.of(Map.of("payload","{\"sourceType\":\"PUBLIC_DATASET\",\"purchasable\":true}")));assertThrows(BusinessException.class,()->service.list("","",1));}
 @Test void unknownTradeFieldsRemainNull(){when(mapper.list("","",0,20)).thenReturn(List.of(Map.of("payload","{\"sourceType\":\"PUBLIC_DATASET\",\"purchasable\":false,\"currentPrice\":99,\"stock\":99,\"historicalPrice\":10,\"originalCurrency\":\"USD\"}")));var result=service.list("","",1);var row=(Map<?,?>)((List<?>)result.get("list")).get(0);assertNull(row.get("stock"));assertNull(row.get("currentPrice"));assertEquals(10,row.get("historicalPrice"));assertEquals("USD",row.get("originalCurrency"));}
 @Test void keywordCategoryAndPaginationStayBound(){service.list("cup","饮水杯",2);verify(mapper).list("cup","饮水杯",20,20);verify(mapper).count("cup","饮水杯");}
}
