package com.simlect.controller.internal;

import com.simlect.api.support.ProductFeignSupport;
import com.simlect.biz.RagQuestionService;
import com.simlect.component.EsSearchComponent;
import com.simlect.component.RedisComponent;
import com.simlect.constants.RabbitMQConfig;
import com.simlect.constants.ReliableMessageSender;
import com.simlect.entity.po.RagQuestion;
import com.simlect.utils.AuthCookieHelper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
class SearchToolInternalControllerTest {
    @Test void keywordRefreshNeverQueuesEmbeddingAndRejectsInvalidIdentity(){
        org.springframework.test.util.ReflectionTestUtils.setField(searchToolInternalController,"internalToken","ISOLATED-TEST-INTERNAL");
        org.junit.jupiter.api.Assertions.assertThrows(com.simlect.exception.BusinessException.class,()->searchToolInternalController.refreshKeywordIndex("bad",java.util.Map.of("productIds",List.of("P1"))));
        searchToolInternalController.refreshKeywordIndex("ISOLATED-TEST-INTERNAL",java.util.Map.of("productIds",List.of("P1")));
        verify(esSearchComponent).saveIndex("P1");verifyNoInteractions(reliableMessageSender,ragQuestionService);
    }
    @Test void keywordRefreshRejectsDuplicatesAndOversizedBatches(){
        org.springframework.test.util.ReflectionTestUtils.setField(searchToolInternalController,"internalToken","ISOLATED-TEST-INTERNAL");
        for(var ids:List.of(List.<String>of(),List.of("P1","P1"),java.util.Collections.nCopies(51,"P1"))){
            org.junit.jupiter.api.Assertions.assertThrows(com.simlect.exception.BusinessException.class,()->searchToolInternalController.refreshKeywordIndex("ISOLATED-TEST-INTERNAL",java.util.Map.of("productIds",ids)));
        }
        verifyNoInteractions(esSearchComponent,reliableMessageSender);
    }

    @Mock
    private RedisComponent redisComponent;
    @Mock
    private AuthCookieHelper authCookieHelper;
    @Mock
    private EsSearchComponent esSearchComponent;
    @Mock
    private ProductFeignSupport productFeignSupport;
    @Mock
    private RagQuestionService ragQuestionService;
    @Mock
    private ReliableMessageSender reliableMessageSender;

    @InjectMocks
    private SearchToolInternalController searchToolInternalController;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.standaloneSetup(searchToolInternalController)
                .setControllerAdvice(new com.simlect.controller.AGlobalExceptionHandlerController())
                .build();
    }

    @Test
    void productData_indexesAllAndQueuesRag() throws Exception {
        when(productFeignSupport.listOnSaleProductIds()).thenReturn(List.of("P1", "P2"));

        mockMvc.perform(post("/internal/search/tool/productData"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("success"));

        verify(esSearchComponent).saveIndex("P1");
        verify(esSearchComponent).saveIndex("P2");
        verify(reliableMessageSender, times(2)).sendMessage(eq(RabbitMQConfig.RAG_EXCHANGE),
                eq(RabbitMQConfig.RAG_QUEUE_KEY), any(), anyString(), any());
    }

    @Test
    void ragData_queuesAllFaq() throws Exception {
        RagQuestion q1 = new RagQuestion();
        q1.setQuestionId(1);
        RagQuestion q2 = new RagQuestion();
        q2.setQuestionId(2);
        when(ragQuestionService.findListByParam(null)).thenReturn(List.of(q1, q2));

        mockMvc.perform(post("/internal/search/tool/ragData"))
                .andExpect(status().isOk());

        verify(reliableMessageSender, times(2)).sendMessage(eq(RabbitMQConfig.RAG_EXCHANGE),
                eq(RabbitMQConfig.RAG_QUEUE_KEY), any(), anyString(), any());
    }

    @Test
    void ragData_noQuestions_noMq() throws Exception {
        when(ragQuestionService.findListByParam(null)).thenReturn(null);

        mockMvc.perform(post("/internal/search/tool/ragData"))
                .andExpect(status().isOk());

        verifyNoInteractions(reliableMessageSender);
    }
}
