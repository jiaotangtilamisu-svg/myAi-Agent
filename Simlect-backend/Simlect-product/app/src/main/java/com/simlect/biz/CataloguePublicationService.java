package com.simlect.biz;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.simlect.component.ProductBloomFilterComponent;
import com.simlect.component.RedisComponent;
import com.simlect.entity.po.*;
import com.simlect.entity.query.*;
import com.simlect.exception.BusinessException;
import com.simlect.mappers.*;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import java.util.*;
import java.math.BigDecimal;

/** Explicit administrator publication of a bundled, reviewed public catalogue.
 * Reuses product tables. Never publishes MQ vectorization jobs or creates stock.
 */
@Service
public class CataloguePublicationService {
    @Resource private ProductInfoMapper<ProductInfo,ProductInfoQuery> products;
    @Resource private ProductSkuMapper<ProductSku,ProductSkuQuery> skus;
    @Resource private ProductPropertyValueMapper<ProductPropertyValue,ProductPropertyValueQuery> properties;
    @Resource private SysCategoryMapper<SysCategory,SysCategoryQuery> categories;
    @Resource private PublicCatalogueMapper provenance;
    @Resource private ProductBloomFilterComponent bloom;
    @Resource private RedisComponent redis;
    private final ObjectMapper json=new ObjectMapper();

    public Map<String,Object> preview() {
        try(var in=getClass().getResourceAsStream("/catalogue/abo-storefront.json")) {
            if(in==null)throw new IllegalStateException();
            Map<String,Object> plan=json.readValue(in,new com.fasterxml.jackson.core.type.TypeReference<Map<String,Object>>(){});
            validate(plan); return plan;
        }catch(Exception e){throw new BusinessException("ABO商品发布资料缺失或校验失败，未修改商品");}
    }

    public Map<String,Object> readinessPreview(){
        try(var in=getClass().getResourceAsStream("/catalogue/abo-commerce-ready.json")){
            var p=json.readValue(in,new com.fasterxml.jackson.core.type.TypeReference<Map<String,Object>>(){});
            if(!"ABO31_COMMERCE_READY_V1".equals(p.get("planId"))||((List<?>)p.get("products")).size()!=100)throw new IllegalArgumentException();
            return p;
        }catch(Exception e){throw new BusinessException("商城中文化和库存计划未就绪");}
    }

    @Transactional(rollbackFor=Exception.class)
    public Map<String,Object> localize(String planId){
        if(!"ABO31_COMMERCE_READY_V1".equals(planId)||!"COMMITTED".equals(provenance.lockAboBatch()))throw new BusinessException("商城准备计划不匹配");
        var plan=readinessPreview();verifyBackup(plan);
        for(var row:(List<Map<String,Object>>)plan.get("products")){
            String id=row.get("productId").toString();
            if(!id.matches("ABO[A-Z0-9]{10}")||products.selectByProductId(id)==null)throw new BusinessException("目标商品不存在");
            ProductInfo update=new ProductInfo();update.setProductName(row.get("productName").toString());update.setProductDesc(row.get("productDesc").toString());
            products.updateByProductId(update,id);
            provenance.updateLocalSpecification(id,row.get("specification").toString());
            if(provenance.markLocalCatalogue(id)!=1)throw new BusinessException("商品目录确认失败");
        }
        return plan;
    }

    static void validate(Map<String,Object> plan) {
        if(!"ABO31_STOREFRONT_V1".equals(plan.get("planId"))||!"CC-BY-4.0".equals(plan.get("license")))throw new IllegalArgumentException();
        List<?> rows=(List<?>)plan.get("products");
        if(rows==null||rows.size()!=100)throw new IllegalArgumentException();
        Set<String> ids=new HashSet<>();
        for(Object item:rows){
            Map<?,?> p=(Map<?,?>)item;
            String id=String.valueOf(p.get("productId")),source=String.valueOf(p.get("sourceId"));
            if(!source.matches("[A-Z0-9]{10}")||!id.equals("ABO"+source)||!ids.add(id))throw new IllegalArgumentException();
            if(!String.valueOf(p.get("cover")).matches("catalogue/abo/"+source+"\\.(jpg|png)"))throw new IllegalArgumentException();
            if(!Set.of("A311","A312","A313").contains(p.get("categoryId")))throw new IllegalArgumentException();
            BigDecimal price=new BigDecimal(p.get("price").toString());
            if(price.signum()<=0||price.compareTo(new BigDecimal("1000"))>0||price.scale()>2)throw new IllegalArgumentException();
            String name=String.valueOf(p.get("productName"));if(name.isBlank()||name.length()>200)throw new IllegalArgumentException();
        }
    }

    @Transactional(rollbackFor=Exception.class)
    public Map<String,Object> publish(String planId) {
        if(!"ABO31_STOREFRONT_V1".equals(planId))throw new BusinessException("发布计划不匹配");
        // Lock the existing committed source batch: simultaneous/repeated submissions cannot duplicate products.
        if(!"COMMITTED".equals(provenance.lockAboBatch()))throw new BusinessException("ABO来源批次未就绪");
        Map<String,Object> plan=preview();
        List<Map<String,Object>> rows=(List<Map<String,Object>>)plan.get("products");
        long existing=rows.stream().filter(p->products.selectByProductId(p.get("productId").toString())!=null).count();
        if(existing==100){
            for(var p:rows){ProductInfo stored=products.selectByProductId(p.get("productId").toString());
                if(!stored.getCover().equals(p.get("cover"))||stored.getMinPrice().compareTo(new BigDecimal(p.get("price").toString()))!=0)
                    throw new BusinessException("既有ABO商品已变更，不覆盖");}
            reconcile(rows);return Map.of("status","ALREADY_PUBLISHED","products",100);
        }
        if(existing!=0)throw new BusinessException("发现部分既有ABO商品，请人工核对，未覆盖");
        verifyBackup(plan);
        List<ProductInfo> infos=new ArrayList<>();List<ProductSku> skuRows=new ArrayList<>();List<ProductPropertyValue> values=new ArrayList<>();
        for(Map<String,Object> p:rows){
            ProductInfo info=new ProductInfo();String id=p.get("productId").toString();
            info.setProductId(id);info.setProductName(p.get("productName").toString());info.setProductDesc(p.get("productDesc").toString());
            info.setCover(p.get("cover").toString());info.setCategoryId(p.get("categoryId").toString());info.setpCategoryId("A310");
            info.setMinPrice(new BigDecimal(p.get("price").toString()));info.setMaxPrice(info.getMinPrice());
            info.setStatus(1);info.setCommendType(((Number)p.get("commendType")).intValue());info.setTotalSale(0);info.setCreateTime(new Date());infos.add(info);
            ProductSku sku=new ProductSku();sku.setProductId(id);sku.setPropertyValueIdHash(p.get("skuHash").toString());sku.setPropertyValueIds("ABO_STD");sku.setPrice(info.getMinPrice());sku.setSort(0);skuRows.add(sku);
            ProductPropertyValue v=new ProductPropertyValue();v.setProductId(id);v.setPropertyId("ABO31SPEC");v.setPropertyName("规格");v.setPropertyValueId("ABO_STD");v.setPropertyValue(p.get("specification").toString());v.setPropertySort(1);v.setCoverType(0);v.setSort(0);values.add(v);
        }
        String[] categoryIds={"A310","A311","A312","A313"},names={"精选商品","手机壳","饮水杯","耳机"};
        for(int i=0;i<categoryIds.length;i++){
            if(categories.selectByCategoryId(categoryIds[i])!=null)throw new BusinessException("商品分类ID冲突，未覆盖");
            SysCategory c=new SysCategory();c.setCategoryId(categoryIds[i]);c.setCategoryName(names[i]);c.setpCategoryId(i==0?"0":"A310");c.setSort(i);categories.insert(c);
        }
        products.insertBatch(infos);skus.insertBatch(skuRows);properties.insertBatch(values);
        for(Map<String,Object> p:rows)if(provenance.bindAboProduct(p.get("sourceId").toString(),p.get("productId").toString())!=1)throw new BusinessException("商品来源绑定失败，整批回滚");
        // Preserve all original rows and order snapshots; only remove old demo/test entries from sale.
        for(String id:List.of("DEMO001","DEMO002","DEMO003","DEMO004","DEMO005","DEMO006","DEMO007","DEMO008","V16142348M","V16142348O","V16142348P","V16142348S")){
            ProductInfo old=products.selectByProductId(id);if(old==null)continue;
            ProductInfo change=new ProductInfo();change.setStatus(0);change.setCommendType(0);products.updateByProductId(change,id);
        }
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization(){@Override public void afterCommit(){
            reconcile(rows);
        }});
        return Map.of("status","PUBLISHED","products",100,"stockCreated",0,"embeddingRequests",0,"planId",planId);
    }

    void verifyBackup(Map<String,Object> plan){
        try{
            var path=java.nio.file.Path.of(plan.get("backupFile").toString());
            String actual=java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(java.nio.file.Files.readAllBytes(path)));
            if(!actual.equals(plan.get("backupSha256")))throw new IllegalStateException();
        }catch(Exception e){throw new BusinessException("数据库备份缺失或哈希不符，未发布商品");}
    }

    private void reconcile(List<Map<String,Object>> rows){
        rows.forEach(p->bloom.add(p.get("productId").toString()));
        redis.saveCategory2Redis(categories.selectList(new SysCategoryQuery()));
    }
}
