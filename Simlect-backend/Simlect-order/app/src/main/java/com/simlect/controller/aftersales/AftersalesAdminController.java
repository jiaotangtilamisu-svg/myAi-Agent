package com.simlect.controller.aftersales;

import com.simlect.biz.AftersalesCaseService;
import com.simlect.biz.AftersalesCaseService.Command;
import com.simlect.controller.ABaseController;
import com.simlect.entity.vo.ResponseVO;
import jakarta.annotation.Resource;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/admin/aftersalesCase")
public class AftersalesAdminController extends ABaseController {
    @Resource private CaseAuthentication auth;
    @Resource private AftersalesCaseService service;
    @PostMapping("/returnLogistics") public ResponseVO returnLogistics(HttpServletRequest r,@RequestBody Command c){return getSuccessResponseVO(service.command(auth.admin(r),"RETURN_LOGISTICS",c));}
    @PostMapping("/returnProgress") public ResponseVO returnProgress(HttpServletRequest r,@RequestBody Command c){return getSuccessResponseVO(service.command(auth.admin(r),"RETURN_PROGRESS",c));}
    @PostMapping("/acceptReturn") public ResponseVO acceptReturn(HttpServletRequest r,@RequestBody Command c){return getSuccessResponseVO(service.command(auth.admin(r),"RETURN_ACCEPT",c));}
    @PostMapping("/simulateRefund") public ResponseVO simulateRefund(HttpServletRequest r,@RequestBody Command c){return getSuccessResponseVO(service.command(auth.admin(r),"MOCK_REFUND",c));}
    @PostMapping("/detail") public ResponseVO detail(HttpServletRequest r,@RequestParam String caseId){return getSuccessResponseVO(service.detail(auth.admin(r),caseId));}
    @PostMapping("/list") public ResponseVO list(HttpServletRequest r,@RequestParam(required=false) String state,@RequestParam(defaultValue="1") int page,@RequestParam(defaultValue="20") int size){return getSuccessResponseVO(service.list(auth.admin(r),state,page,size));}
    @PostMapping("/approve") public ResponseVO approve(HttpServletRequest r,@RequestBody Command c){return getSuccessResponseVO(service.command(auth.admin(r),"APPROVE",c));}
    @PostMapping("/reject") public ResponseVO reject(HttpServletRequest r,@RequestBody Command c){return getSuccessResponseVO(service.command(auth.admin(r),"REJECT",c));}
    @PostMapping("/claim") public ResponseVO claim(HttpServletRequest r,@RequestBody Command c){return getSuccessResponseVO(service.command(auth.admin(r),"CLAIM",c));}
    @PostMapping("/succeed") public ResponseVO succeed(HttpServletRequest r,@RequestBody Command c){return getSuccessResponseVO(service.command(auth.admin(r),"SUCCEED",c));}
    @PostMapping("/fail") public ResponseVO fail(HttpServletRequest r,@RequestBody Command c){return getSuccessResponseVO(service.command(auth.admin(r),"FAIL",c));}
    @PostMapping("/retry") public ResponseVO retry(HttpServletRequest r,@RequestBody Command c){return getSuccessResponseVO(service.command(auth.admin(r),"RETRY",c));}
    @PostMapping("/archive") public ResponseVO archive(HttpServletRequest r,@RequestBody Command c){return getSuccessResponseVO(service.command(auth.admin(r),"ARCHIVE",c));}
    @PostMapping("/prepareRefund") public ResponseVO prepareRefund(HttpServletRequest r,@RequestBody Command c){return getSuccessResponseVO(service.command(auth.admin(r),"PREPARE_REFUND",c));}
    @PostMapping("/startMockRefund") public ResponseVO startMockRefund(HttpServletRequest r,@RequestBody Command c){return getSuccessResponseVO(service.command(auth.admin(r),"START_MOCK_REFUND",c));}
    @PostMapping("/completeMockRefund") public ResponseVO completeMockRefund(HttpServletRequest r,@RequestBody Command c){return getSuccessResponseVO(service.command(auth.admin(r),"COMPLETE_MOCK_REFUND",c));}
    @PostMapping("/timeoutMockRefund") public ResponseVO timeoutMockRefund(HttpServletRequest r,@RequestBody Command c){return getSuccessResponseVO(service.command(auth.admin(r),"TIMEOUT_MOCK_REFUND",c));}
}
