package com.simlect.controller;
import com.simlect.component.EsSearchComponent;
import com.simlect.entity.vo.ResponseVO;
import com.simlect.exception.BusinessException;
import jakarta.annotation.Resource;
import org.springframework.web.bind.annotation.*;
import java.util.*;

/** Internal-token protected lexical projection only; no MQ/vector/model calls. */
@RestController @RequestMapping("/internal/search")
public class CatalogueIndexController extends ABaseController {
    @Resource private EsSearchComponent es;
    @PostMapping("/syncCatalogue")
    public ResponseVO<Map<String,Object>> sync(@RequestBody Map<String,List<String>> request){
        List<String> ids=request==null?null:request.get("productIds");
        if(ids==null||ids.isEmpty()||ids.size()>150||ids.stream().anyMatch(i->i==null||!i.matches("[A-Za-z0-9_-]{1,15}")))throw new BusinessException("商品索引参数错误");
        for(String id:ids.stream().distinct().toList())es.saveIndex(id);
        return getSuccessResponseVO(Map.of("indexed",ids.stream().distinct().count(),"embeddingRequests",0));
    }
}
