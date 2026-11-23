package com.simlect.controller.internal;

import com.fasterxml.jackson.databind.JsonNode;
import com.simlect.biz.AftersalesCaseService;
import com.simlect.controller.ABaseController;
import com.simlect.controller.aftersales.CaseAuthentication;
import com.simlect.entity.vo.ResponseVO;
import com.simlect.exception.BusinessException;
import jakarta.annotation.Resource;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

@RestController
@RequestMapping("/internal/order/aftersales")
public class AftersalesInternalController extends ABaseController {
    public record Create(long sourceMessageId,JsonNode report) {}
    @Resource private CaseAuthentication auth;
    @Resource private AftersalesCaseService service;
    @Value("${simlect.internal.token:}") private String internalToken;
    @PostMapping("/create") public ResponseVO create(HttpServletRequest r,@RequestBody Create body){
        // Explicit protection remains even if a deployment disables the general internal filter.
        String supplied=r.getHeader("X-Internal-Token");
        if(internalToken.isBlank()||supplied==null||!MessageDigest.isEqual(internalToken.getBytes(StandardCharsets.UTF_8),supplied.getBytes(StandardCharsets.UTF_8)))
            throw new BusinessException("内部调用身份校验失败");
        return getSuccessResponseVO(service.create(auth.user(r),body.sourceMessageId(),body.report()));
    }
}
