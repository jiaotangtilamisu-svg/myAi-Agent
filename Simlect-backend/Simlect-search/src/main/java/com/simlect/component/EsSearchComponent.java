package com.simlect.component;

import com.simlect.api.support.ProductFeignSupport;
import com.simlect.api.vo.ProductSearchIndexVO;
import com.simlect.api.dto.ProductInfoDTO;
import com.simlect.entity.enums.PageSize;
import com.simlect.api.enums.ProductStatusEnum;
import com.simlect.entity.vo.PaginationResultVO;
import com.simlect.utils.StringTools;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.Resource;
import jakarta.validation.constraints.NotEmpty;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.BeanUtils;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

@Component("esSearchComponent")
@Slf4j
public class EsSearchComponent {

    @Resource
    private ElasticsearchOperations elasticsearchOperations;

    @Resource
    private ProductFeignSupport productFeignSupport;

    @PostConstruct
    public void createIndexWithIK() {
        try {
            IndexOperations indexOperations = elasticsearchOperations.indexOps(ProductInfoDTO.class);
            if (indexOperations.exists()) {
                log.info("索引已存在，跳过创建");
                return;
            }
            Boolean success = indexOperations.createWithMapping();
            if (Boolean.TRUE.equals(success)) {
                log.info("索引创建成功（IK 分词）");
            } else {
                log.error("创建索引失败：ES 返回 false。请确认已安装 analysis-ik（镜像 simlect-elasticsearch:9.2.1-ik）");
            }
        } catch (Exception e) {
            log.error("创建索引失败（常见原因：ES 未安装 IK 插件 ik_max_word）。"
                    + "请重建中间件 ES：docker compose -f deploy/docker-compose.middleware.yml build elasticsearch --no-cache && up -d elasticsearch", e);
        }
    }

    // 保存索引
    public void saveIndex(String productId){
        ProductSearchIndexVO productInfo = productFeignSupport.getSearchIndex(productId);
        if (productInfo == null) {
            ProductInfoDTO deleteDto = new ProductInfoDTO();
            deleteDto.setProductId(productId);
            try {
                elasticsearchOperations.delete(deleteDto);
            } catch (Exception e) {
                log.warn("删除不存在商品的ES索引跳过 productId={}", productId);
            }
            return;
        }
        ProductInfoDTO productInfoDTO = new ProductInfoDTO();
        BeanUtils.copyProperties(productInfo, productInfoDTO);
        if (ProductStatusEnum.ON_SALE.getStatus().equals(productInfo.getStatus())){
            elasticsearchOperations.save(productInfoDTO);
        }else {
            elasticsearchOperations.delete(productInfoDTO);
        }
    }
    // 查询索引
    public PaginationResultVO<ProductInfoDTO> searchProducts(@NotEmpty String keyWords,
                                                             BigDecimal priceFrom,
                                                             BigDecimal priceTo,
                                                             String sortType,
                                                             String sortField,
                                                             Integer pageNo){
        try {
            // 参数处理
            pageNo = pageNo == null ? 1 : pageNo;
            //es 分页从0开始
            pageNo = pageNo - 1;
            int pageSize = PageSize.SIZE15.getSize();
            java.util.List<Object> filters=new java.util.ArrayList<>();
            com.fasterxml.jackson.databind.ObjectMapper mapper=new com.fasterxml.jackson.databind.ObjectMapper();
            if(priceFrom!=null)filters.add(java.util.Map.of("range",java.util.Map.of("maxPrice",java.util.Map.of("gte",priceFrom))));
            if(priceTo!=null)filters.add(java.util.Map.of("range",java.util.Map.of("minPrice",java.util.Map.of("lte",priceTo))));
            if("price".equals(sortField)){filters.add(java.util.Map.of("exists",java.util.Map.of("field","minPrice")));filters.add(java.util.Map.of("exists",java.util.Map.of("field","maxPrice")));}
            Object lexical=mapper.readValue(ProductLexicalQuery.json(keyWords),Object.class);
            String queryJson=mapper.writeValueAsString(java.util.Map.of("bool",java.util.Map.of("must",java.util.List.of(lexical),"filter",filters)));
            // 对于分类
            // 如果sortField为空，则默认为综合分类
            if (sortField == null){
                sortField = "composite";
            }
            if (sortField.equals("composite")){
                sortField = "_score";
            }else if (sortField.equals("price")){
                sortField = "minPrice";
            }else if (sortField.equals("sale")){
                sortField = "totalSale";
            }

            // 对于排序
            // 如果sortType为空，则默认为降序
            Sort.Direction sortDirection = Sort.Direction.DESC;
            if (Objects.equals(sortType, "asc")){
                sortDirection = Sort.Direction.ASC;
            }

            Sort sort = Sort.by(sortDirection, sortField);
            // 分页
            Pageable pageable = PageRequest.of(pageNo, pageSize, sort);
            // 执行查询
            org.springframework.data.elasticsearch.core.query.StringQuery criteriaQuery = new org.springframework.data.elasticsearch.core.query.StringQuery(queryJson);
            criteriaQuery.setPageable(pageable);
            SearchHits<ProductInfoDTO> searchHits = elasticsearchOperations.search(criteriaQuery, ProductInfoDTO.class);
            // 处理结果
            List<ProductInfoDTO> productInfoDTOList = searchHits.getSearchHits().stream().map(SearchHit::getContent).collect(Collectors.toList());
            long totalHits = searchHits.getTotalHits();
            int totalPage = (int) Math.ceil((double) totalHits / pageSize);
            return new PaginationResultVO<>((int) totalHits, pageSize, pageNo + 1, totalPage, productInfoDTOList);

        }catch (Exception e){
            log.error("搜索失败", e);
            throw new com.simlect.exception.BusinessException("搜索服务暂时不可用，请稍后重试");
        }
    }
}


