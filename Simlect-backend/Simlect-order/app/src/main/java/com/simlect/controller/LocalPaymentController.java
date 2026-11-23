package com.simlect.controller;

import com.simlect.annotation.GlobalInterceptor;
import com.simlect.api.dto.PayInfoDTO;
import com.simlect.api.dto.PayOrderNotifyDTO;
import com.simlect.biz.OrderInfoService;
import com.simlect.entity.vo.ResponseVO;
import com.simlect.exception.BusinessException;
import jakarta.annotation.Resource;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.*;
import java.util.Map;

/** Explicit local-only payment simulation; never accepts a client-supplied amount. */
@RestController
@RequestMapping("/order")
public class LocalPaymentController extends ABaseController {
    @Resource private OrderInfoService orderInfoService;
    @Value("${simlect.pay.local-mock-enabled:false}") private boolean enabled;
    @Value("${simlect.production-ready:false}") private boolean productionReady;

    @GetMapping("/paymentMode")
    @GlobalInterceptor(checkLogin = true)
    public ResponseVO paymentMode() {
        return getSuccessResponseVO(Map.of("localMock", enabled && !productionReady));
    }

    @PostMapping("/localPay")
    @GlobalInterceptor(checkLogin = true)
    public ResponseVO localPay(@RequestParam String orderId) {
        if (!enabled || productionReady) throw new BusinessException("本地模拟支付未开启");
        // Existing service validates ownership and payable state, and computes the authoritative total.
        PayInfoDTO info = orderInfoService.getPayInfo(getTokenUserInfo().getUserId(), orderId);
        PayOrderNotifyDTO notification = new PayOrderNotifyDTO(info.getPayOrderId(), "LOCAL-" + info.getPayOrderId());
        notification.setTotalAmount(info.getAmount());
        orderInfoService.paySuccess(notification);
        return getSuccessResponseVO(null);
    }
}
