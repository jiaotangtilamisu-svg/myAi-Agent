package com.simlect.biz;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.simlect.constants.RabbitMQConfig;
import com.simlect.constants.ReliableMessageSender;
import com.simlect.entity.dto.RagDataDTO;
import com.simlect.entity.enums.MessageReliabilityLevelEnum;
import com.simlect.entity.enums.RagDataTypeEnum;
import com.simlect.entity.po.KnowledgeDocument;
import com.simlect.exception.BusinessException;
import com.simlect.mappers.KnowledgeDocumentMapper;
import jakarta.annotation.Resource;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import java.util.*;

@Service
public class KnowledgeDocumentService {
    @Resource private KnowledgeDocumentMapper mapper;
    @Resource private KnowledgeDocumentParser parser;
    @Resource private ReliableMessageSender sender;
    @Resource private VectorStore vectorStore;
    private final ObjectMapper json=new ObjectMapper().findAndRegisterModules().disable(com.fasterxml.jackson.databind.SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
    private static final TypeReference<List<KnowledgeDocumentParser.Chunk>> CHUNKS=new TypeReference<>(){};

    @Transactional(rollbackFor=Exception.class)
    public KnowledgeDocument importDocument(String id,Long expectedRevision,String title,String filename,String source,byte[] bytes) {
        return importRaw(id,expectedRevision,title,filename,source,bytes,"authenticated-admin");
    }
    private KnowledgeDocument importRaw(String id,Long expectedRevision,String title,String filename,String source,byte[] bytes,String actor) {
        if(title==null||title.isBlank()||title.length()>200||source==null||source.isBlank()||source.length()>1000||filename==null)
            throw new BusinessException("文档名称和可追溯来源不能为空或超长");
        String safe=filename.replace('\\','/');safe=safe.substring(safe.lastIndexOf('/')+1);
        if(safe.isBlank()||safe.length()>200||safe.chars().anyMatch(Character::isISOControl))throw new BusinessException("文档文件名不合法");
        var sections=parser.parse(safe,bytes);
        KnowledgeDocument doc;
        boolean created=id==null;
        if(created){doc=new KnowledgeDocument();doc.setDocumentId(UUID.randomUUID().toString());doc.setRevision(1);}
        else{doc=requiredLocked(id,expectedRevision);if(Set.of("DELETED","RETIRED").contains(doc.getState()))throw new BusinessException("已删除文档不可覆盖");doc.setRevision(doc.getRevision()+1);}
        String previous=created?"NEW":doc.getState();
        doc.setTitle(title.strip());doc.setFilename(safe);doc.setSource(source.strip());
        doc.setApproved(false);doc.setReviewedRevision(0);doc.setReviewedBy("");doc.setIndexState("NOT_INDEXED");doc.setIndexedRevision(0);doc.setState("DRAFT");
        var chunks=parser.split(doc.getDocumentId(),doc.getRevision(),sections);
        if(created)mapper.insert(doc);else mapper.update(doc);
        try{mapper.insertRevision(doc.getDocumentId(),doc.getRevision(),json.writeValueAsString(chunks));}
        catch(Exception e){throw new BusinessException("保存文档分块失败",e);}
        mapper.saveOriginal(doc.getDocumentId(),doc.getRevision(),bytes);
        audit(doc,"IMPORT",actor,previous,doc.getState());
        return doc;
    }

    @Transactional(rollbackFor=Exception.class)
    public KnowledgeDocument publish(String id,long revision,boolean confirmedPolicy) {
        if(!confirmedPolicy)throw new BusinessException("必须由管理员明确确认政策来源和正文后发布");
        KnowledgeDocument doc=requiredLocked(id,revision);
        if(Set.of("DELETED","RETIRED").contains(doc.getState()))throw new BusinessException("文档已删除");
        if(!"PENDING_REVIEW".equals(doc.getState())||!PolicyRules.reviewed(doc))throw new BusinessException("政策必须先提交审核并由管理员审核通过");
        PolicyRules.validate(doc);
        if(!PolicyRules.effective(doc))throw new BusinessException("政策未生效、已过期或来源无效");
        doc.setState("PUBLISHED");doc.setIndexState("INDEXING");doc.setIndexedRevision(0);mapper.update(doc);
        audit(doc,"PUBLISH","authenticated-admin","PENDING_REVIEW","PUBLISHED");enqueue(doc);
        return doc;
    }

    @Transactional(rollbackFor=Exception.class)
    public void reindex(String id,long revision) {
        KnowledgeDocument doc=requiredLocked(id,revision);
        if(!"PUBLISHED".equals(doc.getState())||!PolicyRules.reviewed(doc)||!PolicyRules.effective(doc))throw new BusinessException("只能重新向量化当前有效且审核通过的已发布文档");
        doc.setIndexState("INDEXING");doc.setIndexedRevision(0);mapper.update(doc);audit(doc,"REINDEX","authenticated-admin",doc.getState(),doc.getState());enqueue(doc);
    }

    @Transactional(rollbackFor=Exception.class)
    public void delete(String id,long revision) {
        KnowledgeDocument doc=requiredLocked(id,revision);
        String previous=doc.getState();
        if("RETIRED".equals(previous))throw new BusinessException("政策已归档");
        doc.setState("RETIRED");doc.setApproved(false);mapper.update(doc);
        audit(doc,"RETIRE","authenticated-admin",previous,"RETIRED");
    }

    public List<KnowledgeDocument> list(int page,int size) {
        if(page<1||page>10000||size<1||size>50)throw new BusinessException("分页参数错误");
        return mapper.list((page-1)*size,size);
    }
    public List<KnowledgeDocument> filtered(int page,int size,String category,String state) {
        if(page<1||page>10000||size<1||size>50)throw new BusinessException("分页参数错误");
        category=category==null||category.isBlank()?null:category;
        state=state==null||state.isBlank()?null:state;
        if(category!=null&&!PolicyRules.CATEGORIES.contains(category))throw new BusinessException("类别错误");
        if(state!=null&&!Set.of("DRAFT","PENDING_REVIEW","PUBLISHED","DISABLED","RETIRED").contains(state))throw new BusinessException("状态错误");
        return mapper.filtered((page-1)*size,size,category,state);
    }
    public Map<String,Object> detail(String id) {
        checkId(id);KnowledgeDocument doc=mapper.get(id);
        if(doc==null)throw new BusinessException("文档不存在");
        return Map.of("document",doc,"chunks",chunks(doc),"versions",mapper.revisions(id),"audit",mapper.auditHistory(id));
    }

    /** Latest database catalog is authoritative; old, deleted, unapproved or in-flight vectors fail closed. */
    public List<Map<String,Object>> approvedCatalog(List<String> ids) {return approvedCatalog(ids,null);}
    public List<Map<String,Object>> approvedCatalog(List<String> ids,String category) {
        if(category!=null&&!PolicyRules.CATEGORIES.contains(category))throw new BusinessException("政策类别不合法");
        if(ids==null||ids.size()>50)throw new BusinessException("文档查询参数错误");
        List<Map<String,Object>> result=new ArrayList<>();
        for(String id:new LinkedHashSet<>(ids)) {
            checkId(id);KnowledgeDocument doc=mapper.get(id);
            if(!PolicyRules.retrievable(doc,category))continue;
            Map<String,Object> m=new LinkedHashMap<>();m.put("documentId",id);m.put("revision",doc.getRevision());
            m.put("title",doc.getTitle());m.put("filename",doc.getFilename());m.put("source",doc.getSource());
            m.put("category",doc.getCategory());m.put("issuer",doc.getIssuer());m.put("originalUrl",doc.getOriginalUrl());m.put("publishedOn",Objects.toString(doc.getPublishedOn(),""));m.put("effectiveFrom",doc.getEffectiveFrom().toString()+"Z");m.put("effectiveUntil",doc.getEffectiveUntil()==null ? "" : doc.getEffectiveUntil().toString()+"Z");m.put("sourceStatus",doc.getSourceStatus());
            m.put("chunks",chunks(doc).stream().map(c->Map.of("chunkId",c.chunkId(),"sha256",c.sha256(),"section",c.section(),"page",c.page())).toList());result.add(m);
        }
        return result;
    }

    /** Called only by the existing RAG MQ consumer, using the same VectorStore/EmbeddingModel. */
    @Transactional(rollbackFor=Exception.class)
    public void synchronize(String id) {
        checkId(id);KnowledgeDocument doc=mapper.lock(id);
        if(doc==null)throw new BusinessException("文档不存在，拒绝无范围清理");
        List<String> all=new ArrayList<>();
        for(String revision:mapper.history(id))all.addAll(readChunks(revision).stream().map(KnowledgeDocumentParser.Chunk::chunkId).toList());
        if(!"PUBLISHED".equals(doc.getState())||!PolicyRules.reviewed(doc)||!PolicyRules.effective(doc))return;
        // Duplicate MQ deliveries must not bill a successfully indexed revision again.
        if("READY".equals(doc.getIndexState())&&doc.getIndexedRevision()==doc.getRevision())return;
        List<KnowledgeDocumentParser.Chunk> chunks=chunks(doc);
        List<Document> docs=new ArrayList<>();
        for(var c:chunks) {
            Map<String,Object> metadata=new LinkedHashMap<>();metadata.put("dataType",RagDataTypeEnum.AFTERSALES_POLICY.getType());
            metadata.put("documentId",id);metadata.put("revision",doc.getRevision());metadata.put("chunkId",c.chunkId());
            metadata.put("documentName",doc.getTitle());metadata.put("filename",doc.getFilename());metadata.put("source",doc.getSource());
            metadata.put("category",doc.getCategory());metadata.put("issuer",doc.getIssuer());metadata.put("originalUrl",doc.getOriginalUrl());
            metadata.put("section",c.section());metadata.put("page",c.page());metadata.put("sha256",c.sha256());metadata.put("approved",true);
            docs.add(new Document(c.chunkId(),c.text(),metadata));
        }
        // Never delete the currently stored vectors before all new embedding/writes succeed.
        // DashScope text-embedding-v4 accepts at most ten texts in one request.
        // Reuse the existing VectorStore/EmbeddingModel; keep stable chunk IDs for retry upserts.
        for(int start=0;start<docs.size();start+=10) {
            vectorStore.add(docs.subList(start,Math.min(start+10,docs.size())));
        }
        Set<String> keep=new HashSet<>(chunks.stream().map(KnowledgeDocumentParser.Chunk::chunkId).toList());
        List<String> stale=all.stream().filter(k->!keep.contains(k)).distinct().toList();
        if(!stale.isEmpty())vectorStore.delete(stale);
        doc.setIndexState("READY");doc.setIndexedRevision(doc.getRevision());mapper.update(doc);
        audit(doc,"INDEX_READY","system:rag-consumer",doc.getState(),doc.getState());
    }

    @Transactional(rollbackFor=Exception.class)
    public KnowledgeDocument importManaged(String id,Long expected,String title,String filename,String source,byte[] bytes,Map<String,String> fields,String actor) {
        KnowledgeDocument doc=importRaw(id,expected,title,filename,source,bytes,actor);
        applyMetadata(doc,fields);PolicyRules.validate(doc);mapper.update(doc);
        audit(doc,"METADATA",actor,"DRAFT","DRAFT");return doc;
    }

    private void applyMetadata(KnowledgeDocument d,Map<String,String> f) {
        try {
            d.setCategory(f.getOrDefault("category","PLATFORM_DEMO"));
            d.setIssuer(f.getOrDefault("issuer",""));d.setOriginalUrl(f.getOrDefault("originalUrl",""));
            d.setSourceStatus(f.getOrDefault("sourceStatus","UNVERIFIED"));
            d.setPublishedOn(f.getOrDefault("publishedOn","").isBlank()?null:java.time.LocalDate.parse(f.get("publishedOn")));
            d.setEffectiveFrom(f.getOrDefault("effectiveFrom","").isBlank()?null:java.time.LocalDateTime.ofInstant(java.time.Instant.parse(f.get("effectiveFrom")),java.time.ZoneOffset.UTC));
            d.setEffectiveUntil(f.getOrDefault("effectiveUntil","").isBlank()?null:java.time.LocalDateTime.ofInstant(java.time.Instant.parse(f.get("effectiveUntil")),java.time.ZoneOffset.UTC));
        } catch(Exception e){throw new BusinessException("政策元数据或UTC时间格式不合法");}
    }

    @Transactional(rollbackFor=Exception.class)
    public KnowledgeDocument transition(String id,long revision,String action,String actor) {
        KnowledgeDocument d=requiredLocked(id,revision);String previous=d.getState();
        switch(action) {
            case "submit" -> {if(!"DRAFT".equals(previous))throw new BusinessException("只能提交草稿");PolicyRules.validate(d);d.setState("PENDING_REVIEW");d.setApproved(false);}
            case "approve" -> {if(!"PENDING_REVIEW".equals(previous)||d.isApproved())throw new BusinessException("政策不处于待审核状态");PolicyRules.validate(d);if(!"VALID".equals(d.getSourceStatus()))throw new BusinessException("必须核实来源有效状态");d.setApproved(true);d.setReviewedRevision(revision);d.setReviewedBy(actor);}
            case "reject" -> {if(!"PENDING_REVIEW".equals(previous))throw new BusinessException("政策不处于待审核状态");d.setState("DRAFT");d.setApproved(false);d.setReviewedRevision(0);d.setReviewedBy("");}
            case "disable" -> {if(!"PUBLISHED".equals(previous))throw new BusinessException("只能停用已发布政策");d.setState("DISABLED");}
            case "enable" -> {if(!"DISABLED".equals(previous)||!PolicyRules.reviewed(d)||!PolicyRules.effective(d))throw new BusinessException("重新启用要求审核版本一致、来源有效且处于有效期");PolicyRules.validate(d);d.setState("PUBLISHED");if(d.getIndexedRevision()!=revision){d.setIndexState("INDEXING");enqueue(d);}}
            default -> throw new BusinessException("不支持的政策操作");
        }
        mapper.update(d);audit(d,action.toUpperCase(Locale.ROOT),actor,previous,d.getState());return d;
    }

    @Transactional(rollbackFor=Exception.class)
    public KnowledgeDocument publishManaged(String id,long revision,boolean confirmed,String actor) {
        KnowledgeDocument d=publish(id,revision,confirmed);audit(d,"PUBLISH_ACTOR",actor,"PENDING_REVIEW",d.getState());return d;
    }
    @Transactional(rollbackFor=Exception.class)
    public void reindexManaged(String id,long revision,String actor) {
        reindex(id,revision);audit(requiredLocked(id,revision),"REINDEX_ACTOR",actor,"PUBLISHED","PUBLISHED");
    }
    @Transactional(rollbackFor=Exception.class)
    public void retireManaged(String id,long revision,String actor) {
        delete(id,revision);audit(requiredLocked(id,revision),"RETIRE_ACTOR",actor,"","RETIRED");
    }

    public Map<String,Object> version(String id,long revision) {
        checkId(id);if(revision<1)throw new BusinessException("版本不合法");
        try {
            String meta=mapper.versionMetadata(id,revision);
            return Map.of("documentId",id,"revision",revision,"chunks",readChunks(mapper.chunks(id,revision)),"metadata",meta==null?Map.of():json.readValue(meta,Map.class));
        } catch(java.io.IOException e){throw new BusinessException("版本元数据无效",e);}
    }
    public byte[] original(String id,long revision) {
        checkId(id);byte[] bytes=mapper.original(id,revision);if(bytes==null)throw new BusinessException("该版本没有保留原始文件");return bytes;
    }
    @Transactional(rollbackFor=Exception.class)
    public KnowledgeDocument updateMetadata(String id,long revision,Map<String,String> fields,String actor) {
        KnowledgeDocument d=requiredLocked(id,revision);
        return importManaged(id,revision,d.getTitle(),d.getFilename(),d.getSource(),original(id,revision),fields,actor);
    }
    private void audit(KnowledgeDocument d,String action,String actor,String from,String to) {
        try {mapper.audit(d.getDocumentId(),d.getRevision(),action,actor,from,to,json.writeValueAsString(d));}
        catch(Exception e){throw new BusinessException("政策审计记录失败",e);}
    }

    private KnowledgeDocument requiredLocked(String id,Long revision) {
        checkId(id);KnowledgeDocument doc=mapper.lock(id);
        if(doc==null||revision==null||revision!=doc.getRevision())throw new BusinessException("文档不存在或版本已变化，请刷新");
        return doc;
    }
    private void checkId(String id) {
        try{if(id==null||!UUID.fromString(id).toString().equals(id))throw new IllegalArgumentException();}
        catch(IllegalArgumentException e){throw new BusinessException("文档ID不合法");}
    }
    private List<KnowledgeDocumentParser.Chunk> chunks(KnowledgeDocument doc) {return readChunks(mapper.chunks(doc.getDocumentId(),doc.getRevision()));}
    private List<KnowledgeDocumentParser.Chunk> readChunks(String value) {
        try{List<KnowledgeDocumentParser.Chunk> chunks=json.readValue(value,CHUNKS);if(chunks==null||chunks.isEmpty())throw new IllegalArgumentException();return chunks;}
        catch(Exception e){throw new BusinessException("文档分块记录无效",e);}
    }
    private void enqueue(KnowledgeDocument doc) {
        String id=doc.getDocumentId();long revision=doc.getRevision();
        Runnable send=()->sender.sendMessage(RabbitMQConfig.RAG_EXCHANGE,RabbitMQConfig.RAG_QUEUE_KEY,
            new RagDataDTO(id,RagDataTypeEnum.AFTERSALES_POLICY.getType()),"rag:policy:"+id+":"+revision+":"+UUID.randomUUID(),MessageReliabilityLevelEnum.HIGH);
        if(TransactionSynchronizationManager.isSynchronizationActive())TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization(){@Override public void afterCommit(){send.run();}});
        else send.run();
    }
}
