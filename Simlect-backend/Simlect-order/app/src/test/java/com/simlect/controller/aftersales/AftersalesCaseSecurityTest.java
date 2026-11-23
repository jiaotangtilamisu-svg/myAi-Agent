package com.simlect.controller.aftersales;

import com.simlect.biz.AftersalesCaseService;
import com.simlect.biz.AftersalesCaseService.Actor;
import com.simlect.component.RedisComponent;
import com.simlect.controller.AGlobalExceptionHandlerController;
import com.simlect.controller.internal.AftersalesInternalController;
import com.simlect.entity.dto.TokenUserInfoDTO;
import com.simlect.utils.AuthCookieHelper;
import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.*;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import java.util.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@ExtendWith(MockitoExtension.class)
class AftersalesCaseSecurityTest {
    @Mock RedisComponent redis;
    private final AuthCookieHelper cookies=new AuthCookieHelper();
    @Mock AftersalesCaseService service;
    private MockMvc mvc;
    private final String caseId="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
    private final String command="{\"caseId\":\""+caseId+"\",\"expectedVersion\":1,\"requestId\":\"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb\",\"note\":\"TEST ONLY\",\"admin\":true,\"userId\":\"B\",\"action\":\"APPROVE\",\"executeRefund\":true}";
    @BeforeEach void setup(){
        CaseAuthentication auth=new CaseAuthentication();ReflectionTestUtils.setField(auth,"redis",redis);ReflectionTestUtils.setField(auth,"cookies",cookies);
        lenient().when(redis.getTokenUserInfo(anyString())).thenAnswer(c->{if(!"web-a".equals(c.getArgument(0)))return null;var user=new TokenUserInfoDTO();user.setUserId("A");return user;});
        lenient().when(redis.getLoginInfo4Admin(anyString())).thenAnswer(c->"admin-session".equals(c.getArgument(0))?"operator-1":null);
        AftersalesUserController user=new AftersalesUserController();AftersalesAdminController admin=new AftersalesAdminController();AftersalesInternalController internal=new AftersalesInternalController();
        for(Object controller:List.of(user,admin,internal)){ReflectionTestUtils.setField(controller,"auth",auth);ReflectionTestUtils.setField(controller,"service",service);}
        ReflectionTestUtils.setField(internal,"internalToken","test-internal-only");
        mvc=MockMvcBuilders.standaloneSetup(user,admin,internal).setControllerAdvice(new AGlobalExceptionHandlerController()).build();
    }
    @Test void userLoginRequiredForDetail() throws Exception {mvc.perform(post("/order/aftersalesCase/detail").param("caseId",caseId)).andExpect(jsonPath("$.code").value(901));verifyNoInteractions(service);}
    @Test void webSessionCannotApprove() throws Exception {mvc.perform(post("/admin/aftersalesCase/approve").header("token","web-a").contentType("application/json").content(command)).andExpect(jsonPath("$.code").value(901));verifyNoInteractions(service);}
    @Test void forgedAdminHeaderCannotApprove() throws Exception {mvc.perform(post("/admin/aftersalesCase/approve").header(com.simlect.constants.Constants.TOKEN_ADMIN,"web-a").contentType("application/json").content(command)).andExpect(jsonPath("$.code").value(901));verifyNoInteractions(service);}
    @Test void validAdminIdentityComesFromRedisNotBody() throws Exception {
        when(service.command(any(),eq("APPROVE"),any())).thenReturn(Map.of("executionAllowed",false));
        mvc.perform(post("/admin/aftersalesCase/approve").header(com.simlect.constants.Constants.TOKEN_ADMIN,"admin-session").contentType("application/json").content(command)).andExpect(jsonPath("$.data.executionAllowed").value(false));
        verify(service).command(eq(new Actor("operator-1",true)),eq("APPROVE"),any());
    }
    @Test void userConfirmationCannotBeChangedIntoApprovalOrRefundByBody() throws Exception {
        when(service.command(any(),eq("CONFIRM"),any())).thenReturn(Map.of("executionAllowed",false));
        mvc.perform(post("/order/aftersalesCase/confirm").header("token","web-a").contentType("application/json").content(command)).andExpect(jsonPath("$.data.executionAllowed").value(false));
        verify(service).command(eq(new Actor("A",false)),eq("CONFIRM"),any());
    }
    @Test void internalCreateRequiresInternalAndUserIdentity() throws Exception {
        mvc.perform(post("/internal/order/aftersales/create").header("token","web-a").contentType("application/json").content("{\"sourceMessageId\":1,\"report\":{}}")).andExpect(jsonPath("$.status").value("error"));
        mvc.perform(post("/internal/order/aftersales/create").header("X-Internal-Token","test-internal-only").contentType("application/json").content("{\"sourceMessageId\":1,\"report\":{}}")).andExpect(jsonPath("$.code").value(901));verifyNoInteractions(service);
    }
    @Test void internalCreateDoesNotTrustUserIdInPayload() throws Exception {
        when(service.create(any(),eq(1L),any())).thenReturn(Map.of("caseId",caseId));
        mvc.perform(post("/internal/order/aftersales/create").header("X-Internal-Token","test-internal-only").header("token","web-a").contentType("application/json").content("{\"sourceMessageId\":1,\"userId\":\"B\",\"report\":{}}")).andExpect(jsonPath("$.data.caseId").value(caseId));verify(service).create(eq(new Actor("A",false)),eq(1L),any());
    }
    @Test void ownerTrackingUsesVerifiedIdentityNotBody() throws Exception {
        when(service.command(any(),eq("USER_RETURN_LOGISTICS"),any())).thenReturn(Map.of("executionAllowed",false));
        mvc.perform(post("/order/aftersalesCase/returnLogistics").header("token","web-a").contentType("application/json").content(command)).andExpect(jsonPath("$.data.executionAllowed").value(false));
        verify(service).command(eq(new Actor("A",false)),eq("USER_RETURN_LOGISTICS"),any());
    }
    @Test void trackingCannotBeSubmittedWithoutSession() throws Exception {mvc.perform(post("/order/aftersalesCase/returnLogistics").contentType("application/json").content(command)).andExpect(jsonPath("$.code").value(901));verifyNoInteractions(service);}
    @Test void userCannotSetAdministratorLogisticsProgress() throws Exception {mvc.perform(post("/admin/aftersalesCase/returnProgress").header("token","web-a").contentType("application/json").content(command)).andExpect(jsonPath("$.code").value(901));verifyNoInteractions(service);}
    @Test void noRefundEndpointAndNoExecutorDependency() throws Exception {
        mvc.perform(post("/order/aftersalesCase/refund").header("token","web-a").contentType("application/json").content(command)).andExpect(jsonPath("$.status").value("error"));
        for(var field:AftersalesCaseService.class.getDeclaredFields())assertFalse(field.getType().getSimpleName().matches(".*(Pay|Refund|Execute|Feign).*"));verifyNoInteractions(service);
    }
}
