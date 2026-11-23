package com.simlect.controller.aftersales;

import com.simlect.biz.AftersalesCaseService;
import com.simlect.biz.AftersalesCaseService.Command;
import com.simlect.controller.ABaseController;
import com.simlect.entity.vo.ResponseVO;
import jakarta.annotation.Resource;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/order/aftersalesCase")
public class AftersalesUserController extends ABaseController {
    public record CaseListRequest(String state,Integer page,Integer size,String orderId) {}
    public record CaseDetailRequest(String caseId) {}
    @Resource private CaseAuthentication auth;
    @Resource private AftersalesCaseService service;
    @PostMapping("/detail") public ResponseVO detail(HttpServletRequest r,@RequestParam String caseId){return getSuccessResponseVO(service.detail(auth.user(r),caseId));}
    @PostMapping(value="/detail",consumes="application/json") public ResponseVO detailJson(HttpServletRequest r,@RequestBody CaseDetailRequest q){return getSuccessResponseVO(service.detail(auth.user(r),q.caseId()));}
    @PostMapping("/list") public ResponseVO list(HttpServletRequest r,@RequestParam(required=false) String state,@RequestParam(defaultValue="1") int page,@RequestParam(defaultValue="20") int size,@RequestParam(required=false) String orderId){return getSuccessResponseVO(service.list(auth.user(r),state,page,size,orderId));}
    @PostMapping(value="/list",consumes="application/json") public ResponseVO listJson(HttpServletRequest r,@RequestBody CaseListRequest q){return getSuccessResponseVO(service.list(auth.user(r),q.state(),q.page()==null?1:q.page(),q.size()==null?20:q.size(),q.orderId()));}
    @PostMapping("/returnLogistics") public ResponseVO returnLogistics(HttpServletRequest r,@RequestBody Command c){return getSuccessResponseVO(service.command(auth.user(r),"USER_RETURN_LOGISTICS",c));}
    @PostMapping("/confirm") public ResponseVO confirm(HttpServletRequest r,@RequestBody Command c){return getSuccessResponseVO(service.command(auth.user(r),"CONFIRM",c));}
    @PostMapping("/resubmit") public ResponseVO resubmit(HttpServletRequest r,@RequestBody Command c){return getSuccessResponseVO(service.command(auth.user(r),"RESUBMIT",c));}
    @PostMapping("/archive") public ResponseVO archive(HttpServletRequest r,@RequestBody Command c){return getSuccessResponseVO(service.command(auth.user(r),"ARCHIVE",c));}
    @PostMapping("/amend") public ResponseVO amend(HttpServletRequest r,@RequestBody Command c){return getSuccessResponseVO(service.command(auth.user(r),"AMEND",c));}
    @PostMapping("/cancel") public ResponseVO cancel(HttpServletRequest r,@RequestBody Command c){return getSuccessResponseVO(service.command(auth.user(r),"CANCEL",c));}
}
