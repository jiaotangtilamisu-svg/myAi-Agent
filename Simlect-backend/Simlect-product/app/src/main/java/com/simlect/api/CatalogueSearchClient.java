package com.simlect.api;
import com.simlect.entity.vo.ResponseVO;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.*;
import java.util.*;

@FeignClient(name="simlect-search",contextId="catalogue-lexical-index",configuration=CatalogueSearchClient.Timeouts.class)
public interface CatalogueSearchClient {
    class Timeouts {
        @org.springframework.context.annotation.Bean public feign.Request.Options catalogueIndexTimeout(){return new feign.Request.Options(5000,java.util.concurrent.TimeUnit.MILLISECONDS,60000,java.util.concurrent.TimeUnit.MILLISECONDS,true);}
    }
    @PostMapping("/internal/search/syncCatalogue")
    ResponseVO<Map<String,Object>> sync(@RequestBody Map<String,List<String>> request);
}
