package com.simlect.biz;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.simlect.exception.BusinessException;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Durable audit-backed mock lifecycle. Never contains a payment client or executes funds. */
public final class CaseRefundWorkflow {
    private static final ObjectMapper JSON=new ObjectMapper();
    private static final Set<String> EVENTS=Set.of("PREPARE_REFUND","START_MOCK_REFUND","COMPLETE_MOCK_REFUND","TIMEOUT_MOCK_REFUND","MOCK_REFUND");
    private CaseRefundWorkflow(){}
    public static Map<String,Object> state(String caseId,long plan,List<Map<String,Object>> history){
        Map<String,Object> s=new LinkedHashMap<>();s.put("refundId",UUID.nameUUIDFromBytes((caseId+":"+plan).getBytes(StandardCharsets.UTF_8)).toString());s.put("refundMode","MOCK");s.put("refundStatus","NOT_EXECUTED");s.put("attempt",0);s.put("executionAllowed",false);
        for(var event:history)if(EVENTS.contains(String.valueOf(event.get("action")))&&((Number)event.get("planVersion")).longValue()==plan){
            JsonNode n=read(String.valueOf(event.get("note")));s.put("refundStatus",n.path("status").asText("NOT_EXECUTED"));s.put("type",n.path("type").asText());s.put("failureReason",n.path("failureReason").asText());s.put("attempt",n.path("attempt").asInt(1));
        }
        return s;
    }
    public static String command(String action,String caseId,long plan,List<Map<String,Object>> history,JsonNode input,boolean enabled){
        if(input==null||!input.isObject()||!Set.of("refund","return_refund").contains(input.path("type").asText()))throw new BusinessException("仅支持退款或退货退款");
        var current=state(caseId,plan,history);String status=(String)current.get("refundStatus"),type=input.path("type").asText();
        if(current.containsKey("type")&&!current.get("type").equals(type))throw new BusinessException("退款类型已确定，不能变更以绕过验收");
        String next;int attempt=((Number)current.get("attempt")).intValue();String reason="";
        switch(action){
            case "PREPARE_REFUND" -> {if(!Set.of("NOT_EXECUTED","FAILED").contains(status))throw new BusinessException("退款不可重复准备；结果未知须先人工核实");next="PENDING";}
            case "START_MOCK_REFUND" -> {
                if(!enabled)throw new BusinessException("模拟退款开关关闭，不执行真实退款");
                if(!status.equals("PENDING"))throw new BusinessException("须先准备待执行退款");
                if(type.equals("return_refund")){
                    var accept=history.stream().filter(e->"RETURN_ACCEPT".equals(e.get("action"))).reduce((a,b)->b).orElse(Map.of());
                    if(!read(String.valueOf(accept.getOrDefault("note","{}"))).path("accepted").asBoolean())throw new BusinessException("退货未验收通过");
                }
                next="PROCESSING";attempt++;
            }
            case "COMPLETE_MOCK_REFUND" -> {
                if(!enabled||!Set.of("PROCESSING","UNKNOWN").contains(status))throw new BusinessException("退款未处理中或模拟开关关闭");
                if(!input.path("simulateFailure").isBoolean()||input.path("result").asText().isBlank())throw new BusinessException("请明确模拟结果并填写核实说明");
                if(status.equals("UNKNOWN")&&(!input.path("manualReconciliation").isBoolean()||!input.path("manualReconciliation").asBoolean()))throw new BusinessException("超时结果未知，须人工核实后登记结果");
                boolean failure=input.path("simulateFailure").asBoolean();next=failure?"FAILED":"SUCCEEDED";reason=failure?input.path("result").asText():"";
            }
            case "TIMEOUT_MOCK_REFUND" -> {if(!enabled||!status.equals("PROCESSING")||input.path("result").asText().isBlank())throw new BusinessException("只能记录处理中退款的超时并填写说明");next="UNKNOWN";reason=input.path("result").asText();}
            default -> throw new BusinessException("不支持的退款状态操作");
        }
        ObjectNode n=JSON.createObjectNode();n.put("type",type);n.put("refundId",String.valueOf(current.get("refundId")));n.put("mode","MOCK");n.put("status",next);n.put("attempt",attempt);n.put("failureReason",reason);n.put("result",input.path("result").asText());n.put("manualReconciliation",status.equals("UNKNOWN")&&action.equals("COMPLETE_MOCK_REFUND"));n.put("executionAllowed",false);
        return n.toString();
    }
    private static JsonNode read(String s){try{return JSON.readTree(s);}catch(Exception e){throw new BusinessException("退款履约记录无效");}}
}
