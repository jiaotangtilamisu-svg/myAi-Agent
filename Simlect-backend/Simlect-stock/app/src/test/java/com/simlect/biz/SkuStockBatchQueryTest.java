package com.simlect.biz;

import com.simlect.api.dto.*;
import com.simlect.domain.SkuStock;
import com.simlect.mappers.SkuStockMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class SkuStockBatchQueryTest {
    @Mock SkuStockMapper mapper;
    @InjectMocks SkuStockService service;
    @Test void batchReturnsOnlyExistingRowsAndPreservesZero() {
        SkuStockBatchQueryDTO d=new SkuStockBatchQueryDTO();d.setItems(List.of(new SkuStockQueryDTO("P1","h1"),new SkuStockQueryDTO("P1","h2")));
        SkuStock row=new SkuStock();row.setProductId("P1");row.setPropertyValueIdHash("h1");row.setStock(0);
        when(mapper.selectBatch(d.getItems())).thenReturn(List.of(row));
        var result=service.queryBatch(d);assertEquals(1,result.size());assertEquals(0,result.get(0).getStock());
        verify(mapper).selectBatch(d.getItems());verifyNoMoreInteractions(mapper);
    }
    @Test void rejectsUnboundedOrEmptyQuery() {
        assertThrows(RuntimeException.class,()->service.queryBatch(new SkuStockBatchQueryDTO()));verifyNoInteractions(mapper);
    }
}
