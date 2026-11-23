package com.simlect.biz;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.simlect.exception.BusinessException;
import com.simlect.mappers.PublicCatalogueMapper;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import java.util.*;

@Service
public class PublicCatalogueService {
    @Resource private PublicCatalogueMapper mapper;
    private final ObjectMapper json=new ObjectMapper();
    public Map<String,Object> list(String keyword,String category,int page) {
        if(keyword==null)keyword="";if(category==null)category="";
        if(page<1||page>10000||keyword.length()>100||category.length()>100)throw new BusinessException("查询参数错误");
        List<Map<String,Object>> rows=new ArrayList<>();
        for(var r:mapper.list(keyword,category,(page-1)*20,20)) {
            try {
                Map<String,Object> payload=json.readValue((String)r.get("payload"),new com.fasterxml.jackson.core.type.TypeReference<Map<String,Object>>(){});
                if(!"PUBLIC_DATASET".equals(payload.get("sourceType"))||!Boolean.FALSE.equals(payload.get("purchasable")))throw new IllegalArgumentException();
                // Fail closed on trade fields even if an imported payload is malformed.
                payload.put("purchasable",false);payload.put("currentPrice",null);payload.put("stock",null);payload.put("stockStatus","UNKNOWN");payload.put("skus",null);
                rows.add(payload);
            } catch(Exception e) {throw new BusinessException("公开资料读取失败，请检查导入记录");}
        }
        return Map.of("list",rows,"totalCount",mapper.count(keyword,category),"pageNo",page,"pageSize",20,"purchasable",false);
    }
    public List<Map<String,Object>> batches(){return mapper.batches();}
}
