package com.simlect.component;
import com.simlect.api.support.ProductQueryIntent;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class ProductLexicalQueryTest {
 @Test void exportExactJavaQueriesForOptInRealEsTest() throws Exception {
  String path=System.getenv("QUALITY_ES_EXPORT");if(path==null)return;
  var rows=new LinkedHashMap<String,Object>();
  for(String q:List.of("苹果","苹果手机","Apple手机","iPhone","苹果256G","三星手机","Samsung手机","Galaxy手机","华为手机","OPPO手机","不存在型号","手机壳"))rows.put(q,new ObjectMapper().readTree(ProductLexicalQuery.json(q)));
  java.nio.file.Files.writeString(java.nio.file.Path.of(path),new ObjectMapper().writeValueAsString(rows));
 }
 @Test void conceptsAreConjunctiveAliasesAreDisjunctive() throws Exception {
  var groups=ProductQueryIntent.groups("Apple手机256G");assertEquals(3,groups.size());
  assertTrue(groups.stream().anyMatch(g->g.contains("苹果")&&g.contains("iphone")));
  var q=new ObjectMapper().readTree(ProductLexicalQuery.json("Apple手机256G"));
  assertEquals(3,q.path("bool").path("must").size());
  for(var must:q.path("bool").path("must"))assertEquals(1,must.path("bool").path("minimum_should_match").asInt());
 }
 @Test void semanticAliasesShareConcepts(){
  assertEquals(ProductQueryIntent.groups("三星手机"),ProductQueryIntent.groups("Samsung手机"));
  assertEquals(ProductQueryIntent.groups("小米手机"),ProductQueryIntent.groups("Redmi手机"));
  assertEquals(ProductQueryIntent.groups("苹果256G"),ProductQueryIntent.groups("Apple256GB"));
 }
 @Test void titlePrefixIsEvidenceButCompatibilityIsNot(){
  assertEquals("三星",ProductQueryIntent.brandEvidence("[全新]Samsung Galaxy S24 手机",List.of()).get("value"));
  assertTrue(ProductQueryIntent.brandEvidence("通用手机壳适用苹果三星",List.of()).isEmpty());
  assertTrue(ProductQueryIntent.brandEvidence("Apple compatible 通用手机壳",List.of()).isEmpty());
  assertEquals("三星",ProductQueryIntent.brandEvidence("三星Galaxy Z Flip8 手机",List.of()).get("value"));
  assertTrue(ProductQueryIntent.brandEvidence("苹果味果汁",List.of()).isEmpty());
  assertTrue(ProductQueryIntent.brandEvidence("Apple 手机",List.of("三星","苹果")).isEmpty());
  assertEquals("三星",ProductQueryIntent.brandEvidence("名称待确认",List.of("Samsung")).get("value"));
 }
 @Test void wildcardCharactersRemainLiteralAndInputBounded(){
  assertTrue(ProductQueryIntent.sqlGroups("100%_手机").stream().flatMap(Collection::stream).anyMatch(v->v.contains("!%")));
  assertThrows(IllegalArgumentException.class,()->ProductQueryIntent.groups("a".repeat(201)));
 }
}
