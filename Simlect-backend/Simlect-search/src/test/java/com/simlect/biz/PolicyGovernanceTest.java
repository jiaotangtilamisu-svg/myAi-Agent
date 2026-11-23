package com.simlect.biz;

import com.simlect.entity.po.KnowledgeDocument;
import com.simlect.mappers.KnowledgeDocumentMapper;
import com.simlect.constants.ReliableMessageSender;
import org.springframework.ai.vectorstore.VectorStore;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import java.time.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

@ExtendWith(MockitoExtension.class)
class PolicyGovernanceTest {
    static final String ID="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
    @Mock KnowledgeDocumentMapper mapper;
    @Mock ReliableMessageSender sender;
    @Mock VectorStore vectorStore;
    @InjectMocks KnowledgeDocumentService service;
    KnowledgeDocument d;
    @BeforeEach void setup(){d=new KnowledgeDocument();d.setDocumentId(ID);d.setRevision(1);d.setTitle("TEST ONLY 演示");d.setSource("fixture://test");d.setState("DRAFT");d.setSourceStatus("VALID");d.setEffectiveFrom(LocalDateTime.now(ZoneOffset.UTC).minusDays(1));}
    void lock(){when(mapper.lock(ID)).thenReturn(d);}
    void reviewed(){d.setApproved(true);d.setReviewedRevision(1);d.setReviewedBy("admin:test");}
    void published(){reviewed();d.setState("PUBLISHED");d.setIndexState("READY");d.setIndexedRevision(1);}
    @Test void draftCannotPublishEvenWithConfirmedTrue(){lock();assertThrows(RuntimeException.class,()->service.publish(ID,1,true));verifyNoInteractions(sender,vectorStore);}
    @Test void submitReviewApprovePublishAreSeparateSteps(){lock();service.transition(ID,1,"submit","admin:test");assertFalse(d.isApproved());assertEquals("PENDING_REVIEW",d.getState());service.transition(ID,1,"approve","admin:reviewer");assertTrue(d.isApproved());assertEquals("PENDING_REVIEW",d.getState());verifyNoInteractions(sender);service.publishManaged(ID,1,true,"admin:publisher");assertEquals("PUBLISHED",d.getState());assertEquals("INDEXING",d.getIndexState());verify(mapper,atLeast(3)).audit(eq(ID),eq(1L),anyString(),anyString(),anyString(),anyString(),anyString());}
    @Test void rejectedPolicyCannotPublish(){lock();d.setState("PENDING_REVIEW");service.transition(ID,1,"reject","admin:test");assertEquals("DRAFT",d.getState());assertThrows(RuntimeException.class,()->service.publish(ID,1,true));}
    @Test void revisionConflictRejectedBeforeWrites(){lock();assertThrows(RuntimeException.class,()->service.transition(ID,2,"submit","admin:test"));verify(mapper,never()).update(any());}
    @Test void repeatApproveRejected(){lock();d.setState("PENDING_REVIEW");service.transition(ID,1,"approve","admin:test");assertThrows(RuntimeException.class,()->service.transition(ID,1,"approve","admin:test"));}
    @Test void disableEnablePreservesVersionAndDoesNotDeleteVectors(){published();lock();service.transition(ID,1,"disable","admin:test");assertFalse(PolicyRules.retrievable(d,null));assertEquals(1,d.getRevision());service.transition(ID,1,"enable","admin:test");assertTrue(PolicyRules.retrievable(d,null));verifyNoInteractions(vectorStore,sender);verify(mapper,never()).saveOriginal(anyString(),anyLong(),any());}
    @Test void expiredPolicyCannotEnable(){published();d.setState("DISABLED");d.setEffectiveUntil(LocalDateTime.now(ZoneOffset.UTC).minusMinutes(1));lock();assertThrows(RuntimeException.class,()->service.transition(ID,1,"enable","admin:test"));}
    @Test void futurePolicyExcluded(){published();d.setEffectiveFrom(LocalDateTime.now(ZoneOffset.UTC).plusDays(1));assertFalse(PolicyRules.retrievable(d,null));}
    @Test void reviewedOldVersionCannotEnable(){published();d.setState("DISABLED");d.setRevision(2);lock();assertThrows(RuntimeException.class,()->service.transition(ID,2,"enable","admin:test"));}
    @Test void industryReferenceNeverDefaultBusinessPolicy(){published();d.setCategory("INDUSTRY_REFERENCE");assertFalse(PolicyRules.retrievable(d,null));assertTrue(PolicyRules.retrievable(d,"INDUSTRY_REFERENCE"));assertFalse(PolicyRules.retrievable(d,"LAW"));}
    @Test void lawRequiresAuthorityUrlAndPublicationDate(){d.setCategory("LAW");assertThrows(RuntimeException.class,()->PolicyRules.validate(d));d.setIssuer("TEST ONLY");d.setPublishedOn(LocalDate.of(2020,1,1));d.setOriginalUrl("https://example.invalid/test-law");assertDoesNotThrow(()->PolicyRules.validate(d));}
    @Test void invalidIntervalRejected(){d.setEffectiveUntil(d.getEffectiveFrom());assertThrows(RuntimeException.class,()->PolicyRules.validate(d));}
    @Test void jdReferenceCannotBePublishedAsShopRule(){d.setOriginalUrl("https://help.jd.com/test-only");assertThrows(RuntimeException.class,()->PolicyRules.validate(d));d.setCategory("INDUSTRY_REFERENCE");d.setIssuer("TEST ONLY");d.setPublishedOn(LocalDate.of(2020,1,1));assertDoesNotThrow(()->PolicyRules.validate(d));}
    @Test void invalidSourceExcludedEvenWhenIndexed(){published();d.setSourceStatus("INVALID");assertFalse(PolicyRules.retrievable(d,null));}
    @Test void retireKeepsOriginalAndVersions(){published();lock();service.delete(ID,1);assertEquals("RETIRED",d.getState());verifyNoInteractions(vectorStore,sender);verify(mapper,never()).saveOriginal(anyString(),anyLong(),any());}
    @Test void arbitraryActionCannotSetPublishedOrApproval(){lock();assertThrows(RuntimeException.class,()->service.transition(ID,1,"PUBLISHED","admin:test"));verify(mapper,never()).update(any());}
    @Test void disabledNotEligibleEvenIfVectorsRemain(){published();d.setState("DISABLED");when(mapper.get(ID)).thenReturn(d);assertTrue(service.approvedCatalog(List.of(ID)).isEmpty());verifyNoInteractions(vectorStore);}
}
