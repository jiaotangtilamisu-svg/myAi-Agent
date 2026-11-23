package com.simlect.biz;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.simlect.biz.AftersalesCaseService.*;
import com.simlect.entity.po.OrderInfo;
import com.simlect.exception.BusinessException;
import com.simlect.mappers.AftersalesCaseMapper;
import org.junit.jupiter.api.*;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.mybatis.spring.*;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.*;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.annotation.AnnotationTransactionAttributeSource;
import org.springframework.transaction.interceptor.TransactionInterceptor;
import java.nio.file.*;
import java.lang.reflect.*;
import java.util.*;
import java.util.concurrent.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/** Actual mapper SQL, transactions and concurrency against fresh in-memory H2 MySQL mode. */
class AftersalesCasePersistenceTest {
    private final ObjectMapper json=new ObjectMapper();
    private final Actor user=new Actor("A",false), admin=new Actor("admin-1",true);
    private AftersalesCaseService service;
    private AftersalesCaseMapper mapper;
    private JdbcTemplate jdbc;
    private OrderInfoService orders;
    private DataSourceTransactionManager tx;

    protected boolean usesIsolatedMySql(){return false;}
    @BeforeEach void setup() throws Exception {
        DriverManagerDataSource ds;
        String isolated=System.getenv("QUALITY_MYSQL_SCHEMA");
        if(usesIsolatedMySql()){
            if(isolated==null||!isolated.matches("simlect_quality32_[a-f0-9]{12}")||System.getenv("QUALITY_MYSQL_PASSWORD")==null)throw new IllegalStateException("Explicit isolated MySQL fixture is required");
            ds=new DriverManagerDataSource("jdbc:mysql://127.0.0.1:13306/"+isolated+"?useUnicode=true&characterEncoding=utf-8&serverTimezone=Asia/Shanghai&useSSL=false","root",System.getenv("QUALITY_MYSQL_PASSWORD"));
            jdbc=new JdbcTemplate(ds);
        }else{
            ds=new DriverManagerDataSource("jdbc:h2:mem:"+UUID.randomUUID()+";MODE=MySQL;DATABASE_TO_UPPER=FALSE;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=10000","sa","");
            jdbc=new JdbcTemplate(ds);jdbc.execute("CREATE SCHEMA simlect_order");
            ds.setUrl(ds.getUrl()+";INIT=SET SCHEMA simlect_order");
        }
        Path root=Path.of("").toAbsolutePath();while(!Files.exists(root.resolve("sql/09_aftersales_cases.sql")))root=root.getParent();
        String sql=Files.readString(root.resolve("sql/09_aftersales_cases.sql")).replaceAll("(?m)^--.*$","");
        if(usesIsolatedMySql())sql=sql.replace("USE simlect_order;","USE `"+isolated+"`;");
        for(String statement:sql.split(";"))if(!statement.isBlank())jdbc.execute(statement);
        if(usesIsolatedMySql())for(String table:List.of("aftersales_audit","aftersales_manual_task","aftersales_plan","aftersales_case"))jdbc.execute("DELETE FROM `"+isolated+"`.`"+table+"`");
        if(usesIsolatedMySql()){
            jdbc.execute("CREATE TABLE IF NOT EXISTS `"+isolated+"`.order_info LIKE simlect_order.order_info");
            jdbc.execute("DELETE FROM `"+isolated+"`.order_info");
            jdbc.update("INSERT INTO order_info(order_id,user_id,order_status) VALUES('O-A','A',2),('O-B','B',2)");
        }
        // Reapplying the additive script does not remove existing content.
        for(String statement:sql.split(";"))if(!statement.isBlank())jdbc.execute(statement);
        var factory=new SqlSessionFactoryBean();factory.setDataSource(ds);
        if(usesIsolatedMySql())factory.setMapperLocations(new org.springframework.core.io.ClassPathResource("com/simlect/mappers/OrderInfoMapper.xml"));
        var config=new org.apache.ibatis.session.Configuration();config.setMapUnderscoreToCamelCase(true);config.addMapper(AftersalesCaseMapper.class);factory.setConfiguration(config);
        mapper=new SqlSessionTemplate(factory.getObject()).getMapper(AftersalesCaseMapper.class);
        if(usesIsolatedMySql()){
            var reader=new com.simlect.biz.impl.OrderInfoServiceImpl();
            ReflectionTestUtils.setField(reader,"orderInfoMapper",new SqlSessionTemplate(factory.getObject()).getMapper(com.simlect.mappers.OrderInfoMapper.class));
            orders=spy(reader); // Real SQL normally; individual fault tests may override one lookup.
        }else{
          orders=mock(OrderInfoService.class);
          when(orders.getOrderInfoByOrderIdAndUserId(anyString(),anyString())).thenAnswer(i->{
            String id=i.getArgument(0), owner=i.getArgument(1);
            if(!(id.equals("O-A")&&owner.equals("A"))&&!(id.equals("O-B")&&owner.equals("B")))return null;
            OrderInfo row=new OrderInfo();row.setOrderId(id);row.setUserId(owner);row.setOrderStatus(2);return row;
          });
        }
        tx=new DataSourceTransactionManager(ds);service=proxied(mapper);
    }
    protected OrderInfo readFixtureOrder(String id,String user){return orders.getOrderInfoByOrderIdAndUserId(id,user);}
    private AftersalesCaseService proxied(AftersalesCaseMapper repository){
        var target=new AftersalesCaseService();ReflectionTestUtils.setField(target,"mapper",repository);ReflectionTestUtils.setField(target,"orderInfoService",orders);
        var proxy=new ProxyFactory(target);proxy.setProxyTargetClass(true);
        proxy.addAdvice(new TransactionInterceptor(tx,new AnnotationTransactionAttributeSource()));return (AftersalesCaseService)proxy.getProxy();
    }
    private ObjectNode report(boolean low){
        var r=json.createObjectNode();r.put("schemaVersion",1);r.put("orderId","O-A");r.put("executionAllowed",false);
        r.put("caseType",low?"AFTERSALES_CONSULT":"REFUND_PROGRESS");
        r.putObject("orderFacts").put("queryStatus","SUCCESS").putObject("data").put("ownerVerified",true).put("orderId","O-A");
        r.putObject("diagnosis").put("status",low?"NOT_OBSERVED":"UNCERTAIN");
        r.putObject("policyEvidence").put("status","SUCCESS").putArray("hits").addObject().put("documentName","TEST ONLY").put("revision",1).put("source","fixture://test");
        r.putArray("recommendedActions").addObject().put("code",low?"CONTACT_CARRIER":"REFUND_REVIEW").put("title","UNTRUSTED auto refund title");return r;
    }
    private Map<String,Object> create(boolean low){return service.create(user,1,report(low));}
    private Command command(Map<String,Object> row,String note){return new Command((String)row.get("caseId"),((Number)row.get("version")).longValue(),UUID.randomUUID().toString(),note);}
    private Map<String,Object> step(Actor actor,String action,Map<String,Object> row){return service.command(actor,action,command(row,"TEST ONLY manual note"));}
    private Map<String,Object> active(){var r=step(user,"CONFIRM",create(false));r=step(admin,"APPROVE",r);return step(admin,"CLAIM",r);}
    @Test void ordinaryOrderReturnRequestStillRequiresAdministratorReview(){var r=report(true);r.put("requestedOperation","RETURN_GUIDANCE");var row=service.create(user,1,r);assertEquals("HIGH",row.get("risk"));row=step(user,"CONFIRM",row);assertEquals("ADMIN_REVIEW",row.get("state"));assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM aftersales_manual_task",Integer.class));}
    @Test void fulfillmentDefaultRefundSwitchIsClosed(){var r=active();assertThrows(com.simlect.exception.BusinessException.class,()->service.command(admin,"MOCK_REFUND",command(r,"{\"type\":\"refund\"}")));}
    @Test void refundCapabilitiesAreServerFactsNotPendingStatus(){
        var r=active();assertEquals(false,((Map<?,?>)r.get("capabilities")).get("mockRefundEnabled"));
        ReflectionTestUtils.setField(service,"mockRefundEnabled",true);
        var capability=(Map<?,?>)service.detail(user,(String)r.get("caseId")).get("capabilities");
        assertEquals(true,capability.get("mockRefundEnabled"));assertEquals(false,capability.get("realRefundExecutionEnabled"));
    }
    @Test void repeatedAdminTrackingWithNewRequestIdDoesNotAdvanceOrFakeAcceptance(){
        var r=active();r=service.command(user,"USER_RETURN_LOGISTICS",command(r,"{\"type\":\"return_refund\",\"carrier\":\"TEST\",\"trackingNo\":\"TEST12345\"}"));
        var current=r;int count=events(r).size();
        var failure=assertThrows(BusinessException.class,()->service.command(admin,"RETURN_LOGISTICS",command(current,"{\"type\":\"return_refund\",\"carrier\":\"TEST\",\"trackingNo\":\"TEST12345\",\"accepted\":true}")));
        assertTrue(failure.getMessage().contains("已登记"));
        var saved=service.detail(user,(String)r.get("caseId"));assertEquals(count,events(saved).size());assertEquals(r.get("version"),saved.get("version"));
        assertNull(((Map<?,?>)saved.get("fulfillment")).get("acceptance"));
    }
    @Test void adminTrackingIsCanonicalAndCorrectionRequiresReason(){
        var r=active();r=service.command(admin,"RETURN_LOGISTICS",command(r,"{\"type\":\"return_refund\",\"carrier\":\"TEST\",\"trackingNo\":\"TEST12345\",\"accepted\":true}"));
        assertFalse(String.valueOf(events(r).get(events(r).size()-1).get("note")).contains("accepted"));
        var before=r;assertThrows(BusinessException.class,()->service.command(admin,"RETURN_LOGISTICS",command(before,"{\"type\":\"return_refund\",\"carrier\":\"TEST\",\"trackingNo\":\"CORRECT12345\"}")));
        r=service.command(admin,"RETURN_LOGISTICS",command(r,"{\"type\":\"return_refund\",\"carrier\":\"TEST\",\"trackingNo\":\"CORRECT12345\",\"result\":\"TEST verified typo correction\"}"));
        assertEquals("CORRECT12345",((Map<?,?>)r.get("fulfillment")).get("trackingNo"));
    }
    @Test void orderScopedCaseQueryFiltersBeforePaginationAndKeepsOwnership(){
        OrderInfo owned=new OrderInfo();owned.setOrderId("O-OLDER");owned.setUserId("A");owned.setOrderStatus(3);
        when(orders.getOrderInfoByOrderIdAndUserId("O-OLDER","A")).thenReturn(owned);
        var diagnosis=report(false);diagnosis.put("orderId","O-OLDER");((ObjectNode)diagnosis.path("orderFacts").path("data")).put("orderId","O-OLDER");
        var target=service.create(user,100,diagnosis);
        for(int i=0;i<25;i++)service.create(user,200+i,report(false));
        var result=service.list(user,null,1,20,"O-OLDER");assertEquals(1,result.size());assertEquals(target.get("caseId"),result.get(0).get("caseId"));
        assertTrue(service.list(new Actor("B",false),null,1,20,"O-OLDER").isEmpty());
    }
    @Test void returnMustHaveTrackingBeforeAcceptance(){var r=active();assertThrows(com.simlect.exception.BusinessException.class,()->service.command(admin,"RETURN_ACCEPT",command(r,"{\"type\":\"return_refund\",\"accepted\":true,\"result\":\"TEST\"}")));}
    @Test void returnLogisticsAndAcceptanceAreAudited(){var r=active();r=service.command(admin,"RETURN_LOGISTICS",command(r,"{\"type\":\"return_refund\",\"carrier\":\"TEST\",\"trackingNo\":\"TEST12345\"}"));r=service.command(admin,"RETURN_ACCEPT",command(r,"{\"type\":\"return_refund\",\"accepted\":true,\"result\":\"TEST acceptance\"}"));assertEquals("IN_PROGRESS",r.get("state"));assertEquals(6,events(r).size());}
    @Test void ordinaryUserCannotRegisterReturnHandling(){var r=active();assertThrows(com.simlect.exception.BusinessException.class,()->service.command(user,"RETURN_LOGISTICS",command(r,"{}")));}
    @Test void mockFailureRetryReusesRefundIdAndSuccessIsNotRepeated() throws Exception {
        ReflectionTestUtils.setField(service,"mockRefundEnabled",true);var r=active();
        r=service.command(admin,"MOCK_REFUND",command(r,"{\"type\":\"refund\",\"simulateFailure\":true}"));
        String first=json.readTree((String)events(r).get(events(r).size()-1).get("note")).path("refundId").asText();
        r=service.command(admin,"MOCK_REFUND",command(r,"{\"type\":\"refund\"}"));
        var last=json.readTree((String)events(r).get(events(r).size()-1).get("note"));assertEquals(first,last.path("refundId").asText());assertEquals("MOCK",last.path("mode").asText());assertFalse(last.path("executionAllowed").asBoolean());
        var finalRow=r;assertThrows(com.simlect.exception.BusinessException.class,()->service.command(admin,"MOCK_REFUND",command(finalRow,"{\"type\":\"refund\"}")));
    }
    @Test void userReturnTrackingAfterApprovalIsOwnedAndAudited(){
        var r=step(admin,"APPROVE",step(user,"CONFIRM",create(false)));
        var cmd=command(r,"{\"type\":\"return_refund\",\"carrier\":\"TEST\",\"trackingNo\":\"TEST12345\",\"accepted\":true}");
        r=service.command(user,"USER_RETURN_LOGISTICS",cmd);assertEquals("MANUAL_PENDING",r.get("state"));
        assertEquals(true,service.command(user,"USER_RETURN_LOGISTICS",cmd).get("replayed"));
        var f=(Map<?,?>)r.get("fulfillment");assertEquals("TEST12345",f.get("trackingNo"));assertNull(f.get("acceptance"));
        assertThrows(BusinessException.class,()->service.command(user,"USER_RETURN_LOGISTICS",cmdFor(cmd.caseId(),3,"{}")));
    }
    private Command cmdFor(String id,long version,String note){return new Command(id,version,UUID.randomUUID().toString(),note);}
    @Test void otherUserCannotRegisterTracking(){var r=active();assertThrows(BusinessException.class,()->service.command(new Actor("B",false),"USER_RETURN_LOGISTICS",command(r,"{}")));}
    @Test void draftOrReviewCannotRegisterTracking(){var r=create(false);var draft=r;assertThrows(BusinessException.class,()->service.command(user,"USER_RETURN_LOGISTICS",command(draft,"{}")));r=step(user,"CONFIRM",r);var review=r;assertThrows(BusinessException.class,()->service.command(user,"USER_RETURN_LOGISTICS",command(review,"{}")));}
    @Test void userTrackingThenAdminProgressExceptionAndAcceptance(){
        var r=active();r=service.command(user,"USER_RETURN_LOGISTICS",command(r,"{\"type\":\"return_refund\",\"carrier\":\"TEST\",\"trackingNo\":\"TEST12345\"}"));
        r=service.command(admin,"RETURN_PROGRESS",command(r,"{\"type\":\"return_refund\",\"logisticsStatus\":\"EXCEPTION\",\"result\":\"TEST followup\"}"));
        assertEquals("EXCEPTION",((Map<?,?>)r.get("fulfillment")).get("logisticsStatus"));
        r=service.command(admin,"RETURN_ACCEPT",command(r,"{\"type\":\"return_refund\",\"accepted\":false,\"result\":\"TEST damaged\"}"));
        assertEquals("REJECTED",((Map<?,?>)r.get("fulfillment")).get("acceptance"));
        ReflectionTestUtils.setField(service,"mockRefundEnabled",true);var rejected=r;assertThrows(BusinessException.class,()->service.command(admin,"MOCK_REFUND",command(rejected,"{\"type\":\"return_refund\"}")));
    }
    @Test void userCannotFalsifyProgressOrAcceptance(){var r=active();for(String action:List.of("RETURN_PROGRESS","RETURN_ACCEPT","MOCK_REFUND"))assertThrows(BusinessException.class,()->service.command(user,action,command(r,"{}")));}
    @Test void progressNeedsTrackingAndValidState(){var r=active();assertThrows(BusinessException.class,()->service.command(admin,"RETURN_PROGRESS",command(r,"{\"type\":\"return_refund\",\"logisticsStatus\":\"DELIVERED\",\"result\":\"TEST\"}")));}
    @Test void applicationReasonIsMandatoryAndProjected(){var r=create(false);var draft=r;assertThrows(BusinessException.class,()->service.command(user,"CONFIRM",command(draft,"")));r=step(user,"CONFIRM",r);assertEquals("TEST ONLY manual note",r.get("applicationReason"));}
    @Test void mockRefundFailureProjectionPreservesStableId(){ReflectionTestUtils.setField(service,"mockRefundEnabled",true);var r=active();r=service.command(admin,"MOCK_REFUND",command(r,"{\"type\":\"refund\",\"simulateFailure\":true,\"result\":\"TEST unavailable\"}"));var f=(Map<?,?>)r.get("fulfillment");assertEquals("FAILED",f.get("refundStatus"));assertEquals("TEST unavailable",f.get("failureReason"));assertEquals(false,f.get("executionAllowed"));String id=(String)f.get("refundId");r=service.command(admin,"MOCK_REFUND",command(r,"{\"type\":\"refund\"}"));assertEquals(id,((Map<?,?>)r.get("fulfillment")).get("refundId"));assertEquals("SUCCEEDED",((Map<?,?>)r.get("fulfillment")).get("refundStatus"));}
    @Test void confirmRechecksCurrentOrderOwnership(){var r=create(false);when(orders.getOrderInfoByOrderIdAndUserId("O-A","A")).thenReturn(null);assertThrows(BusinessException.class,()->step(user,"CONFIRM",r));assertEquals("AWAITING_USER",service.detail(user,(String)r.get("caseId")).get("state"));}
    @Test void structuredApplicationReasonAndMaterialsPersist(){var r=create(false);r=service.command(user,"CONFIRM",command(r,"{\"reason\":\"TEST broken product\",\"materials\":[\"TEST evidence description\"]}"));assertEquals("TEST broken product",r.get("applicationReason"));assertEquals("TEST evidence description",((JsonNode)r.get("applicationMaterials")).get(0).asText());assertEquals(2,((JsonNode)r.get("submittedOrderStatus")).asInt());}
    @Test void malformedApplicationMaterialsCannotSubmit(){var r=create(false);assertThrows(BusinessException.class,()->service.command(user,"CONFIRM",command(r,"{\"reason\":\"TEST\",\"materials\":[true]}")));assertEquals("AWAITING_USER",service.detail(user,(String)r.get("caseId")).get("state"));}
    @Test void refundGuidanceCannotBypassNonEmptyPlanValidation(){var r=report(false);r.put("requestedOperation","RETURN_GUIDANCE");r.set("recommendedActions",json.createArrayNode());assertThrows(BusinessException.class,()->service.create(user,1,r));assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM aftersales_case",Integer.class));}
    @Test void stringFailureFlagCannotSilentlyBecomeMockSuccess(){ReflectionTestUtils.setField(service,"mockRefundEnabled",true);var r=active();assertThrows(BusinessException.class,()->service.command(admin,"MOCK_REFUND",command(r,"{\"type\":\"refund\",\"simulateFailure\":\"yes\"}")));assertEquals("NOT_EXECUTED",((Map<?,?>)service.detail(user,(String)r.get("caseId")).get("fulfillment")).get("refundStatus"));}
    @Test void punctuationOnlyTrackingIsNotAnActualTrackingNumber(){var r=active();assertThrows(BusinessException.class,()->service.command(user,"USER_RETURN_LOGISTICS",command(r,"{\"type\":\"return_refund\",\"carrier\":\"TEST\",\"trackingNo\":\"-----\"}")));}
    private Map<String,Object> fixtureState(String target,long source){
        var row=service.create(user,source,report(false));
        if(target.equals("AWAITING_USER"))return row;
        row=step(user,"CONFIRM",row);if(target.equals("ADMIN_REVIEW"))return row;
        if(target.equals("REJECTED"))return step(admin,"REJECT",row);
        row=step(admin,"APPROVE",row);if(target.equals("MANUAL_PENDING"))return row;
        row=step(admin,"CLAIM",row);if(target.equals("IN_PROGRESS"))return row;
        if(target.equals("PROCESSING_FAILED"))return step(admin,"FAIL",row);
        row=step(admin,"SUCCEED",row);if(target.equals("RESOLVED"))return row;
        return step(user,"ARCHIVE",row);
    }
    @ParameterizedTest @ValueSource(strings={"AWAITING_USER","ADMIN_REVIEW","REJECTED","MANUAL_PENDING","IN_PROGRESS","PROCESSING_FAILED","RESOLVED","ARCHIVED"})
    void independentStateModelChecksEveryCoreCommand(String state){
        Map<String,Map<String,String>> rules=Map.of(
            "AWAITING_USER",Map.of("CONFIRM","ADMIN_REVIEW"),"ADMIN_REVIEW",Map.of("APPROVE","MANUAL_PENDING","REJECT","REJECTED"),
            "REJECTED",Map.of("RESUBMIT","AWAITING_USER","ARCHIVE","ARCHIVED"),"MANUAL_PENDING",Map.of("CLAIM","IN_PROGRESS"),
            "IN_PROGRESS",Map.of("SUCCEED","RESOLVED","FAIL","PROCESSING_FAILED"),"PROCESSING_FAILED",Map.of("RETRY","MANUAL_PENDING"),
            "RESOLVED",Map.of("ARCHIVE","ARCHIVED"),"ARCHIVED",Map.of());
        long source=10000;
        for(String action:List.of("CONFIRM","APPROVE","REJECT","RESUBMIT","CLAIM","SUCCEED","FAIL","RETRY","ARCHIVE")){
            var row=fixtureState(state,source++);var actor=Set.of("CONFIRM","RESUBMIT","ARCHIVE").contains(action)?user:admin;
            int before=events(row).size();String expected=rules.get(state).get(action);
            if(expected!=null){var next=service.command(actor,action,command(row,"TEST model command"));assertEquals(expected,next.get("state"));assertEquals(before+1,events(next).size());}
            else{assertThrows(BusinessException.class,()->service.command(actor,action,command(row,"TEST invalid command")));var after=service.detail(user,(String)row.get("caseId"));assertEquals(state,after.get("state"));assertEquals(before,events(after).size());}
        }
    }
    private org.springframework.test.web.servlet.MockMvc actualCaseHttp(){
        var redis=mock(com.simlect.component.RedisComponent.class);
        when(redis.getTokenUserInfo(anyString())).thenAnswer(c->{if(!"fixture-a".equals(c.getArgument(0)))return null;var u=new com.simlect.entity.dto.TokenUserInfoDTO();u.setUserId("A");return u;});
        when(redis.getLoginInfo4Admin(anyString())).thenAnswer(c->"fixture-admin".equals(c.getArgument(0))?"admin-1":null);
        var auth=new com.simlect.controller.aftersales.CaseAuthentication();ReflectionTestUtils.setField(auth,"redis",redis);ReflectionTestUtils.setField(auth,"cookies",new com.simlect.utils.AuthCookieHelper());
        var userController=new com.simlect.controller.aftersales.AftersalesUserController();var adminController=new com.simlect.controller.aftersales.AftersalesAdminController();
        for(var controller:List.of(userController,adminController)){ReflectionTestUtils.setField(controller,"auth",auth);ReflectionTestUtils.setField(controller,"service",service);}
        return org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup(userController,adminController).setControllerAdvice(new com.simlect.controller.AGlobalExceptionHandlerController()).build();
    }
    private Map<String,Object> httpCommand(org.springframework.test.web.servlet.MockMvc mvc,boolean isAdmin,String action,Map<String,Object> row,String note) throws Exception {
        var response=mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post((isAdmin?"/admin/aftersalesCase/":"/order/aftersalesCase/")+action)
            .header(isAdmin?com.simlect.constants.Constants.TOKEN_ADMIN:com.simlect.constants.Constants.TOKEN_WEB,isAdmin?"fixture-admin":"fixture-a").contentType("application/json").content(json.writeValueAsString(command(row,note)))).andReturn().getResponse();
        JsonNode body=json.readTree(response.getContentAsString(java.nio.charset.StandardCharsets.UTF_8));assertEquals(200,body.path("code").asInt(),body.toString());
        return json.convertValue(body.get("data"),new com.fasterxml.jackson.core.type.TypeReference<Map<String,Object>>(){});
    }
    @Test void userCaseReadAcceptsActualPythonJsonAndBrowserFormContracts() throws Exception {
        var row=create(false);var mvc=actualCaseHttp();
        for(boolean jsonBody:List.of(true,false)){
            var request=org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post("/order/aftersalesCase/list").header(com.simlect.constants.Constants.TOKEN_WEB,"fixture-a");
            if(jsonBody)request.contentType("application/json").content("{\"orderId\":\"O-A\"}");else request.param("orderId","O-A");
            JsonNode response=json.readTree(mvc.perform(request).andReturn().getResponse().getContentAsString(java.nio.charset.StandardCharsets.UTF_8));
            assertEquals(200,response.path("code").asInt());assertEquals(row.get("caseId"),response.path("data").get(0).path("caseId").asText());
        }
        var detail=org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post("/order/aftersalesCase/detail").header(com.simlect.constants.Constants.TOKEN_WEB,"fixture-a").contentType("application/json").content("{\"caseId\":\""+row.get("caseId")+"\"}");
        JsonNode data=json.readTree(mvc.perform(detail).andReturn().getResponse().getContentAsString(java.nio.charset.StandardCharsets.UTF_8));
        assertEquals(200,data.path("code").asInt());assertEquals("O-A",data.path("data").path("orderId").asText());
    }
    @Test void actualControllerTransactionMapperReturnRefundLifecycle() throws Exception {
        ReflectionTestUtils.setField(service,"mockRefundEnabled",true);var mvc=actualCaseHttp();var r=create(false);
        r=httpCommand(mvc,false,"confirm",r,"{\"reason\":\"TEST quality concern\",\"materials\":[\"TEST description\"]}");assertEquals("ADMIN_REVIEW",r.get("state"));
        r=httpCommand(mvc,true,"approve",r,"TEST verified and approved for manual handling");r=httpCommand(mvc,true,"claim",r,"TEST claim");
        r=httpCommand(mvc,false,"returnLogistics",r,"{\"type\":\"return_refund\",\"carrier\":\"TEST\",\"trackingNo\":\"TEST12345\"}");
        r=httpCommand(mvc,true,"returnProgress",r,"{\"type\":\"return_refund\",\"logisticsStatus\":\"DELIVERED\",\"result\":\"TEST checked delivery\"}");
        r=httpCommand(mvc,true,"acceptReturn",r,"{\"type\":\"return_refund\",\"accepted\":true,\"result\":\"TEST accepted\"}");
        r=httpCommand(mvc,true,"simulateRefund",r,"{\"type\":\"return_refund\",\"simulateFailure\":true,\"result\":\"TEST transient failure\"}");
        var failed=(Map<?,?>)r.get("fulfillment");assertEquals("FAILED",failed.get("refundStatus"));String id=(String)failed.get("refundId");
        r=httpCommand(mvc,true,"simulateRefund",r,"{\"type\":\"return_refund\"}");var success=(Map<?,?>)r.get("fulfillment");assertEquals("SUCCEEDED",success.get("refundStatus"));assertEquals(id,success.get("refundId"));assertEquals("MOCK",success.get("refundMode"));
        r=httpCommand(mvc,true,"succeed",r,"TEST mock handling complete, not bank settlement");r=httpCommand(mvc,false,"archive",r,"TEST archive");assertEquals("ARCHIVED",r.get("state"));
        assertEquals(11,events(r).size());assertEquals(11,jdbc.queryForObject("SELECT COUNT(*) FROM aftersales_audit",Integer.class));
    }
    @Test void actualControllerRejectsUntrustedUserWithoutAuditWrites() throws Exception {
        var mvc=actualCaseHttp();var r=create(false);String payload=json.writeValueAsString(command(r,"TEST"));
        var response=mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post("/order/aftersalesCase/confirm").header("token","forged").contentType("application/json").content(payload)).andReturn().getResponse();
        assertEquals(901,json.readTree(response.getContentAsString()).path("code").asInt());assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM aftersales_audit",Integer.class));assertEquals("AWAITING_USER",service.detail(user,(String)r.get("caseId")).get("state"));
    }
    @Test void amendmentCreatesNewDraftWithTypedMaterialsAndNeverSubmits(){
        var r=create(true);var oldVersion=r.get("planVersion");
        r=service.command(user,"AMEND",command(r,"{\"reason\":\"TEST broken\",\"materials\":[\"TEST photo reference\"],\"requestedType\":\"refund\"}"));
        assertEquals("AWAITING_USER",r.get("state"));assertEquals("HIGH",r.get("risk"));assertEquals("refund",r.get("requestedType"));assertEquals(((Number)oldVersion).longValue()+1,((Number)r.get("planVersion")).longValue());
        assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM aftersales_manual_task",Integer.class));
        r=service.command(user,"CONFIRM",command(r,"{\"reason\":\"TEST broken\",\"materials\":[\"TEST photo reference\"],\"requestedType\":\"refund\"}"));assertEquals("ADMIN_REVIEW",r.get("state"));
        var submitted=r;assertThrows(BusinessException.class,()->service.command(user,"AMEND",command(submitted,"TEST new reason")));
    }
    @Test void cancellationCancelsOnlyPendingCaseTaskAndReplayIsIdempotent(){
        var r=step(admin,"APPROVE",step(user,"CONFIRM",create(false)));var cmd=command(r,"TEST changed mind");
        r=service.command(user,"CANCEL",cmd);assertEquals("CANCELLED",r.get("state"));assertEquals("CANCELLED",jdbc.queryForObject("SELECT state FROM aftersales_manual_task",String.class));
        assertEquals(true,service.command(user,"CANCEL",cmd).get("replayed"));assertEquals(4,events(r).size());
        assertEquals("ARCHIVED",step(user,"ARCHIVE",r).get("state"));verify(orders,never()).updateOrderInfoByOrderId(any(),anyString());
    }
    @Test void cancellationAndAmendmentCannotCrossOwnershipOrInterruptActiveHandling(){
        var r=create(false);for(String a:List.of("AMEND","CANCEL")){
            assertThrows(BusinessException.class,()->service.command(new Actor("B",false),a,command(r,"TEST")));
            assertThrows(BusinessException.class,()->service.command(admin,a,command(r,"TEST")));
        }
        var active=active();assertThrows(BusinessException.class,()->service.command(user,"CANCEL",command(active,"TEST")));
    }
    @Test void requestedTypeCannotBeOverriddenByOldFulfillmentEndpoint(){
        var r=service.command(user,"CONFIRM",command(create(false),"{\"reason\":\"TEST\",\"materials\":[],\"requestedType\":\"return_refund\"}"));
        r=step(admin,"CLAIM",step(admin,"APPROVE",r));var current=r;ReflectionTestUtils.setField(service,"mockRefundEnabled",true);
        assertThrows(BusinessException.class,()->service.command(admin,"MOCK_REFUND",command(current,"{\"type\":\"refund\"}")));
        assertEquals("NOT_EXECUTED",((Map<?,?>)service.detail(user,(String)r.get("caseId")).get("fulfillment")).get("refundStatus"));
    }
    @Test void stagedRefundDefaultOffAndOwnerHandlerChecksPersistNoFalseProcessing(){
        var r=service.command(admin,"PREPARE_REFUND",command(active(),"{\"type\":\"refund\"}"));assertEquals("PENDING",((Map<?,?>)r.get("fulfillment")).get("refundStatus"));
        assertThrows(BusinessException.class,()->service.command(admin,"START_MOCK_REFUND",command(r,"{\"type\":\"refund\"}")));
        for(String a:List.of("PREPARE_REFUND","START_MOCK_REFUND","COMPLETE_MOCK_REFUND","TIMEOUT_MOCK_REFUND")){
            assertThrows(BusinessException.class,()->service.command(user,a,command(r,"{\"type\":\"refund\"}")));
            assertThrows(BusinessException.class,()->service.command(new Actor("other-admin",true),a,command(r,"{\"type\":\"refund\"}")));
        }
        assertEquals("PENDING",((Map<?,?>)service.detail(user,(String)r.get("caseId")).get("fulfillment")).get("refundStatus"));
    }
    @Test void stagedRefundTimeoutRequiresManualReconciliationAndRetryKeepsOriginalId() throws Exception {
        ReflectionTestUtils.setField(service,"mockRefundEnabled",true);var mvc=actualCaseHttp();var r=active();
        r=httpCommand(mvc,true,"prepareRefund",r,"{\"type\":\"refund\"}");String id=(String)((Map<?,?>)r.get("fulfillment")).get("refundId");
        r=httpCommand(mvc,true,"startMockRefund",r,"{\"type\":\"refund\"}");assertEquals("PROCESSING",((Map<?,?>)r.get("fulfillment")).get("refundStatus"));
        var processing=r;assertThrows(BusinessException.class,()->step(admin,"SUCCEED",processing));
        r=httpCommand(mvc,true,"timeoutMockRefund",r,"{\"type\":\"refund\",\"result\":\"TEST timeout\"}");assertEquals("UNKNOWN",((Map<?,?>)r.get("fulfillment")).get("refundStatus"));var unknown=r;
        assertThrows(BusinessException.class,()->service.command(admin,"PREPARE_REFUND",command(unknown,"{\"type\":\"refund\"}")));
        for(String flag:List.of("false","\"true\""))assertThrows(BusinessException.class,()->service.command(admin,"COMPLETE_MOCK_REFUND",command(unknown,"{\"type\":\"refund\",\"simulateFailure\":false,\"result\":\"TEST\",\"manualReconciliation\":"+flag+"}")));
        r=httpCommand(mvc,true,"completeMockRefund",r,"{\"type\":\"refund\",\"simulateFailure\":true,\"result\":\"TEST reconciled failure\",\"manualReconciliation\":true}");assertEquals("FAILED",((Map<?,?>)r.get("fulfillment")).get("refundStatus"));assertTrue(json.readTree((String)events(r).get(events(r).size()-1).get("note")).path("manualReconciliation").asBoolean());
        var failed=r;assertThrows(BusinessException.class,()->step(admin,"SUCCEED",failed));
        r=httpCommand(mvc,true,"prepareRefund",r,"{\"type\":\"refund\"}");r=httpCommand(mvc,true,"startMockRefund",r,"{\"type\":\"refund\"}");
        var completion=command(r,"{\"type\":\"refund\",\"simulateFailure\":false,\"result\":\"TEST success\"}");r=service.command(admin,"COMPLETE_MOCK_REFUND",completion);
        assertEquals(id,((Map<?,?>)r.get("fulfillment")).get("refundId"));assertEquals(2,((Map<?,?>)r.get("fulfillment")).get("attempt"));assertEquals(false,((Map<?,?>)r.get("fulfillment")).get("executionAllowed"));
        assertEquals(true,service.command(admin,"COMPLETE_MOCK_REFUND",completion).get("replayed"));var success=r;
        for(String a:List.of("START_MOCK_REFUND","PREPARE_REFUND","MOCK_REFUND"))assertThrows(BusinessException.class,()->service.command(admin,a,command(success,"{\"type\":\"refund\"}")));
        assertEquals("RESOLVED",step(admin,"SUCCEED",r).get("state"));
    }
    @Test void stagedReturnRefundRequiresReceiptAndPreservesAcceptanceEvidence(){
        ReflectionTestUtils.setField(service,"mockRefundEnabled",true);var r=active();r=service.command(admin,"PREPARE_REFUND",command(r,"{\"type\":\"return_refund\"}"));var pending=r;
        assertThrows(BusinessException.class,()->service.command(admin,"START_MOCK_REFUND",command(pending,"{\"type\":\"return_refund\"}")));
        r=service.command(user,"USER_RETURN_LOGISTICS",command(r,"{\"type\":\"return_refund\",\"carrier\":\"TEST\",\"trackingNo\":\"TEST12345\"}"));var tracked=r;
        assertThrows(BusinessException.class,()->service.command(admin,"RETURN_ACCEPT",command(tracked,"{\"type\":\"return_refund\",\"received\":false,\"accepted\":true,\"result\":\"TEST\"}")));
        r=service.command(admin,"RETURN_ACCEPT",command(r,"{\"type\":\"return_refund\",\"received\":true,\"condition\":\"INTACT\",\"accepted\":true,\"evidenceRefs\":[\"TEST warehouse receipt\"],\"result\":\"TEST checked\"}"));
        assertEquals("INTACT",((Map<?,?>)r.get("fulfillment")).get("returnCondition"));assertEquals("TEST warehouse receipt",((JsonNode)((Map<?,?>)r.get("fulfillment")).get("acceptanceEvidence")).get(0).asText());
        r=service.command(admin,"START_MOCK_REFUND",command(r,"{\"type\":\"return_refund\"}"));var processing=r;
        assertThrows(BusinessException.class,()->service.command(admin,"RETURN_ACCEPT",command(processing,"{\"type\":\"return_refund\",\"accepted\":false,\"result\":\"TEST override\"}")));
    }
    @Test void amendmentAndCancellationRoutesUseRealAuthenticationTransactionAndMapper() throws Exception {
        var mvc=actualCaseHttp();var r=create(false);r=httpCommand(mvc,false,"amend",r,"{\"reason\":\"TEST revised\",\"materials\":[],\"requestedType\":\"refund\"}");
        assertEquals("refund",r.get("requestedType"));r=httpCommand(mvc,false,"cancel",r,"TEST cancel draft");assertEquals("CANCELLED",r.get("state"));assertEquals(3,events(r).size());
    }
    @Test void explicitlyConfirmedRefundCannotBeClosedBeforeExecution(){
        var r=service.command(user,"CONFIRM",command(create(false),"{\"reason\":\"TEST\",\"materials\":[],\"requestedType\":\"refund\"}"));r=step(admin,"CLAIM",step(admin,"APPROVE",r));var pending=r;
        assertThrows(BusinessException.class,()->step(admin,"SUCCEED",pending));assertEquals("IN_PROGRESS",service.detail(user,(String)r.get("caseId")).get("state"));
    }
    @Test void exchangeApplicationIsManualOnlyAndNeverBecomesRefund() throws Exception {
        var mvc=actualCaseHttp();var r=create(false);r=httpCommand(mvc,false,"amend",r,"{\"reason\":\"TEST wrong size\",\"materials\":[],\"requestedType\":\"exchange\"}");
        r=httpCommand(mvc,false,"confirm",r,"{\"reason\":\"TEST wrong size\",\"materials\":[],\"requestedType\":\"exchange\"}");assertEquals("ADMIN_REVIEW",r.get("state"));
        r=httpCommand(mvc,true,"approve",r,"TEST manual exchange review");r=httpCommand(mvc,true,"claim",r,"TEST claim");var active=r;
        ReflectionTestUtils.setField(service,"mockRefundEnabled",true);
        for(String a:List.of("PREPARE_REFUND","MOCK_REFUND"))assertThrows(BusinessException.class,()->service.command(admin,a,command(active,"{\"type\":\"refund\"}")));
        assertThrows(BusinessException.class,()->service.command(admin,"PREPARE_REFUND",command(active,"{\"type\":\"exchange\"}")));
        r=httpCommand(mvc,true,"succeed",r,"TEST human exchange followup recorded; no money or shipment executed");assertEquals("RESOLVED",r.get("state"));assertEquals("NOT_EXECUTED",((Map<?,?>)r.get("fulfillment")).get("refundStatus"));
    }
    @SuppressWarnings("unchecked") private List<Map<String,Object>> events(Map<String,Object> row){return (List<Map<String,Object>>)row.get("timeline");}

    @Test void createAndIdempotentReplayPreserveOnePlanAndAudit(){
        var first=create(false);var second=create(false);assertEquals(first.get("caseId"),second.get("caseId"));assertEquals(true,second.get("replayed"));
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM aftersales_case",Integer.class));assertEquals(1,events(second).size());
        assertEquals("AWAITING_USER",first.get("state"));assertEquals(false,first.get("executionAllowed"));
    }
    @Test void sameSourceCannotOverwriteDiagnosis(){create(false);var altered=report(false);altered.put("extra","changed");assertThrows(BusinessException.class,()->service.create(user,1,altered));}
    @Test void ownCaseReadableOthersRejected(){var row=create(false);assertNotNull(service.detail(user,(String)row.get("caseId")));assertThrows(BusinessException.class,()->service.detail(new Actor("B",false),(String)row.get("caseId")));assertEquals(0,service.list(new Actor("B",false),null,1,20).size());}
    @Test void otherUsersOrderCannotCreate(){var r=report(false);r.put("orderId","O-B");((ObjectNode)r.path("orderFacts").path("data")).put("orderId","O-B");assertThrows(BusinessException.class,()->service.create(user,1,r));assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM aftersales_case",Integer.class));}
    @Test void userBReadsOwnCase(){var r=report(false);r.put("orderId","O-B");((ObjectNode)r.path("orderFacts").path("data")).put("orderId","O-B");var row=service.create(new Actor("B",false),2,r);assertEquals("O-B",service.detail(new Actor("B",false),(String)row.get("caseId")).get("orderId"));}
    @Test void lowRiskUserConfirmationCreatesOnlyManualTask(){var row=step(user,"CONFIRM",create(true));assertEquals("MANUAL_PENDING",row.get("state"));assertEquals("PENDING",jdbc.queryForObject("SELECT state FROM aftersales_manual_task",String.class));assertEquals(false,row.get("executionAllowed"));}
    @Test void highRiskCannotDowngradeByReportApprovalFlag(){var r=report(false);r.put("approvalRequired",false);var row=service.create(user,1,r);assertEquals("HIGH",row.get("risk"));row=step(user,"CONFIRM",row);assertEquals("ADMIN_REVIEW",row.get("state"));assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM aftersales_manual_task",Integer.class));}
    @Test void administratorApprovalCreatesPendingTask(){var row=step(admin,"APPROVE",step(user,"CONFIRM",create(false)));assertEquals("MANUAL_PENDING",row.get("state"));assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM aftersales_manual_task",Integer.class));}
    @Test void rejectionAndResubmissionVersionCannotBypassUserOrAdmin(){var row=step(admin,"REJECT",step(user,"CONFIRM",create(false)));assertEquals("REJECTED",row.get("state"));row=step(user,"RESUBMIT",row);assertEquals(2L,row.get("planVersion"));assertEquals("AWAITING_USER",row.get("state"));assertEquals(2,jdbc.queryForObject("SELECT COUNT(*) FROM aftersales_plan",Integer.class));assertEquals("ADMIN_REVIEW",step(user,"CONFIRM",row).get("state"));}
    @ParameterizedTest @ValueSource(strings={"APPROVE","REJECT","CLAIM","SUCCEED","FAIL","RETRY"}) void nonAdminCannotUseAdministrativeCommands(String action){var row=create(false);assertThrows(BusinessException.class,()->service.command(user,action,command(row,"note")));assertEquals(1,events(service.detail(user,(String)row.get("caseId"))).size());}
    @Test void adminCannotConfirmForUser(){var row=create(false);assertThrows(BusinessException.class,()->step(admin,"CONFIRM",row));}
    @ParameterizedTest @ValueSource(strings={"APPROVE","REJECT","CLAIM","SUCCEED","FAIL","RETRY","ARCHIVE","RESUBMIT","REFUND"}) void illegalStateChangesRejected(String action){var row=create(false);Actor who=action.equals("RESUBMIT")?user:admin;assertThrows(BusinessException.class,()->step(who,action,row));}
    @Test void duplicateCommandIsReplayButDifferentPayloadRejected(){var row=create(false);var cmd=command(row,"TEST application reason");var next=service.command(user,"CONFIRM",cmd);assertEquals(true,service.command(user,"CONFIRM",cmd).get("replayed"));assertEquals(2,events(next).size());assertThrows(BusinessException.class,()->service.command(user,"CONFIRM",new Command(cmd.caseId(),cmd.expectedVersion(),cmd.requestId(),"changed")));}
    @Test void staleVersionCannotMoveState(){var row=create(false);step(user,"CONFIRM",row);assertThrows(BusinessException.class,()->step(user,"CONFIRM",row));}
    @Test void successAndArchiveHaveCompleteTimeline(){var row=step(admin,"APPROVE",step(user,"CONFIRM",create(false)));row=step(admin,"CLAIM",row);row=step(admin,"SUCCEED",row);assertEquals("RESOLVED",row.get("state"));row=step(user,"ARCHIVE",row);assertEquals("ARCHIVED",row.get("state"));assertEquals(List.of("CREATE","CONFIRM","APPROVE","CLAIM","SUCCEED","ARCHIVE"),events(row).stream().map(e->e.get("action")).toList());assertNotNull(jdbc.queryForObject("SELECT finished_at FROM aftersales_manual_task",java.sql.Timestamp.class));}
    @Test void failureReasonAndRetryAreRetained(){var row=step(admin,"CLAIM",step(user,"CONFIRM",create(true)));row=step(admin,"FAIL",row);assertEquals("PROCESSING_FAILED",row.get("state"));row=step(admin,"RETRY",row);assertEquals("MANUAL_PENDING",row.get("state"));assertEquals(2,jdbc.queryForObject("SELECT COUNT(*) FROM aftersales_manual_task",Integer.class));assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM aftersales_manual_task WHERE state='FAILED' AND result_note IS NOT NULL",Integer.class));}
    @Test void onlyAssignedHandlerCanFinish(){var row=step(admin,"CLAIM",step(user,"CONFIRM",create(true)));assertThrows(BusinessException.class,()->step(new Actor("admin-other",true),"SUCCEED",row));}
    @Test void emptyFailureReasonRejected(){var row=step(admin,"CLAIM",step(user,"CONFIRM",create(true)));assertThrows(BusinessException.class,()->service.command(admin,"FAIL",command(row,"")));}
    @Test void planUsesServerLabelsAndKeepsPolicyEvidence(){var row=create(true);String content=mapper.planContent((String)row.get("caseId"),1);assertFalse(content.contains("UNTRUSTED"));assertTrue(content.contains("fixture://test"));assertTrue(content.contains("executionAllowed\":false"));}
    @Test void auditFailureRollsBackTaskAndState(){
        var row=step(user,"CONFIRM",create(false));
        AftersalesCaseMapper failing=(AftersalesCaseMapper)Proxy.newProxyInstance(getClass().getClassLoader(),new Class[]{AftersalesCaseMapper.class},(p,m,a)->{
            if(m.getName().equals("audit")&&"APPROVE".equals(((Map<?,?>)a[0]).get("action")))throw new IllegalStateException("test audit outage");
            try{return m.invoke(mapper,a);}catch(InvocationTargetException e){throw e.getCause();}
        });
        assertThrows(IllegalStateException.class,()->proxied(failing).command(admin,"APPROVE",command(row,"note")));
        assertEquals("ADMIN_REVIEW",service.detail(user,(String)row.get("caseId")).get("state"));assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM aftersales_manual_task",Integer.class));
    }
    @Test void concurrentVersionsOnlyOneWins() throws Exception {
        var row=create(false);var start=new CountDownLatch(1);var pool=Executors.newFixedThreadPool(2);
        try{var jobs=new ArrayList<Future<Boolean>>();for(int i=0;i<2;i++)jobs.add(pool.submit(()->{start.await();try{step(user,"CONFIRM",row);return true;}catch(BusinessException e){return false;}}));start.countDown();int successes=0;for(var job:jobs)if(job.get(15,TimeUnit.SECONDS))successes++;assertEquals(1,successes);assertEquals(2,events(service.detail(user,(String)row.get("caseId"))).size());}finally{pool.shutdownNow();}
    }
    @Test void concurrentCreateIsIdempotent() throws Exception {
        var pool=Executors.newFixedThreadPool(2);try{var first=pool.submit(()->create(false));var second=pool.submit(()->create(false));assertEquals(first.get(15,TimeUnit.SECONDS).get("caseId"),second.get(15,TimeUnit.SECONDS).get("caseId"));assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM aftersales_audit",Integer.class));}finally{pool.shutdownNow();}
    }
    @Test void concurrentDuplicateApprovalCreatesExactlyOneTask() throws Exception {
        var row=step(user,"CONFIRM",create(false));var request=command(row,"TEST ONLY approval");var pool=Executors.newFixedThreadPool(2);
        try{var first=pool.submit(()->service.command(admin,"APPROVE",request));var second=pool.submit(()->service.command(admin,"APPROVE",request));
            var a=first.get(15,TimeUnit.SECONDS);var b=second.get(15,TimeUnit.SECONDS);assertEquals("MANUAL_PENDING",a.get("state"));assertEquals("MANUAL_PENDING",b.get("state"));
            assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM aftersales_manual_task",Integer.class));assertEquals(3,events(service.detail(user,(String)row.get("caseId"))).size());
        }finally{pool.shutdownNow();}
    }
    @Test void creationAuditFailureLeavesNoHalfCreatedCase(){
        AftersalesCaseMapper failing=(AftersalesCaseMapper)Proxy.newProxyInstance(getClass().getClassLoader(),new Class[]{AftersalesCaseMapper.class},(p,m,a)->{
            if(m.getName().equals("audit"))throw new IllegalStateException("test audit outage");
            try{return m.invoke(mapper,a);}catch(InvocationTargetException e){throw e.getCause();}
        });
        assertThrows(IllegalStateException.class,()->proxied(failing).create(user,1,report(false)));
        assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM aftersales_case",Integer.class));assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM aftersales_plan",Integer.class));
    }
    @Test void migrationDoesNotContainDestructiveOrBusinessStatements() throws Exception {
        Path root=Path.of("").toAbsolutePath();while(!Files.exists(root.resolve("sql/09_aftersales_cases.sql")))root=root.getParent();
        String sql=Files.readString(root.resolve("sql/09_aftersales_cases.sql")).replaceAll("(?m)^--.*$","").toUpperCase(Locale.ROOT);
        assertFalse(sql.matches("(?s).*\\b(DROP|TRUNCATE|DELETE|ALTER|INSERT)\\b.*"));
    }
}
