package com.simlect.biz;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.simlect.constants.ReliableMessageSender;
import com.simlect.entity.po.KnowledgeDocument;
import com.simlect.mappers.KnowledgeDocumentMapper;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.VectorStore;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import java.nio.charset.StandardCharsets;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class KnowledgeDocumentServiceTest {
    static final String ID="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
    @Mock KnowledgeDocumentMapper mapper;
    @Mock ReliableMessageSender sender;
    @Mock VectorStore vectorStore;
    @Spy KnowledgeDocumentParser parser=new KnowledgeDocumentParser();
    @InjectMocks KnowledgeDocumentService service;
    KnowledgeDocument doc;
    @BeforeEach void setup(){doc=new KnowledgeDocument();doc.setDocumentId(ID);doc.setTitle("TEST ONLY");doc.setFilename("test.txt");doc.setSource("TEST FIXTURE NOT APPROVED POLICY");doc.setRevision(1);doc.setState("DRAFT");doc.setEffectiveFrom(java.time.LocalDateTime.now(java.time.ZoneOffset.UTC).minusDays(1));doc.setSourceStatus("VALID");}
    String chunks(long revision)throws Exception{return new ObjectMapper().writeValueAsString(new KnowledgeDocumentParser().split(ID,revision,List.of(new KnowledgeDocumentParser.Section("测试章节",0,"TEST ONLY, no actual policy"))));}
    void ready(){doc.setApproved(true);doc.setState("PUBLISHED");doc.setIndexState("READY");doc.setReviewedBy("admin:test");doc.setReviewedRevision(doc.getRevision());doc.setIndexedRevision(doc.getRevision());}
    @Test void importDefaultsToDraftNoEmbeddingOrMq() {
        var created=service.importDocument(null,null,"TEST","test.txt","test fixture","TEST ONLY".getBytes(StandardCharsets.UTF_8));
        assertFalse(created.isApproved());assertEquals("DRAFT",created.getState());
        verify(mapper).insert(created);verify(mapper).insertRevision(eq(created.getDocumentId()),eq(1L),contains("sha256"));verifyNoInteractions(sender,vectorStore);
    }
    @Test void updateInvalidatesApprovalAndIncrementsRevision() {
        ready();when(mapper.lock(ID)).thenReturn(doc);
        service.importDocument(ID,1L,"NEW TEST","new.txt","TEST SOURCE","NEW TEST ONLY".getBytes(StandardCharsets.UTF_8));
        assertEquals(2,doc.getRevision());assertFalse(doc.isApproved());assertEquals("DRAFT",doc.getState());verifyNoInteractions(sender,vectorStore);
    }
    @Test void staleUpdateIsRejected() {
        when(mapper.lock(ID)).thenReturn(doc);
        assertThrows(RuntimeException.class,()->service.importDocument(ID,0L,"TEST","test.txt","SOURCE",new byte[]{65}));
        verify(mapper,never()).update(any());
    }
    @Test void cannotPublishWithoutExplicitConfirmation(){assertThrows(RuntimeException.class,()->service.publish(ID,1,false));verifyNoInteractions(sender,mapper,vectorStore);}
    @Test void publishUsesExistingReliableRagQueue() {
        doc.setState("PENDING_REVIEW");doc.setApproved(true);doc.setReviewedRevision(1);doc.setReviewedBy("admin:test");when(mapper.lock(ID)).thenReturn(doc);service.publish(ID,1,true);
        assertTrue(doc.isApproved());assertEquals("PUBLISHED",doc.getState());assertEquals("INDEXING",doc.getIndexState());
        verify(sender).sendMessage(anyString(),anyString(),argThat(value->value instanceof com.simlect.entity.dto.RagDataDTO d && d.getType().equals("aftersales_policy")&&d.getDataId().equals(ID)),startsWith("rag:policy:"),any());
    }
    @Test void vectorWritePreservesMetadataAndOnlyThenDeletesStale()throws Exception {
        doc.setRevision(2);ready();doc.setIndexState("INDEXING");when(mapper.lock(ID)).thenReturn(doc);
        when(mapper.chunks(ID,2)).thenReturn(chunks(2));when(mapper.history(ID)).thenReturn(List.of(chunks(1),chunks(2)));
        service.synchronize(ID);
        ArgumentCaptor<List<Document>> docs=ArgumentCaptor.forClass(List.class);var ordered=inOrder(vectorStore,mapper);
        ordered.verify(vectorStore).add(docs.capture());ordered.verify(vectorStore).delete(anyList());ordered.verify(mapper).update(doc);
        assertEquals("aftersales_policy",docs.getValue().get(0).getMetadata().get("dataType"));
        assertEquals("测试章节",docs.getValue().get(0).getMetadata().get("section"));assertEquals("TEST FIXTURE NOT APPROVED POLICY",docs.getValue().get(0).getMetadata().get("source"));
        assertEquals("READY",doc.getIndexState());assertEquals(2,doc.getIndexedRevision());
    }
    @Test void embeddingOrEsFailureNeverDeletesOldVectorsOrPublishesReady()throws Exception {
        ready();doc.setIndexState("INDEXING");when(mapper.lock(ID)).thenReturn(doc);when(mapper.history(ID)).thenReturn(List.of(chunks(1)));when(mapper.chunks(ID,1)).thenReturn(chunks(1));
        doThrow(new RuntimeException("Embedding unavailable")).when(vectorStore).add(anyList());
        assertThrows(RuntimeException.class,()->service.synchronize(ID));verify(vectorStore,never()).delete(anyList());verify(mapper,never()).update(any());assertEquals("INDEXING",doc.getIndexState());
    }
    @Test void deleteImmediatelyRevokesEligibilityAndMqRemovesOnlyOwnedIds()throws Exception {
        ready();when(mapper.lock(ID)).thenReturn(doc);service.delete(ID,1);
        assertEquals("RETIRED",doc.getState());assertFalse(doc.isApproved());
        when(mapper.get(ID)).thenReturn(doc);assertTrue(service.approvedCatalog(List.of(ID)).isEmpty());
        when(mapper.history(ID)).thenReturn(List.of(chunks(1)));service.synchronize(ID);
        List<String> expected=parser.split(ID,1,List.of(new KnowledgeDocumentParser.Section("测试章节",0,"TEST ONLY, no actual policy"))).stream().map(KnowledgeDocumentParser.Chunk::chunkId).toList();
        verify(vectorStore,never()).delete(anyList());verify(vectorStore,never()).add(anyList());
    }
    @Test void catalogRejectsInFlightOrUnapprovedVersion() {
        when(mapper.get(ID)).thenReturn(doc);assertTrue(service.approvedCatalog(List.of(ID)).isEmpty());
        ready();doc.setIndexState("INDEXING");assertTrue(service.approvedCatalog(List.of(ID)).isEmpty());
        doc.setIndexState("READY");doc.setIndexedRevision(0);assertTrue(service.approvedCatalog(List.of(ID)).isEmpty());
    }
    @Test void catalogReturnsVerifiedSourceAndChunkHashes()throws Exception {
        ready();when(mapper.get(ID)).thenReturn(doc);when(mapper.chunks(ID,1)).thenReturn(chunks(1));
        var rows=service.approvedCatalog(List.of(ID));assertEquals(1,rows.size());assertEquals(doc.getSource(),rows.get(0).get("source"));assertTrue(rows.get(0).get("chunks").toString().contains("sha256"));
    }
    @Test void unapprovedCannotReindexAndUnknownCannotDeleteVectors() {
        when(mapper.lock(ID)).thenReturn(doc);assertThrows(RuntimeException.class,()->service.reindex(ID,1));
        when(mapper.lock(ID)).thenReturn(null);assertThrows(RuntimeException.class,()->service.synchronize(ID));verifyNoInteractions(vectorStore);
    }
    @Test void reindexKeepsRevisionAndSchedulesNewOperation() {
        ready();when(mapper.lock(ID)).thenReturn(doc);service.reindex(ID,1);assertEquals(1,doc.getRevision());assertEquals("INDEXING",doc.getIndexState());verify(sender).sendMessage(anyString(),anyString(),any(),anyString(),any());
    }
    @Test void failedVectorizationCanRetrySameReviewedRevision()throws Exception {
        ready();doc.setIndexState("INDEXING");doc.setIndexedRevision(0);
        when(mapper.lock(ID)).thenReturn(doc);when(mapper.history(ID)).thenReturn(List.of(chunks(1)));when(mapper.chunks(ID,1)).thenReturn(chunks(1));
        doThrow(new RuntimeException("Mock embedding unavailable")).doNothing().when(vectorStore).add(anyList());
        assertThrows(RuntimeException.class,()->service.synchronize(ID));assertEquals(0,doc.getIndexedRevision());
        service.synchronize(ID);assertEquals(1,doc.getIndexedRevision());assertEquals("READY",doc.getIndexState());assertEquals("PUBLISHED",doc.getState());
    }
    @Test void officialSizedDocumentUsesAtMostTenTextsPerVectorCall()throws Exception {
        ready();doc.setIndexState("INDEXING");doc.setIndexedRevision(0);
        List<KnowledgeDocumentParser.Section> sections=new ArrayList<>();
        for(int i=0;i<61;i++)sections.add(new KnowledgeDocumentParser.Section("TEST ONLY section "+i,0,"TEST ONLY synthetic parser fixture "+i));
        String payload=new ObjectMapper().writeValueAsString(parser.split(ID,1,sections));
        when(mapper.lock(ID)).thenReturn(doc);when(mapper.history(ID)).thenReturn(List.of(payload));when(mapper.chunks(ID,1)).thenReturn(payload);
        service.synchronize(ID);
        ArgumentCaptor<List<Document>> batches=ArgumentCaptor.forClass(List.class);verify(vectorStore,times(7)).add(batches.capture());
        assertTrue(batches.getAllValues().stream().allMatch(b->b.size()<=10));
        assertEquals(61,batches.getAllValues().stream().mapToInt(List::size).sum());
        assertEquals(61,batches.getAllValues().stream().flatMap(List::stream).map(Document::getId).distinct().count());
        assertEquals("READY",doc.getIndexState());
    }
    @Test void duplicateDeliveryOfReadyRevisionDoesNotReembed(){
        ready();when(mapper.lock(ID)).thenReturn(doc);when(mapper.history(ID)).thenReturn(List.of());
        service.synchronize(ID);verifyNoInteractions(vectorStore);verify(mapper,never()).update(any());verify(mapper,never()).chunks(anyString(),anyLong());
    }
}
