package com.simlect.biz;
import com.simlect.mappers.KnowledgeDocumentMapper;
import org.apache.ibatis.session.Configuration;
import org.apache.ibatis.type.ByteArrayTypeHandler;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
class PolicyOriginalMappingTest {
 @Test void blobIsMappedAsSingleDocumentNotPrimitiveRows(){
  Configuration c=new Configuration();c.addMapper(KnowledgeDocumentMapper.class);
  var map=c.getMappedStatement(KnowledgeDocumentMapper.class.getName()+".originalContent").getResultMaps().get(0);
  assertEquals(KnowledgeDocumentMapper.OriginalContent.class,map.getType());
  assertInstanceOf(ByteArrayTypeHandler.class,map.getResultMappings().get(0).getTypeHandler());
 }
 @Test void originalContractPreservesExactUtf8Bytes(){
  byte[] bytes="第一条 中文法规\nUTF8二进制".getBytes(java.nio.charset.StandardCharsets.UTF_8);
  var mapper=mock(KnowledgeDocumentMapper.class,CALLS_REAL_METHODS);
  var content=new KnowledgeDocumentMapper.OriginalContent();content.setBytes(bytes);
  when(mapper.originalContent("test-only",1L)).thenReturn(content);
  assertArrayEquals(bytes,mapper.original("test-only",1L));
  assertNull(mapper.original("missing",1L));
 }
}
