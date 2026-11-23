package com.simlect.controller.internal;

import com.fasterxml.jackson.databind.*;
import com.simlect.biz.ProductAgentQueryService;
import com.simlect.mappers.*;
import org.junit.jupiter.api.*;
import org.mybatis.spring.*;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;
import org.springframework.web.servlet.DispatcherServlet;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
import org.springframework.context.annotation.Configuration;
import org.apache.catalina.startup.Tomcat;
import java.nio.file.*;
import java.net.*;
import java.net.http.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

/** Opt-in actual loopback HTTP→Spring MVC→production Controller→MyBatis→MySQL.
 * Internal auth/Gateway tested separately; this narrow fixture does not impersonate them. */
class ProductCatalogMySqlHttpIT {
 @Configuration @EnableWebMvc static class WebConfig {}
 @Test void semanticQueriesUseRealSqlThroughHttp() throws Exception {
  String schema=System.getenv("QUALITY_MYSQL_SCHEMA");assertNotNull(schema);
  assertTrue(schema.matches("simlect_quality33_[a-f0-9]{12}"));
  var ds=new DriverManagerDataSource("jdbc:mysql://127.0.0.1:13306/"+schema+"?useUnicode=true&characterEncoding=utf-8&useSSL=false&serverTimezone=Asia/Shanghai","root",System.getenv("QUALITY_MYSQL_PASSWORD"));
  var factory=new SqlSessionFactoryBean();factory.setDataSource(ds);
  var resources=new PathMatchingResourcePatternResolver();
  factory.setMapperLocations(resources.getResource("classpath:com/simlect/mappers/ProductInfoMapper.xml"),resources.getResource("classpath:com/simlect/mappers/ProductSkuMapper.xml"),resources.getResource("classpath:com/simlect/mappers/ProductPropertyValueMapper.xml"));
  var session=new SqlSessionTemplate(factory.getObject());
  var controller=new ProductAgentInternalController();
  ReflectionTestUtils.setField(controller,"productInfoMapper",session.getMapper(ProductInfoMapper.class));
  ReflectionTestUtils.setField(controller,"productSkuMapper",session.getMapper(ProductSkuMapper.class));
  ReflectionTestUtils.setField(controller,"productPropertyValueMapper",session.getMapper(ProductPropertyValueMapper.class));
  ReflectionTestUtils.setField(controller,"productAgentQueryService",new ProductAgentQueryService()); // Not used by searchOnSale.
  var mvc=new AnnotationConfigWebApplicationContext();mvc.register(WebConfig.class);
  var tomcat=new Tomcat();tomcat.setPort(0);tomcat.getConnector().setProperty("address","127.0.0.1");
  Path base=Files.createTempDirectory("simlect-quality33-tomcat-");tomcat.setBaseDir(base.toString());
  var ctx=tomcat.addContext("",base.toString());ctx.setParentClassLoader(getClass().getClassLoader());
  mvc.setServletContext(ctx.getServletContext());mvc.refresh();
  mvc.getBeanFactory().registerSingleton("productAgentInternalController",controller);
  mvc.getBean(org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping.class).afterPropertiesSet();
  Tomcat.addServlet(ctx,"quality",new DispatcherServlet(mvc)).setLoadOnStartup(1);ctx.addServletMappingDecoded("/","quality");
  var mapper=new ObjectMapper();List<Map<String,Object>> evidence=new ArrayList<>();
  try {
   tomcat.start();int port=tomcat.getConnector().getLocalPort();
   Map<String,String> queries=new LinkedHashMap<>();
   queries.put("苹果手机","QA");queries.put("Apple手机","QA");queries.put("iPhone","QA");queries.put("苹果256G","QA");
   queries.put("三星手机","QS");queries.put("Samsung手机","QS");queries.put("Galaxy手机","QS");queries.put("华为手机","QH");queries.put("OPPO手机","QO");
   var client=HttpClient.newHttpClient();
   for(var q:queries.entrySet()){
    var request=HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+"/internal/product/agent/searchOnSale")).header("Content-Type","application/json").POST(HttpRequest.BodyPublishers.ofString(mapper.writeValueAsString(Map.of("keyword",q.getKey(),"limit",20)))).build();
    var response=client.send(request,HttpResponse.BodyHandlers.ofString());assertEquals(200,response.statusCode());
    var json=mapper.readTree(response.body());assertEquals(200,json.path("code").asInt());
    List<String> ids=new ArrayList<>();json.path("data").forEach(row->ids.add(row.path("productId").asText()));
    assertEquals(List.of(q.getValue()),ids,q.getKey());
    evidence.add(Map.of("query",q.getKey(),"ids",ids,"http",response.statusCode()));
   }
   assertEquals(6,new JdbcTemplate(ds).queryForObject("SELECT COUNT(*) FROM product_info",Integer.class));
   Files.writeString(Path.of(System.getenv("QUALITY_HTTP_EVIDENCE")),mapper.writeValueAsString(evidence));
  } finally {tomcat.stop();tomcat.destroy();mvc.close();}
 }
}
