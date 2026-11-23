package com.simlect.controller.internal;

import com.simlect.biz.OrderCommentService;
import com.simlect.biz.OrderInfoService;
import com.simlect.biz.OrderItemService;
import com.simlect.biz.OrderLogisticsInfoService;
import com.simlect.component.RedisComponent;
import com.simlect.controller.AGlobalExceptionHandlerController;
import com.simlect.entity.dto.TokenUserInfoDTO;
import com.simlect.entity.po.OrderInfo;
import com.simlect.entity.po.OrderItem;
import com.simlect.utils.AuthCookieHelper;
import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.List;

import static org.hamcrest.Matchers.nullValue;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

@ExtendWith(MockitoExtension.class)
class OrderAgentOwnershipTest {
    @Mock private OrderInfoService orders;
    @Mock private OrderItemService items;
    @Mock private OrderLogisticsInfoService logistics;
    @Mock private OrderCommentService comments;
    @Mock private RedisComponent redis;
    @Mock private AuthCookieHelper cookies;
    private MockMvc mvc;

    private static OrderInfo order(String orderId, String owner) {
        OrderInfo order = new OrderInfo();
        order.setOrderId(orderId);
        order.setUserId(owner);
        return order;
    }

    @BeforeEach
    void setUp() {
        OrderAgentInternalController controller = new OrderAgentInternalController();
        ReflectionTestUtils.setField(controller, "orderInfoService", orders);
        ReflectionTestUtils.setField(controller, "orderItemService", items);
        ReflectionTestUtils.setField(controller, "orderLogisticsInfoService", logistics);
        ReflectionTestUtils.setField(controller, "orderCommentService", comments);
        ReflectionTestUtils.setField(controller, "redisComponent", redis);
        ReflectionTestUtils.setField(controller, "authCookieHelper", cookies);
        when(cookies.resolveWebToken(any(HttpServletRequest.class)))
                .thenAnswer(call -> ((HttpServletRequest) call.getArgument(0)).getHeader("token"));
        lenient().when(redis.getTokenUserInfo(anyString())).thenAnswer(call -> {
            String token = call.getArgument(0);
            if (!token.equals("token-a") && !token.equals("token-b")) return null;
            TokenUserInfoDTO user = new TokenUserInfoDTO();
            user.setUserId(token.equals("token-a") ? "user-a" : "user-b");
            return user;
        });
        lenient().when(orders.getOrderInfoByOrderIdAndUserId(anyString(), anyString())).thenAnswer(call -> {
            String id = call.getArgument(0);
            String user = call.getArgument(1);
            return (id.equals("order-a") && user.equals("user-a"))
                    || (id.equals("order-b") && user.equals("user-b")) ? order(id, user) : null;
        });
        mvc = MockMvcBuilders.standaloneSetup(controller)
                .setControllerAdvice(new AGlobalExceptionHandlerController()).build();
    }

    @Test
    void userA_readsOwnOrder() throws Exception {
        mvc.perform(post("/internal/order/agent/getOrder").header("token", "token-a")
                        .contentType("application/json").content("{\"orderId\":\"order-a\",\"userId\":\"user-a\"}"))
                .andExpect(jsonPath("$.data.userId").value("user-a"));
        verify(orders).getOrderInfoByOrderIdAndUserId("order-a", "user-a");
        verify(orders, never()).getOrderInfoByOrderId(anyString());
    }

    @Test
    void userB_readsOwnOrder() throws Exception {
        mvc.perform(post("/internal/order/agent/getOrder").header("token", "token-b")
                        .contentType("application/json").content("{\"orderId\":\"order-b\"}"))
                .andExpect(jsonPath("$.data.userId").value("user-b"));
    }

    @Test
    void userA_cannotReadOrderB() throws Exception {
        mvc.perform(post("/internal/order/agent/getOrder").header("token", "token-a")
                        .contentType("application/json").content("{\"orderId\":\"order-b\"}"))
                .andExpect(jsonPath("$.data").value(nullValue()));
        verifyNoInteractions(items);
    }

    @ParameterizedTest
    @ValueSource(strings = {"getOrder", "getOrderItem", "listOrderItems", "listOrders", "getLogistics", "getComment"})
    void forgedBodyUserId_neverQueriesBusinessServices(String endpoint) throws Exception {
        mvc.perform(post("/internal/order/agent/" + endpoint).header("token", "token-a")
                        .contentType("application/json").content("{\"userId\":\"user-b\",\"orderId\":\"order-b\",\"orderItemId\":\"item-b\"}"))
                .andExpect(jsonPath("$.status").value("error"))
                .andExpect(jsonPath("$.data").value(nullValue()));
        verifyNoInteractions(orders, items, logistics, comments);
    }

    @ParameterizedTest
    @ValueSource(strings = {"getOrder", "getOrderItem", "listOrderItems", "listOrders", "getLogistics", "getComment"})
    void internalTokenAlone_doesNotAuthenticateBusinessUser(String endpoint) throws Exception {
        mvc.perform(post("/internal/order/agent/" + endpoint).header("X-Internal-Token", "test-internal")
                        .contentType("application/json").content("{\"userId\":\"user-b\",\"orderId\":\"order-b\"}"))
                .andExpect(jsonPath("$.code").value(901))
                .andExpect(jsonPath("$.data").value(nullValue()));
        verifyNoInteractions(orders, items, logistics, comments);
    }

    @Test
    void userA_cannotReadForeignItemThroughOwnedOrderParameter() throws Exception {
        OrderItem item = new OrderItem();
        item.setOrderId("order-b");
        item.setOrderItemId("item-b");
        when(items.getOrderItemByOrderItemId("item-b")).thenReturn(item);
        mvc.perform(post("/internal/order/agent/getOrderItem").header("token", "token-a")
                        .contentType("application/json").content("{\"orderId\":\"order-a\",\"orderItemId\":\"item-b\"}"))
                .andExpect(jsonPath("$.data").value(nullValue()));
        verify(orders).getOrderInfoByOrderIdAndUserId("order-b", "user-a");
    }

    @Test
    void userA_cannotListForeignItems() throws Exception {
        mvc.perform(post("/internal/order/agent/listOrderItems").header("token", "token-a")
                        .contentType("application/json").content("{\"orderId\":\"order-b\"}"))
                .andExpect(jsonPath("$.data.length()").value(0));
        verifyNoInteractions(items);
    }

    @ParameterizedTest
    @ValueSource(strings = {"getLogistics", "getComment"})
    void foreignLogisticsAndComments_areRejectedBeforeQuery(String endpoint) throws Exception {
        mvc.perform(post("/internal/order/agent/" + endpoint).header("token", "token-a")
                        .contentType("application/json").content("{\"orderId\":\"order-b\"}"))
                .andExpect(jsonPath("$.data").value(nullValue()));
        verifyNoInteractions(logistics, comments);
    }

    @Test
    void userA_readsOwnedItem() throws Exception {
        OrderItem item = new OrderItem();
        item.setOrderId("order-a");
        item.setOrderItemId("item-a");
        when(items.getOrderItemByOrderItemId("item-a")).thenReturn(item);
        mvc.perform(post("/internal/order/agent/getOrderItem").header("token", "token-a")
                        .contentType("application/json").content("{\"orderItemId\":\"item-a\"}"))
                .andExpect(jsonPath("$.data.orderItemId").value("item-a"));
    }

    @Test
    void userB_listsOwnedItems() throws Exception {
        OrderItem item = new OrderItem();
        item.setOrderId("order-b");
        item.setOrderItemId("item-b");
        when(items.findListByParam(any())).thenReturn(List.of(item));
        mvc.perform(post("/internal/order/agent/listOrderItems").header("token", "token-b")
                        .contentType("application/json").content("{\"orderId\":\"order-b\"}"))
                .andExpect(jsonPath("$.data[0].orderItemId").value("item-b"));
    }
}
