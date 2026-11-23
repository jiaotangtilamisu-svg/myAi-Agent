package com.simlect.controller.internal;

import com.simlect.biz.KnowledgeDocumentService;
import com.simlect.controller.ABaseController;
import com.simlect.entity.vo.ResponseVO;
import jakarta.annotation.Resource;
import org.springframework.web.bind.annotation.*;
import java.util.*;

@RestController
@RequestMapping("/internal/knowledge")
public class KnowledgeCatalogController extends ABaseController {
    @Resource private KnowledgeDocumentService service;
    @PostMapping("/catalog")
    public ResponseVO<List<Map<String,Object>>> catalog(@RequestBody Map<String,Object> body){return getSuccessResponseVO(service.approvedCatalog((List<String>)body.get("documentIds"),(String)body.get("category")));}
}
