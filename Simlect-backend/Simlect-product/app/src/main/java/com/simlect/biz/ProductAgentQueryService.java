package com.simlect.biz;

import com.simlect.api.StockFeignClient;
import com.simlect.api.dto.SkuStockBatchQueryDTO;
import com.simlect.api.dto.SkuStockDTO;
import com.simlect.api.dto.SkuStockQueryDTO;
import com.simlect.entity.po.*;
import com.simlect.entity.query.*;
import com.simlect.entity.vo.ResponseVO;
import com.simlect.exception.BusinessException;
import com.simlect.mappers.*;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import java.time.Instant;
import java.util.*;

/** Agent-only read aggregation. Existing shopping and stock mutation contracts are unchanged. */
@Service
public class ProductAgentQueryService {
    @Resource private ProductInfoMapper<ProductInfo, ProductInfoQuery> productInfoMapper;
    @Resource private ProductSkuMapper<ProductSku, ProductSkuQuery> productSkuMapper;
    @Resource private ProductPropertyValueMapper<ProductPropertyValue, ProductPropertyValueQuery> productPropertyValueMapper;
    @Resource private StockFeignClient stockFeignClient;
    @Resource private SysCategoryMapper<SysCategory, SysCategoryQuery> sysCategoryMapper;
    @Resource private PublicCatalogueMapper publicCatalogueMapper;

    public Map<String, Object> queryBatch(List<String> productIds) {
        if (productIds == null || productIds.size() > 50 || productIds.stream().anyMatch(i -> i == null || i.isBlank()))
            throw new BusinessException("商品查询参数不合法");
        List<String> ids = productIds.stream().distinct().toList();
        Map<String, Object> result = new LinkedHashMap<>();
        String observed = Instant.now().toString();
        result.put("schemaVersion", 2); result.put("queryTime", observed);
        result.put("queryStatus", "SUCCESS");
        if (ids.isEmpty()) { result.put("products", List.of()); return result; }
        ProductInfoQuery pq = new ProductInfoQuery(); pq.setProductIdList(ids);
        ProductSkuQuery sq = new ProductSkuQuery(); sq.setProductIdList(ids); sq.setOrderBy("sort asc");
        ProductPropertyValueQuery vq = new ProductPropertyValueQuery(); vq.setProductIdList(ids);
        List<ProductInfo> products = productInfoMapper.selectList(pq);
        Map<String,Map<String,Object>> bindings=new HashMap<>();
        if(publicCatalogueMapper!=null){var bound=publicCatalogueMapper.localBindings(ids);if(bound!=null)for(var row:bound)bindings.put(row.get("productId").toString(),row);}
        List<ProductSku> skus = productSkuMapper.selectList(sq);
        List<ProductPropertyValue> values = productPropertyValueMapper.selectList(vq);
        if (products == null || skus == null || values == null) throw new BusinessException("商品查询响应异常");
        List<String> categoryIds=products.stream().flatMap(p->java.util.stream.Stream.of(p.getCategoryId(),p.getpCategoryId()))
                .filter(Objects::nonNull).filter(s->!s.isBlank()).distinct().toList();
        Map<String,String> categoryNames=new HashMap<>();
        if(!categoryIds.isEmpty()) {
            List<Map<String,Object>> names=sysCategoryMapper.selectAgentNames(categoryIds);
            if(names!=null)for(Map<String,Object> n:names)if(n.get("categoryId")!=null&&n.get("categoryName")!=null)
                categoryNames.put(n.get("categoryId").toString(),n.get("categoryName").toString());
        }
        Map<String, SkuStockDTO> stocks = new HashMap<>();
        Set<String> unavailable = new HashSet<>();
        // One RPC/SQL per bounded batch, never one request per SKU.
        List<SkuStockQueryDTO> keys = skus.stream().map(s -> new SkuStockQueryDTO(s.getProductId(), s.getPropertyValueIdHash())).toList();
        for (int start = 0; start < keys.size(); start += 200) {
            List<SkuStockQueryDTO> chunk = keys.subList(start, Math.min(start + 200, keys.size()));
            try {
                SkuStockBatchQueryDTO request = new SkuStockBatchQueryDTO(); request.setItems(chunk);
                ResponseVO<List<SkuStockDTO>> response = stockFeignClient.queryBatch(request);
                if (response == null || !Integer.valueOf(200).equals(response.getCode())
                        || !"success".equals(response.getStatus()) || response.getData() == null)
                    throw new IllegalStateException("Invalid stock response");
                Set<String> requested = new HashSet<>();
                chunk.forEach(k -> requested.add(key(k.getProductId(), k.getPropertyValueIdHash())));
                Map<String, SkuStockDTO> validated = new HashMap<>();
                for (SkuStockDTO row : response.getData()) {
                    if (row == null) throw new IllegalStateException("Invalid stock row");
                    String k = key(row.getProductId(), row.getPropertyValueIdHash());
                    if (!requested.contains(k) || validated.put(k, row) != null)
                        throw new IllegalStateException("Mismatched stock keys");
                }
                stocks.putAll(validated);
            } catch (Exception e) {
                chunk.forEach(k -> unavailable.add(key(k.getProductId(), k.getPropertyValueIdHash())));
            }
        }
        List<Map<String, Object>> out = new ArrayList<>();
        for (String id : ids) {
            ProductInfo p = products.stream().filter(x -> id.equals(x.getProductId())).findFirst().orElse(null);
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("productId", id); item.put("productObservedAt", observed);
            if (p == null) { item.put("queryStatus", "NOT_FOUND"); item.put("productStatus", "NOT_FOUND"); out.add(item); continue; }
            item.put("queryStatus", "SUCCESS"); item.put("productName", p.getProductName());
            item.put("status", p.getStatus());
            String state = Integer.valueOf(1).equals(p.getStatus()) ? "ON_SALE" : Integer.valueOf(0).equals(p.getStatus()) ? "OFF_SHELF" : Integer.valueOf(-1).equals(p.getStatus()) ? "DELETED" : "UNKNOWN";
            item.put("productStatus", state); item.put("minPrice", price(p.getMinPrice())); item.put("maxPrice", price(p.getMaxPrice()));
            if(bindings.containsKey(id)){
                var b=bindings.get(id);
                item.put("dataProvenance",Map.of("sourceType",b.getOrDefault("sourceType","PUBLIC_DATASET"),"sourceName",b.getOrDefault("sourceName","本商城商品目录"),"sourceRecordId",b.get("sourceId"),"batchId",b.get("batchId"),"catalogueStatus","LOCAL_STORE","currency","CNY","fieldSources",Map.of("name","MANUAL","price","MANUAL","sku","MANUAL","stock","MANUAL")));
            }
            item.put("priceStatus", price(p.getMinPrice()) == null || price(p.getMaxPrice()) == null ? "UNKNOWN" : "KNOWN");
            item.put("cover", p.getCover()); item.put("categoryId", p.getCategoryId());
            item.put("categoryName",categoryNames.get(p.getCategoryId()));
            item.put("parentCategoryName",categoryNames.get(p.getpCategoryId()));
            item.put("totalSale", p.getTotalSale()); item.put("productDesc", p.getProductDesc()); item.put("description", p.getProductDesc());
            List<ProductPropertyValue> props = values.stream().filter(v -> id.equals(v.getProductId())).toList();
            item.put("propertyValues", props);
            item.put("brandEvidence",com.simlect.api.support.ProductQueryIntent.brandEvidence(p.getProductName(),props.stream().filter(v->"品牌".equals(v.getPropertyName())).map(ProductPropertyValue::getPropertyValue).filter(Objects::nonNull).toList()));
            List<Map<String, Object>> skuItems = new ArrayList<>();
            boolean allKnown = true; long total = 0;
            for (ProductSku s : skus) {
                if (!id.equals(s.getProductId())) continue;
                Map<String, Object> sku = new LinkedHashMap<>();
                String k = key(id, s.getPropertyValueIdHash()); SkuStockDTO stock = stocks.get(k);
                String stockState = unavailable.contains(k) ? "UNAVAILABLE" : stock == null ? "MISSING" : stock.getStock() == null || stock.getStock() < 0 ? "INVALID_RESPONSE" : "SUCCESS";
                Integer count = "SUCCESS".equals(stockState) ? stock.getStock() : null;
                sku.put("productId", id); sku.put("skuId", s.getPropertyValueIdHash());
                sku.put("propertyValueIdHash", s.getPropertyValueIdHash()); sku.put("propertyValueIds", s.getPropertyValueIds());
                List<String> propIds = s.getPropertyValueIds() == null ? List.of() : Arrays.asList(s.getPropertyValueIds().split("-"));
                List<Map<String, String>> specs = props.stream().filter(v -> propIds.contains(v.getPropertyValueId()))
                    .map(v -> { Map<String, String> spec = new LinkedHashMap<>(); spec.put("name", v.getPropertyName()); spec.put("value", v.getPropertyValue()); return spec; }).toList();
                sku.put("specifications", specs);
                sku.put("skuName", String.join(" / ", specs.stream().map(v -> Objects.toString(v.get("name"), "") + ":" + Objects.toString(v.get("value"), "")).toList()));
                sku.put("price", price(s.getPrice())); sku.put("priceStatus", price(s.getPrice()) == null ? "UNKNOWN" : "KNOWN");
                sku.put("stock", count); sku.put("stockQueryStatus", stockState); sku.put("stockObservedAt", Instant.now().toString());
                sku.put("availability", count == null ? "UNKNOWN" : count == 0 ? "OUT_OF_STOCK" : "IN_STOCK");
                if (count == null) allKnown = false; else total += count;
                skuItems.add(sku);
            }
            allKnown &= !skuItems.isEmpty();
            item.put("skus", skuItems); item.put("skuComplete", true);
            item.put("totalStock", allKnown ? total : null);
            item.put("stockQueryStatus", allKnown ? "SUCCESS" : skuItems.stream().anyMatch(s -> "UNAVAILABLE".equals(s.get("stockQueryStatus"))) ? "UNAVAILABLE" : "UNKNOWN");
            item.put("availability", !"ON_SALE".equals(state) ? "NOT_SALEABLE" : !allKnown ? "UNKNOWN" : total == 0 ? "OUT_OF_STOCK" : "IN_STOCK");
            item.put("sources", Map.of("product", "product-service/product_info", "price", "product-service/product_info+product_sku", "stock", "stock-service/sku_stock"));
            out.add(item);
        }
        result.put("products", out);
        return result;
    }

    private static Object price(java.math.BigDecimal p) { return p == null || p.signum() < 0 ? null : p; }
    private static String key(String id, String hash) { return id + "\0" + hash; }
}
