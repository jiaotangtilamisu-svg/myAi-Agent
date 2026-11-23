package com.simlect.biz;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.core.type.TypeReference;
import com.simlect.api.*;
import com.simlect.api.dto.*;
import com.simlect.component.*;
import com.simlect.entity.po.*;
import com.simlect.entity.query.*;
import com.simlect.entity.vo.ResponseVO;
import com.simlect.exception.BusinessException;
import com.simlect.mappers.*;
import jakarta.annotation.Resource;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import java.util.*;
import java.util.concurrent.*;
import java.nio.file.*;
import java.security.MessageDigest;

/** One explicitly approved, resumable local import. No vectorization/payment/MQ. */
@Service
public class ReferenceCatalogueService {
    @Resource private ProductInfoMapper<ProductInfo,ProductInfoQuery> products;
    @Resource private ProductSkuMapper<ProductSku,ProductSkuQuery> skus;
    @Resource private ProductPropertyValueMapper<ProductPropertyValue,ProductPropertyValueQuery> values;
    @Resource private SysCategoryMapper<SysCategory,SysCategoryQuery> categories;
    @Resource private SysProductPropertyMapper<SysProductProperty,SysProductPropertyQuery> propertyDefinitions;
    @Resource private ReferenceCatalogueMapper ledger;
    @Resource private PlatformTransactionManager transactionManager;
    @Resource private CatalogueOperationsClient stock;
    @Resource private CatalogueSearchClient search;
    @Resource private ProductBloomFilterComponent bloom;
    @Resource private RedisComponent redis;
    private final ObjectMapper json=new ObjectMapper();
    private final ExecutorService worker=Executors.newSingleThreadExecutor(r -> new Thread(r,"reference-catalogue-import"));
    private volatile Map<String,Object> state=Map.of("status","IDLE","processed",0);
    @PreDestroy void close(){worker.shutdownNow();}

    public Map<String,Object> preview(){
        try(var in=getClass().getResourceAsStream("/catalogue/simlect-reference.json")){
            if(in==null)throw new IllegalStateException();
            var plan=json.readValue(in,new TypeReference<Map<String,Object>>(){});
            validate(plan); return plan;
        }catch(Exception e){throw new BusinessException("参考站商品资料尚未准备完成或校验失败");}
    }
    static void validate(Map<String,Object> p){
        if(!String.valueOf(p.get("planId")).matches("REF31_[a-f0-9]{32}"))throw new IllegalArgumentException();
        var rows=(List<Map<String,Object>>)p.get("products");
        if(rows==null||rows.isEmpty()||rows.size()>800)throw new IllegalArgumentException();
        Set<String> ids=new HashSet<>();
        for(var row:rows){
            var info=(Map<String,Object>)row.get("productInfo");
            String id=String.valueOf(info.get("productId"));
            if(!id.matches("[0-9]{15}")||!ids.add(id)||!String.valueOf(row.get("sourceSha256")).matches("[a-f0-9]{64}"))throw new IllegalArgumentException();
            if(!String.valueOf(info.get("cover")).startsWith("catalogue/reference/"))throw new IllegalArgumentException();
            var list=(List<Map<String,Object>>)row.get("skuList");
            if(list==null||list.isEmpty()||list.size()>100)throw new IllegalArgumentException();
            for(var sku:list)if(!id.equals(sku.get("productId"))||!String.valueOf(sku.get("propertyValueIdHash")).matches("[a-f0-9]{32}"))throw new IllegalArgumentException();
        }
    }
    public Map<String,Object> status(){return state;}
    public synchronized Map<String,Object> start(String planId){
        if("RUNNING".equals(state.get("status")))throw new BusinessException("参考商品正在导入，请勿重复提交");
        var plan=preview();
        if(!planId.equals(plan.get("planId")))throw new BusinessException("参考商品计划已变化，请重新预览");
        try{
            String hash=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(Path.of(plan.get("backupFile").toString()))));
            if(!hash.equals(plan.get("backupSha256")))throw new IllegalStateException();
        }catch(Exception e){throw new BusinessException("备份缺失或校验失败，未导入商品");}
        state=Map.of("status","RUNNING","processed",0,"total",((List<?>)plan.get("products")).size(),"planId",planId,"phase","QUEUED");
        worker.submit(() -> execute(plan));
        return state;
    }
    void execute(Map<String,Object> plan){
        String batch=plan.get("planId").toString();
        var rows=(List<Map<String,Object>>)plan.get("products");
        int done=0;String phase="CATEGORIES";
        var tx=new TransactionTemplate(transactionManager);
        try{
            ledger.claim(batch);
            tx.executeWithoutResult(s -> {ledger.lock(batch);for(var root:(List<Map<String,Object>>)plan.get("categories")){
                ensureCategory(root);for(var child:(List<Map<String,Object>>)root.get("children"))ensureCategory(child);
            }});
            redis.saveCategory2Redis(categories.selectList(new SysCategoryQuery()));
            for(int offset=0;offset<rows.size();offset+=25){
                var chunk=rows.subList(offset,Math.min(offset+25,rows.size()));
                phase="PRODUCTS";
                tx.executeWithoutResult(s -> {ledger.lock(batch);for(var row:chunk)insertProduct(batch,row);});
                phase="STOCK";List<SkuStockChangeDTO> changes=new ArrayList<>();
                for(var row:chunk)for(var source:(List<Map<String,Object>>)row.get("skuList")){
                    if(source.get("stock")==null)continue; // Unknown is never a zero.
                    var change=new SkuStockChangeDTO();change.setProductId(source.get("productId").toString());
                    change.setPropertyValueIdHash(source.get("propertyValueIdHash").toString());change.setChangeAmount(((Number)source.get("stock")).intValue());changes.add(change);
                }
                for(int i=0;i<changes.size();i+=200){var b=new SkuStockBatchChangeDTO();
                    b.setOperationId("CATALOGUE_INIT_"+batch+"_"+offset+"_"+i);b.setItems(changes.subList(i,Math.min(i+200,changes.size())));ok(stock.initialize(b));}
                phase="SEARCH";var ids=chunk.stream().map(r -> ((Map<?,?>)r.get("productInfo")).get("productId").toString()).toList();
                ids.forEach(bloom::add);ok(search.sync(Map.of("productIds",ids)));done+=chunk.size();
                state=Map.of("status","RUNNING","processed",done,"total",rows.size(),"planId",batch,"phase",phase);
                ledger.progress(batch,"PROCESSING",json.writeValueAsString(state));
            }
            // Only after all new products, stock and indexes are ready, hide the old
            // catalogue from sale. No product/SKU/stock/order row is deleted.
            phase="FINISHING";
            ProductInfoQuery oldQuery=new ProductInfoQuery();oldQuery.setProductIdFuzzy("ABO");
            var old=products.selectList(oldQuery);
            tx.executeWithoutResult(s -> {ledger.lock(batch);for(var p:old){if(!p.getProductId().matches("ABO[A-Z0-9]{10}"))continue;
                ProductInfo u=new ProductInfo();u.setStatus(0);u.setCommendType(0);products.updateByProductId(u,p.getProductId());}});
            if(!old.isEmpty())ok(search.sync(Map.of("productIds",old.stream().map(ProductInfo::getProductId).toList())));
            state=Map.of("status","COMPLETE","processed",done,"total",rows.size(),"planId",batch,"phase","COMPLETE");
            ledger.progress(batch,"COMMITTED",json.writeValueAsString(state));
        }catch(Exception e){
            state=Map.of("status","FAILED","processed",done,"total",rows.size(),"planId",batch,"phase",phase,"error","该阶段未完成；已保存部分不会回滚为成功，可在核对后安全续传");
            try{ledger.progress(batch,"FAILED",json.writeValueAsString(state));}catch(Exception ignored){}
            org.slf4j.LoggerFactory.getLogger(getClass()).error("Reference catalogue stopped phase={} processed={} errorType={}",phase,done,e.getClass().getSimpleName());
        }
    }
    void ensureCategory(Map<String,Object> source){
        var c=json.convertValue(source,SysCategory.class); // Convert manually: child property definitions have a separate table.
        var old=categories.selectByCategoryId(c.getCategoryId());
        if(old==null){c.setChildren(null);c.setproductPropertyList(null);categories.insert(c);}
        else if(!Objects.equals(old.getCategoryName(),c.getCategoryName())||!Objects.equals(old.getpCategoryId(),c.getpCategoryId()))throw new BusinessException("分类编号冲突，未覆盖");
        for(var p:(List<Map<String,Object>>)source.get("productPropertyList")){
            var def=json.convertValue(p,SysProductProperty.class);var before=propertyDefinitions.selectByPropertyId(def.getPropertyId());
            if(before==null)propertyDefinitions.insert(def);
            else if(!Objects.equals(before.getPropertyName(),def.getPropertyName())||!Objects.equals(before.getCategoryId(),def.getCategoryId()))throw new BusinessException("规格定义冲突，未覆盖");
        }
    }
    void insertProduct(String batch,Map<String,Object> row){
        var p=json.convertValue(row.get("productInfo"),ProductInfo.class);
        String id=p.getProductId(),hash=row.get("sourceSha256").toString();
        if(products.selectByProductId(id)!=null){if(!hash.equals(ledger.boundHash(batch,id)))throw new BusinessException("商品编号冲突，未覆盖");return;}
        products.insert(p);
        for(var source:(List<Map<String,Object>>)row.get("skuList")){
            var s=new ProductSku();s.setProductId(id);s.setPropertyValueIdHash(source.get("propertyValueIdHash").toString());
            s.setPropertyValueIds(String.valueOf(source.get("propertyValueIds")));s.setSort(source.get("sort")==null?0:((Number)source.get("sort")).intValue());
            if(source.get("price")!=null)s.setPrice(new java.math.BigDecimal(source.get("price").toString()));skus.insert(s);
        }
        for(var prop:(List<Map<String,Object>>)row.get("productPropertyList"))for(var val:(List<Map<String,Object>>)prop.get("propertyValues")){
            var v=json.convertValue(val,ProductPropertyValue.class);v.setProductId(id);v.setPropertyId(prop.get("propertyId").toString());v.setPropertyName(prop.get("propertyName").toString());
            v.setPropertySort(prop.get("propertySort")==null?0:((Number)prop.get("propertySort")).intValue());v.setCoverType(prop.get("coverType")==null?0:((Number)prop.get("coverType")).intValue());values.insert(v);
        }
        try{ledger.bind(HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest((batch+":"+id).getBytes(java.nio.charset.StandardCharsets.UTF_8))),id,batch,hash);}
        catch(java.security.NoSuchAlgorithmException e){throw new IllegalStateException(e);}
    }
    static void ok(ResponseVO<?> r){if(r==null||!Integer.valueOf(200).equals(r.getCode())||!"success".equals(r.getStatus()))throw new BusinessException("依赖服务未确认成功");}
}
