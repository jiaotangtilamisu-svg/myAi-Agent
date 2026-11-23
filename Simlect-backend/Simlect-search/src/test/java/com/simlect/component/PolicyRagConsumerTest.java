package com.simlect.component;

import com.simlect.biz.KnowledgeDocumentService;
import com.simlect.entity.dto.RagDataDTO;
import com.rabbitmq.client.Channel;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

@ExtendWith(MockitoExtension.class)
class PolicyRagConsumerTest {
    @Mock KnowledgeDocumentService knowledgeDocumentService;
    @Mock MqListenerHelper mqListenerHelper;
    @Mock MqConsumeFailureRecorder mqConsumeFailureRecorder;
    @Mock Channel channel;
    @InjectMocks RabbitMQRagListenerComponent listener;
    Message message(){MessageProperties p=new MessageProperties();p.setDeliveryTag(42);return new Message(new byte[0],p);}
    @Test void existingConsumerDispatchesPolicyAndAcks()throws Exception {
        Message m=message();when(mqListenerHelper.tryBeginConsume(eq(m),anyLong())).thenReturn(true);
        listener.handleRagData(new RagDataDTO("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","aftersales_policy"),channel,m);
        verify(knowledgeDocumentService).synchronize("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");verify(channel).basicAck(42,false);
    }
    @Test void embeddingOrEsFailureUsesExistingRetryAndDlq()throws Exception {
        Message m=message();when(mqListenerHelper.tryBeginConsume(eq(m),anyLong())).thenReturn(true);
        doThrow(new RuntimeException("Mock embedding failure")).when(knowledgeDocumentService).synchronize(anyString());
        RagDataDTO dto=new RagDataDTO("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","aftersales_policy");
        listener.handleRagData(dto,channel,m);
        verify(mqListenerHelper).nackWithRetryOrDlq(eq(channel),eq(42L),eq(m),anyString(),eq(dto),any(Exception.class));
        verify(channel,never()).basicAck(anyLong(),anyBoolean());
    }
}
