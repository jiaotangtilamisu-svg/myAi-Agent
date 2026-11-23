package com.simlect.controller.internal;

import com.simlect.api.support.ProductFeignSupport;
import com.simlect.biz.RagQuestionService;
import com.simlect.component.EsSearchComponent;
import com.simlect.constants.RabbitMQConfig;
import com.simlect.constants.ReliableMessageSender;
import com.simlect.controller.ABaseController;
import com.simlect.entity.dto.RagDataDTO;
import com.simlect.entity.enums.MessageReliabilityLevelEnum;
import com.simlect.entity.enums.RagDataTypeEnum;
import com.simlect.entity.po.RagQuestion;
import com.simlect.entity.vo.ResponseVO;
import com.simlect.support.MqIdempotencyKeys;
import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RequestMapping("/internal/search/tool")
@RestController
@Slf4j
public class SearchToolInternalController extends ABaseController {
    @org.springframework.beans.factory.annotation.Value("${simlect.internal.token:}") private String internalToken;
    /** Keyword index refresh only. Never enqueue RAG/Embedding work. */
    @PostMapping("/refreshKeywordIndex")
    public ResponseVO<Void> refreshKeywordIndex(@org.springframework.web.bind.annotation.RequestHeader("X-Internal-Token") String supplied,
            @org.springframework.web.bind.annotation.RequestBody java.util.Map<String,List<String>> body){
        if(internalToken==null||internalToken.isBlank()||supplied==null||!java.security.MessageDigest.isEqual(internalToken.getBytes(java.nio.charset.StandardCharsets.UTF_8),supplied.getBytes(java.nio.charset.StandardCharsets.UTF_8)))throw new com.simlect.exception.BusinessException("内部调用身份校验失败");
        List<String> ids=body.get("productIds");
        if(ids==null||ids.isEmpty()||ids.size()>50||ids.stream().anyMatch(id->id==null||!id.matches("[A-Za-z0-9_-]{1,64}"))||new java.util.HashSet<>(ids).size()!=ids.size())throw new com.simlect.exception.BusinessException("商品批次无效");
        ids.forEach(esSearchComponent::saveIndex);
        return getSuccessResponseVO(null);
    }

    @Resource
    private EsSearchComponent esSearchComponent;
    @Resource
    private ProductFeignSupport productFeignSupport;
    @Resource
    private RagQuestionService ragQuestionService;
    @Resource
    private ReliableMessageSender reliableMessageSender;

    @PostMapping("/productData")
    public ResponseVO<Void> productData() {
        List<String> productIds = productFeignSupport.listOnSaleProductIds();
        for (String productId : productIds) {
            esSearchComponent.saveIndex(productId);
            RagDataDTO ragDataDTO = new RagDataDTO(productId, RagDataTypeEnum.PRODUCT.getType());
            reliableMessageSender.sendMessage(
                    RabbitMQConfig.RAG_EXCHANGE,
                    RabbitMQConfig.RAG_QUEUE_KEY,
                    ragDataDTO,
                    MqIdempotencyKeys.ragProduct(productId),
                    MessageReliabilityLevelEnum.HIGH);
        }
        return getSuccessResponseVO(null);
    }

    @PostMapping("/ragData")
    public ResponseVO<Void> ragData() {
        List<RagQuestion> list = ragQuestionService.findListByParam(null);
        if (list != null) {
            for (RagQuestion ragQuestion : list) {
                RagDataDTO ragDataDTO = new RagDataDTO(
                        ragQuestion.getQuestionId().toString(), RagDataTypeEnum.FAQ.getType());
                reliableMessageSender.sendMessage(
                        RabbitMQConfig.RAG_EXCHANGE,
                        RabbitMQConfig.RAG_QUEUE_KEY,
                        ragDataDTO,
                        MqIdempotencyKeys.ragFaq(String.valueOf(ragQuestion.getQuestionId())),
                        MessageReliabilityLevelEnum.HIGH);
            }
        }
        return getSuccessResponseVO(null);
    }
}
