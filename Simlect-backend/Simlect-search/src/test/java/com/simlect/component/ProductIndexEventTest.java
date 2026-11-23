package com.simlect.component;

import com.rabbitmq.client.Channel;
import com.simlect.api.support.ProductFeignSupport;
import com.simlect.api.vo.ProductRagIndexVO;
import com.simlect.entity.dto.RagDataDTO;
import com.simlect.entity.enums.RagDataTypeEnum;
import org.elasticsearch.client.RestClient;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.test.util.ReflectionTestUtils;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class ProductIndexEventTest {
    @Mock EsSearchComponent esSearchComponent;
    @Mock ProductFeignSupport productFeignSupport;
    @Mock VectorStore vectorStore;
    @Mock RestClient restClient;
    @Mock MqListenerHelper mqListenerHelper;
    @Mock MqConsumeFailureRecorder mqConsumeFailureRecorder;
    @Mock Channel channel;
    @InjectMocks RabbitMQRagListenerComponent listener;

    Message message() {
        MessageProperties p = new MessageProperties(); p.setDeliveryTag(23);
        return new Message(new byte[0],p);
    }

    @Test void productEventRefreshesBothIndexesBeforeAck() throws Exception {
        Message m=message(); when(mqListenerHelper.tryBeginConsume(eq(m),anyLong())).thenReturn(true);
        ProductRagIndexVO product=new ProductRagIndexVO();product.setProductName("SYNTHETIC TEST ONLY");product.setStatus(1);
        when(productFeignSupport.getRagIndex("TEST_P1")).thenReturn(product);
        ReflectionTestUtils.setField(listener,"indexName","test-index-only");
        listener.handleRagData(new RagDataDTO("TEST_P1",RagDataTypeEnum.PRODUCT.getType()),channel,m);
        var order=inOrder(esSearchComponent,vectorStore,channel);
        order.verify(esSearchComponent).saveIndex("TEST_P1");
        order.verify(vectorStore).add(anyList());
        order.verify(channel).basicAck(23,false);
    }

    @Test void keywordIndexFailureRetriesWithoutCallingEmbedding() throws Exception {
        Message m=message();when(mqListenerHelper.tryBeginConsume(eq(m),anyLong())).thenReturn(true);
        doThrow(new IllegalStateException("TEST ES unavailable")).when(esSearchComponent).saveIndex("TEST_P1");
        RagDataDTO dto=new RagDataDTO("TEST_P1",RagDataTypeEnum.PRODUCT.getType());
        listener.handleRagData(dto,channel,m);
        verifyNoInteractions(vectorStore);
        verify(channel,never()).basicAck(anyLong(),anyBoolean());
        verify(mqListenerHelper).nackWithRetryOrDlq(eq(channel),eq(23L),eq(m),anyString(),eq(dto),any(Exception.class));
    }
}
