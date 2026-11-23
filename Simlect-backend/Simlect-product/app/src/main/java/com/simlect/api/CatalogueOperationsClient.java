package com.simlect.api;
import com.simlect.api.dto.SkuStockBatchChangeDTO;
import com.simlect.api.vo.StockChangeResultVO;
import com.simlect.entity.vo.ResponseVO;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.*;

@FeignClient(name="simlect-stock",contextId="catalogue-stock-setup")
public interface CatalogueOperationsClient {
    @PostMapping("/internal/stock/initializeCatalogue")
    ResponseVO<StockChangeResultVO> initialize(@RequestBody SkuStockBatchChangeDTO dto);
}
