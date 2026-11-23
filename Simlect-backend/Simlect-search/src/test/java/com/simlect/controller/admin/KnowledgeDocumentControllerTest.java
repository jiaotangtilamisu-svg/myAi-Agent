package com.simlect.controller.admin;

import com.simlect.biz.KnowledgeDocumentService;
import com.simlect.component.RedisComponent;
import com.simlect.utils.AuthCookieHelper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.multipart.MultipartFile;
import java.util.List;
import static org.mockito.Mockito.*;
import static org.junit.jupiter.api.Assertions.*;

@ExtendWith(MockitoExtension.class)
class KnowledgeDocumentControllerTest {
    @Mock KnowledgeDocumentService service;
    @Mock RedisComponent redisComponent;
    @Mock AuthCookieHelper authCookieHelper;
    @InjectMocks KnowledgeDocumentController controller;
    @Test void missingAdminSessionCannotManageDocuments() {
        MockHttpServletRequest request=new MockHttpServletRequest();
        assertThrows(RuntimeException.class,()->controller.list(request,1,20));verifyNoInteractions(service);
    }
    @Test void authenticatedAdminUsesExistingManagementService() {
        MockHttpServletRequest r=new MockHttpServletRequest();when(authCookieHelper.resolveAdminToken(r)).thenReturn("test-only");when(redisComponent.getLoginInfo4Admin("test-only")).thenReturn(new Object());
        when(service.list(1,20)).thenReturn(List.of());assertEquals(200,controller.list(r,1,20).getCode());verify(service).list(1,20);
    }
    @Test void oversizedFileRejectedBeforeReadingBytes()throws Exception {
        MockHttpServletRequest r=new MockHttpServletRequest();when(authCookieHelper.resolveAdminToken(r)).thenReturn("test-only");when(redisComponent.getLoginInfo4Admin("test-only")).thenReturn(new Object());
        MultipartFile f=mock(MultipartFile.class);when(f.getSize()).thenReturn(11L*1024*1024);
        assertThrows(RuntimeException.class,()->controller.importFile(r,f,"TEST","fixture://test",null,null));verify(f,never()).getBytes();verifyNoInteractions(service);
    }
    @Test void unauthenticatedCannotTransitionReviewEnableOrDisable(){
        for(String action:List.of("submit","approve","reject","enable","disable")) {
            assertThrows(RuntimeException.class,()->controller.transition(new MockHttpServletRequest(),"test-id",1,action));
        }
        verifyNoInteractions(service);
    }
    @Test void unauthenticatedCannotPublishEditReadSourceOrReadHistory(){
        MockHttpServletRequest r=new MockHttpServletRequest();
        assertThrows(RuntimeException.class,()->controller.publish(r,"test-id",1,true));
        assertThrows(RuntimeException.class,()->controller.metadata(r,"test-id",1));
        assertThrows(RuntimeException.class,()->controller.original(r,"test-id",1));
        assertThrows(RuntimeException.class,()->controller.version(r,"test-id",1));
        assertThrows(RuntimeException.class,()->controller.reindex(r,"test-id",1));
        assertThrows(RuntimeException.class,()->controller.delete(r,"test-id",1));
        verifyNoInteractions(service);
    }
    @Test void actorIsDerivedFromServerSessionNotRequestParameter(){
        MockHttpServletRequest r=new MockHttpServletRequest();r.setParameter("actor","forged-admin");
        when(authCookieHelper.resolveAdminToken(r)).thenReturn("fixture-session");
        when(redisComponent.getLoginInfo4Admin("fixture-session")).thenReturn("fixture-account");
        controller.transition(r,"test-id",1,"approve");
        verify(service).transition(eq("test-id"),eq(1L),eq("approve"),argThat(a->a.startsWith("admin:")&&!a.contains("fixture")&&!a.contains("forged")));
    }
}
