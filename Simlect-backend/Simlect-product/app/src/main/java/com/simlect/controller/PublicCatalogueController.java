package com.simlect.controller;
import com.simlect.biz.PublicCatalogueService;
import com.simlect.entity.vo.ResponseVO;
import jakarta.annotation.Resource;
import org.springframework.web.bind.annotation.*;

/** Admin endpoint uses the existing /admin/** session interceptor. No write endpoint. */
@RestController
public class PublicCatalogueController extends ABaseController {
 @Resource private PublicCatalogueService service;
 @GetMapping("/product/publicCatalogue")
 public ResponseVO catalogue(@RequestParam(defaultValue="") String keyword,@RequestParam(defaultValue="") String category,@RequestParam(defaultValue="1") int page){return getSuccessResponseVO(service.list(keyword,category,page));}
 @PostMapping("/admin/productInfo/publicBatches")
 public ResponseVO batches(){return getSuccessResponseVO(service.batches());}
}
