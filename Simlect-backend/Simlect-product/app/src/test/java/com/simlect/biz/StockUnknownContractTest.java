package com.simlect.biz;

import com.simlect.api.dto.SkuStockDTO;
import com.simlect.api.support.StockFeignSupport;
import com.simlect.api.support.FeignResponseSupport;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

@ExtendWith(MockitoExtension.class)
class StockUnknownContractTest {
    @Mock FeignResponseSupport feignResponseSupport;
    @InjectMocks StockFeignSupport support;
    @Test void missingStockNeverBecomesZero(){when(feignResponseSupport.call(any(),anyString())).thenReturn(new SkuStockDTO("p","s",null));assertThrows(RuntimeException.class,()->support.getAvailable("p","s"));}
    @Test void zeroStockRemainsZero(){when(feignResponseSupport.call(any(),anyString())).thenReturn(new SkuStockDTO("p","s",0));assertEquals(0,support.getAvailable("p","s"));}
}
