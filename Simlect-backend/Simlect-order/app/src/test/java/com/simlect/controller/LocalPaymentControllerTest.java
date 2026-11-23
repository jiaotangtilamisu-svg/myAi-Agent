package com.simlect.controller;

import com.simlect.api.dto.PayInfoDTO;
import com.simlect.api.dto.PayOrderNotifyDTO;
import com.simlect.biz.OrderInfoService;
import com.simlect.entity.dto.TokenUserInfoDTO;
import com.simlect.exception.BusinessException;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import java.math.BigDecimal;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class LocalPaymentControllerTest {
    @Test void disabledAndProductionModesCannotChangeOrders() {
        var service = mock(OrderInfoService.class);
        var controller = controller(service);
        ReflectionTestUtils.setField(controller, "enabled", false);
        assertThrows(BusinessException.class, () -> controller.localPay("O1"));
        ReflectionTestUtils.setField(controller, "enabled", true);
        ReflectionTestUtils.setField(controller, "productionReady", true);
        assertThrows(BusinessException.class, () -> controller.localPay("O1"));
        verifyNoInteractions(service);
    }
    @Test void ownershipFailureNeverMarksPaymentSuccessful() {
        var service = mock(OrderInfoService.class);
        var controller = controller(service);
        when(service.getPayInfo("LOCALDEMO", "foreign")).thenThrow(new BusinessException("订单不存在"));
        assertThrows(BusinessException.class, () -> controller.localPay("foreign"));
        verify(service, never()).paySuccess(any());
    }
    @Test void successfulPaymentUsesServerAmountAndExistingStateMachine() {
        var service = mock(OrderInfoService.class);
        var controller = controller(service);
        when(service.getPayInfo("LOCALDEMO", "O1")).thenReturn(new PayInfoDTO(null, "P1", new BigDecimal("199.00")));
        controller.localPay("O1");
        var captor = org.mockito.ArgumentCaptor.forClass(PayOrderNotifyDTO.class);
        verify(service).paySuccess(captor.capture());
        assertEquals("P1", captor.getValue().getPayOrderId());
        assertEquals("LOCAL-P1", captor.getValue().getChannelOrderId());
        assertEquals(new BigDecimal("199.00"), captor.getValue().getTotalAmount());
    }
    private LocalPaymentController controller(OrderInfoService service) {
        var controller = spy(new LocalPaymentController());
        ReflectionTestUtils.setField(controller, "orderInfoService", service);
        ReflectionTestUtils.setField(controller, "enabled", true);
        var token = new TokenUserInfoDTO();
        token.setUserId("LOCALDEMO");
        doReturn(token).when(controller).getTokenUserInfo();
        return controller;
    }
}
