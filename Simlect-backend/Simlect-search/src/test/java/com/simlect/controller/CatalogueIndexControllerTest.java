package com.simlect.controller;
import com.simlect.component.EsSearchComponent;
import com.simlect.exception.BusinessException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
@ExtendWith(MockitoExtension.class) class CatalogueIndexControllerTest {
 @Mock EsSearchComponent es; @InjectMocks CatalogueIndexController controller;
 @Test void lexicalSyncDeduplicatesAndMakesNoEmbeddingCall(){var result=controller.sync(Map.of("productIds",List.of("ABOB0896KVCJY","ABOB0896KVCJY")));assertEquals(0,result.getData().get("embeddingRequests"));verify(es).saveIndex("ABOB0896KVCJY");verifyNoMoreInteractions(es);}
 @Test void malformedIdsRejectedBeforeIndexing(){assertThrows(BusinessException.class,()->controller.sync(Map.of("productIds",List.of("../index"))));verifyNoInteractions(es);}
 @Test void boundedBatch(){assertThrows(BusinessException.class,()->controller.sync(Map.of("productIds",Collections.nCopies(151,"ABOB0896KVCJY"))));verifyNoInteractions(es);}
}
