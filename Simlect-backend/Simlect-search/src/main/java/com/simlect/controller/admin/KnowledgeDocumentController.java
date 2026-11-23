package com.simlect.controller.admin;

import com.simlect.biz.KnowledgeDocumentService;
import com.simlect.entity.vo.ResponseVO;
import com.simlect.exception.BusinessException;
import jakarta.annotation.Resource;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/admin/rag/knowledge")
public class KnowledgeDocumentController extends ABaseController {
    @Resource private KnowledgeDocumentService service;
    @Resource private com.simlect.component.RedisComponent redisComponent;
    @Resource private com.simlect.utils.AuthCookieHelper authCookieHelper;
    private void requireAdmin(jakarta.servlet.http.HttpServletRequest request) {
        String token=authCookieHelper.resolveAdminToken(request);
        if(token==null||token.isBlank()||redisComponent.getLoginInfo4Admin(token)==null)
            throw new BusinessException(com.simlect.entity.enums.ResponseCodeEnum.CODE_901);
    }
    private String actor(jakarta.servlet.http.HttpServletRequest request) {
        requireAdmin(request);
        Object account=redisComponent.getLoginInfo4Admin(authCookieHelper.resolveAdminToken(request));
        if(account==null)throw new BusinessException(com.simlect.entity.enums.ResponseCodeEnum.CODE_901);
        try {return "admin:"+java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(String.valueOf(account).getBytes(java.nio.charset.StandardCharsets.UTF_8)));}
        catch(java.security.NoSuchAlgorithmException e){throw new IllegalStateException(e);}
    }
    @PostMapping("/import")
    public ResponseVO importFile(jakarta.servlet.http.HttpServletRequest request,@RequestParam MultipartFile file,@RequestParam String title,@RequestParam String source,
            @RequestParam(required=false) String documentId,@RequestParam(required=false) Long expectedRevision) throws java.io.IOException {
        requireAdmin(request);
        if(file.getSize()>10*1024*1024)throw new BusinessException("文档超过10MiB");
        java.util.Map<String,String> fields=new java.util.HashMap<>();
        for(String key:java.util.List.of("category","issuer","originalUrl","publishedOn","effectiveFrom","effectiveUntil","sourceStatus")) {
            String value=request.getParameter(key);if(value!=null)fields.put(key,value);
        }
        return getSuccessResponseVO(service.importManaged(documentId,expectedRevision,title,file.getOriginalFilename(),source,file.getBytes(),fields,actor(request)));
    }
    @PostMapping("/list") public ResponseVO list(jakarta.servlet.http.HttpServletRequest request,@RequestParam(defaultValue="1") int page,@RequestParam(defaultValue="20") int size){requireAdmin(request);return getSuccessResponseVO(request.getParameter("category")==null && request.getParameter("state")==null ? service.list(page,size) : service.filtered(page,size,request.getParameter("category"),request.getParameter("state")));}
    @PostMapping("/detail") public ResponseVO detail(jakarta.servlet.http.HttpServletRequest request,@RequestParam String documentId){requireAdmin(request);return getSuccessResponseVO(service.detail(documentId));}
    @PostMapping("/publish") public ResponseVO publish(jakarta.servlet.http.HttpServletRequest request,@RequestParam String documentId,@RequestParam long revision,@RequestParam(defaultValue="false") boolean confirmedPolicy){return getSuccessResponseVO(service.publishManaged(documentId,revision,confirmedPolicy,actor(request)));}
    @PostMapping("/reindex") public ResponseVO reindex(jakarta.servlet.http.HttpServletRequest request,@RequestParam String documentId,@RequestParam long revision){service.reindexManaged(documentId,revision,actor(request));return getSuccessResponseVO(null);}
    @PostMapping("/delete") public ResponseVO delete(jakarta.servlet.http.HttpServletRequest request,@RequestParam String documentId,@RequestParam long revision){service.retireManaged(documentId,revision,actor(request));return getSuccessResponseVO(null);}
    @PostMapping("/transition") public ResponseVO transition(jakarta.servlet.http.HttpServletRequest request,@RequestParam String documentId,@RequestParam long revision,@RequestParam String action) {
        return getSuccessResponseVO(service.transition(documentId,revision,action,actor(request)));
    }
    @PostMapping("/metadata") public ResponseVO metadata(jakarta.servlet.http.HttpServletRequest request,@RequestParam String documentId,@RequestParam long revision) {
        String principal=actor(request);java.util.Map<String,String> fields=new java.util.HashMap<>();
        for(String key:java.util.List.of("category","issuer","originalUrl","publishedOn","effectiveFrom","effectiveUntil","sourceStatus")) {
            String value=request.getParameter(key);if(value!=null)fields.put(key,value);
        }
        return getSuccessResponseVO(service.updateMetadata(documentId,revision,fields,principal));
    }
    @PostMapping("/version") public ResponseVO version(jakarta.servlet.http.HttpServletRequest request,@RequestParam String documentId,@RequestParam long revision){requireAdmin(request);return getSuccessResponseVO(service.version(documentId,revision));}
    @GetMapping("/original") public org.springframework.http.ResponseEntity<byte[]> original(jakarta.servlet.http.HttpServletRequest request,@RequestParam String documentId,@RequestParam long revision){requireAdmin(request);return org.springframework.http.ResponseEntity.ok().header("Content-Disposition","attachment; filename=policy-source.bin").contentType(org.springframework.http.MediaType.APPLICATION_OCTET_STREAM).body(service.original(documentId,revision));}
}
