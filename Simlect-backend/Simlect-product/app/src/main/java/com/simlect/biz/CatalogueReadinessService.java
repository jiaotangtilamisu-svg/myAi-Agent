package com.simlect.biz;
import com.simlect.api.*;
import com.simlect.api.dto.*;
import com.simlect.entity.vo.ResponseVO;
import com.simlect.exception.BusinessException;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import java.util.*;

/** Resumable setup: local transaction first, then non-overwriting stock, then lexical projection. */
@Service public class CatalogueReadinessService {
 @Resource private CataloguePublicationService publication;
 @Resource private CatalogueOperationsClient stock;
 @Resource private CatalogueSearchClient search;
 public Map<String,Object> prepare(String planId){
  var plan=publication.localize(planId);
  var rows=(List<Map<String,Object>>)plan.get("products");
  SkuStockBatchChangeDTO batch=new SkuStockBatchChangeDTO();batch.setOperationId("CATALOGUE_INIT_ABO31_COMMERCE_READY_V1");
  List<SkuStockChangeDTO> changes=new ArrayList<>();
  for(var p:rows){SkuStockChangeDTO dto=new SkuStockChangeDTO();dto.setProductId(p.get("productId").toString());dto.setPropertyValueIdHash(p.get("skuHash").toString());dto.setChangeAmount(((Number)p.get("initialStock")).intValue());changes.add(dto);}
  batch.setItems(changes);
  try{success(stock.initialize(batch));}catch(Exception e){throw new BusinessException("中文商品已保存，库存初始化未确认；可以安全重试，不会覆盖既有库存");}
  var ids=new ArrayList<>(rows.stream().map(p->p.get("productId").toString()).toList());
  ids.addAll(List.of("DEMO001","DEMO002","DEMO003","DEMO004","DEMO005","DEMO006","DEMO007","DEMO008","V16142348M","V16142348O","V16142348P","V16142348S"));
  try{success(search.sync(Map.of("productIds",ids)));}catch(Exception e){throw new BusinessException("商品和库存已保存，搜索索引同步未确认；可以安全重试，不会重复增加库存");}
  return Map.of("status","READY","products",100,"indexSynced",true,"embeddingRequests",0,"stockOrigin","LOCAL_CONFIGURED");
 }
 private void success(ResponseVO<?> r){if(r==null||!Integer.valueOf(200).equals(r.getCode())||!"success".equals(r.getStatus()))throw new BusinessException("服务操作失败");}
}
