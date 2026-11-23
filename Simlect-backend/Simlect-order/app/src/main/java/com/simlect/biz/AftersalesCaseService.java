package com.simlect.biz;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.simlect.entity.po.AftersalesCase;
import com.simlect.entity.po.OrderInfo;
import com.simlect.exception.BusinessException;
import com.simlect.mappers.AftersalesCaseMapper;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;

/** Case workflow only. Deliberately has no payment/refund/executor dependency. */
@Service
public class AftersalesCaseService {
    public record Actor(String id, boolean admin) {
        public Actor { if(id==null||id.isBlank()||id.length()>200)throw new BusinessException("登录身份无效"); }
        public String type(){return admin?"ADMIN":"USER";}
    }
    public record Command(String caseId,long expectedVersion,String requestId,String note) {}
    private static final Set<String> STATES=Set.of("AWAITING_USER","ADMIN_REVIEW","REJECTED","MANUAL_PENDING","IN_PROGRESS","PROCESSING_FAILED","RESOLVED","ARCHIVED","CANCELLED");
    private static final Set<String> ADMIN_COMMANDS=Set.of("APPROVE","REJECT","CLAIM","SUCCEED","FAIL","RETRY","RETURN_LOGISTICS","RETURN_PROGRESS","RETURN_ACCEPT","MOCK_REFUND","PREPARE_REFUND","START_MOCK_REFUND","COMPLETE_MOCK_REFUND","TIMEOUT_MOCK_REFUND");
    @org.springframework.beans.factory.annotation.Value("${simlect.aftersales.mock-refund-enabled:false}")
    private boolean mockRefundEnabled;
    private static final Set<String> LOW_ACTIONS=Set.of("WAIT","CONTACT_CARRIER","CONTACT_MERCHANT","CLARIFY_CASE");
    private static final Map<String,String> LABELS=Map.ofEntries(
        Map.entry("WAIT","等待并查看订单后续状态"),Map.entry("CONTACT_CARRIER","人工联系物流核实运输情况"),
        Map.entry("CONTACT_MERCHANT","人工联系商家核实发货情况"),Map.entry("CLARIFY_CASE","补充问题说明"),
        Map.entry("PAYMENT_REVIEW","人工核对支付流水；不执行支付"),Map.entry("REFUND_REVIEW","人工核对退款资料；不执行退款"),
        Map.entry("QUALITY_REVIEW","人工核实质量问题和售后申请"),Map.entry("MANUAL_REVIEW","人工核实事实与适用政策"),
        Map.entry("VERIFY_POLICY","人工确认政策依据"),Map.entry("RECONCILE_EVIDENCE","人工核对冲突证据"),
        Map.entry("VERIFY_PAYMENT","人工核实支付情况；不执行支付"),Map.entry("VERIFY_ORDER","人工核实订单情况"));
    @Resource private AftersalesCaseMapper mapper;
    @Resource private OrderInfoService orderInfoService;
    private final ObjectMapper json=new ObjectMapper().configure(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS,true);

    @Transactional(rollbackFor=Exception.class)
    public Map<String,Object> create(Actor actor,long messageId,JsonNode report) {
        if(actor.admin()||messageId<1||report==null||!report.isObject()||report.toString().length()>200_000)
            throw new BusinessException("诊断案件参数不合法");
        String orderId=report.path("orderId").asText("");
        if(orderId.isBlank()||orderId.length()>64||report.path("schemaVersion").asInt()!=1
                ||!report.has("executionAllowed")||!report.get("executionAllowed").isBoolean()||report.get("executionAllowed").asBoolean()
                ||!"SUCCESS".equals(report.path("orderFacts").path("queryStatus").asText())
                ||!report.path("orderFacts").path("data").path("ownerVerified").asBoolean()
                ||!orderId.equals(report.path("orderFacts").path("data").path("orderId").asText()))
            throw new BusinessException("仅允许已验证订单的只读诊断创建案件");
        OrderInfo owned=orderInfoService.getOrderInfoByOrderIdAndUserId(orderId,actor.id());
        if(owned==null||!actor.id().equals(owned.getUserId())||!orderId.equals(owned.getOrderId()))
            throw new BusinessException("订单不存在或无权访问");
        ObjectNode snapshot=((ObjectNode)report).deepCopy(); snapshot.remove("caseWorkflow");
        String diagnosis=encode(snapshot), hash=sha(diagnosis);
        String risk=risk(snapshot);
        AftersalesCase row=new AftersalesCase();row.setCaseId(UUID.randomUUID().toString());row.setUserId(actor.id());
        row.setOrderId(orderId);row.setSourceMessageId(messageId);row.setRequestHash(hash);row.setDiagnosisJson(diagnosis);
        row.setState("AWAITING_USER");row.setVersion(1);row.setPlanVersion(1);row.setRisk(risk);
        mapper.insert(row); // Unique(user_id, source_message_id) serializes concurrent create retries.
        AftersalesCase stored=mapper.bySource(actor.id(),messageId);
        if(stored==null)throw new BusinessException("创建案件失败");
        if(!stored.getRequestHash().equals(hash))throw new BusinessException("相同诊断消息的内容已变化，拒绝覆盖案件");
        if(!stored.getCaseId().equals(row.getCaseId()))return view(stored,true);
        mapper.plan(row.getCaseId(),1,risk,encode(plan(snapshot,risk,"")));
        audit(row,actor,"CREATE",null,"create:"+messageId,hash,"");
        return view(stored,false);
    }

    @Transactional(rollbackFor=Exception.class)
    public Map<String,Object> detail(Actor actor,String id){checkId(id);return view(authorized(actor,mapper.lock(id)),false);}
    public List<Map<String,Object>> list(Actor actor,String state,int page,int size){
        return list(actor,state,page,size,null);
    }
    public List<Map<String,Object>> list(Actor actor,String state,int page,int size,String orderId){
        if(page<1||page>10000||size<1||size>50||(state!=null&&!STATES.contains(state)))throw new BusinessException("分页或状态参数错误");
        if(orderId!=null){
            if(orderId.isBlank()||orderId.length()>64)throw new BusinessException("订单参数错误");
            return mapper.listForOrder(actor.admin()?null:actor.id(),state,orderId,(page-1)*size,size).stream().map(this::summary).toList();
        }
        return mapper.list(actor.admin()?null:actor.id(),state,(page-1)*size,size).stream().map(this::summary).toList();
    }

    @Transactional(rollbackFor=Exception.class)
    public Map<String,Object> command(Actor actor,String action,Command request) {
        checkId(request.caseId());checkId(request.requestId());
        String note=request.note()==null?"":request.note().strip();
        if(note.length()>2000||request.expectedVersion()<1)throw new BusinessException("版本或说明参数错误");
        if(ADMIN_COMMANDS.contains(action)&&!actor.admin())throw new BusinessException("需要管理员审批或处理权限");
        if(Set.of("CONFIRM","RESUBMIT","AMEND","CANCEL").contains(action)&&actor.admin())throw new BusinessException("管理员不能代替用户确认方案");
        AftersalesCase row=authorized(actor,mapper.lock(request.caseId()));
        String hash=sha(encode(List.of(action,request.expectedVersion(),note)));
        Map<String,Object> prior=mapper.command(row.getCaseId(),request.requestId());
        if(prior!=null){
            if(!hash.equals(prior.get("requestHash"))||!actor.type().equals(prior.get("actorType"))||!actor.id().equals(prior.get("actorId")))
                throw new BusinessException("幂等请求号已经用于其他内容或操作者");
            Map<String,Object> replay=view(row,true);replay.put("appliedVersion",prior.get("caseVersion"));return replay;
        }
        if(row.getVersion()!=request.expectedVersion())throw new BusinessException("案件版本已变化，请刷新后重试");
        String from=row.getState(), to;
        switch(action){
            case "CONFIRM" -> { requireState(row,"AWAITING_USER");requireNote(note);
                OrderInfo current=orderInfoService.getOrderInfoByOrderIdAndUserId(row.getOrderId(),actor.id());
                if(current==null||!actor.id().equals(current.getUserId())||!row.getOrderId().equals(current.getOrderId()))throw new BusinessException("订单已无法核实，请重新查询后再申请");
                note=applicationNote(note,current.getOrderStatus());if(read(note).has("requestedType"))row.setRisk("HIGH");to="HIGH".equals(row.getRisk())?"ADMIN_REVIEW":"MANUAL_PENDING";if(to.equals("MANUAL_PENDING"))newTask(row,1); }
            case "APPROVE" -> { requireState(row,"ADMIN_REVIEW");requireNote(note);to="MANUAL_PENDING";newTask(row,1); }
            case "REJECT" -> { requireState(row,"ADMIN_REVIEW");requireNote(note);to="REJECTED"; }
            case "RESUBMIT" -> {
                requireState(row,"REJECTED");requireNote(note);to="AWAITING_USER";
                JsonNode previous=read(mapper.planContent(row.getCaseId(),row.getPlanVersion()));
                row.setPlanVersion(row.getPlanVersion()+1);
                ObjectNode revised=((ObjectNode)previous).deepCopy();revised.put("userSupplement",note);
                mapper.plan(row.getCaseId(),row.getPlanVersion(),row.getRisk(),encode(revised));
            }
            case "AMEND" -> {
                if(!Set.of("AWAITING_USER","REJECTED").contains(from))throw new BusinessException("仅待确认或驳回方案可修改；已提交方案需先取消");
                note=applicationNote(note,null);row.setPlanVersion(row.getPlanVersion()+1);row.setRisk("HIGH");
                ObjectNode revised=(ObjectNode)read(mapper.planContent(row.getCaseId(),row.getPlanVersion()-1)).deepCopy();revised.set("application",read(note));revised.put("risk","HIGH");mapper.plan(row.getCaseId(),row.getPlanVersion(),"HIGH",encode(revised));to="AWAITING_USER";
            }
            case "CANCEL" -> {
                requireNote(note);if(!Set.of("AWAITING_USER","ADMIN_REVIEW","REJECTED","MANUAL_PENDING").contains(from))throw new BusinessException("案件已处理中，须联系人工核实取消");
                mapper.cancelPendingTasks(row.getCaseId());to="CANCELLED";
            }
            case "PREPARE_REFUND", "START_MOCK_REFUND", "COMPLETE_MOCK_REFUND", "TIMEOUT_MOCK_REFUND" -> {
                requireState(row,"IN_PROGRESS");if(!actor.id().equals(task(row).get("handler")))throw new BusinessException("仅当前任务处理人可操作");
                var history=mapper.timeline(row.getCaseId());JsonNode input=read(note);validateRequestedType(row,input,history);
                note=CaseRefundWorkflow.command(action,row.getCaseId(),row.getPlanVersion(),history,input,mockRefundEnabled);to=from;
            }
            case "CLAIM" -> {
                requireState(row,"MANUAL_PENDING");Map<String,Object> task=task(row);
                if(mapper.claim((String)task.get("taskId"),actor.id())!=1)throw new BusinessException("人工任务已被领取");to="IN_PROGRESS";
            }
            case "SUCCEED", "FAIL" -> {
                requireState(row,"IN_PROGRESS");requireNote(note);Map<String,Object> task=task(row);
                if(!actor.id().equals(task.get("handler")))throw new BusinessException("仅当前任务处理人可提交结果");
                if(action.equals("SUCCEED")&&!Set.of("NOT_EXECUTED","SUCCEEDED").contains(CaseRefundWorkflow.state(row.getCaseId(),row.getPlanVersion(),mapper.timeline(row.getCaseId())).get("refundStatus")))throw new BusinessException("退款结果尚未完成核实，不可将案件标为成功");
                if(action.equals("SUCCEED")){
                    var history=mapper.timeline(row.getCaseId());
                    boolean typed=history.stream().filter(e->Set.of("CONFIRM","AMEND").contains(e.get("action"))).anyMatch(e->{String n=String.valueOf(e.get("note"));return n.startsWith("{")&&Set.of("refund","return_refund").contains(read(n).path("requestedType").asText());});
                    if(typed&&!"SUCCEEDED".equals(CaseRefundWorkflow.state(row.getCaseId(),row.getPlanVersion(),history).get("refundStatus")))throw new BusinessException("退款申请尚无成功执行记录，不能提前完成案件");
                }
                if(mapper.finish((String)task.get("taskId"),actor.id(),action.equals("SUCCEED")?"SUCCEEDED":"FAILED",note)!=1)
                    throw new BusinessException("人工任务状态已变化");
                to=action.equals("SUCCEED")?"RESOLVED":"PROCESSING_FAILED";
            }
            case "RETRY" -> {
                requireState(row,"PROCESSING_FAILED");requireNote(note);Map<String,Object> last=task(row);
                newTask(row,((Number)last.get("attempt")).intValue()+1);to="MANUAL_PENDING";
            }
            case "ARCHIVE" -> { if(!Set.of("RESOLVED","REJECTED","CANCELLED").contains(from))throw new BusinessException("仅已处理或已驳回案件可归档");to="ARCHIVED"; }
            case "USER_RETURN_LOGISTICS" -> {
                if(actor.admin())throw new BusinessException("管理员不能代替用户填写退货物流");
                if(!Set.of("MANUAL_PENDING","IN_PROGRESS").contains(from))throw new BusinessException("须审核通过后再填写退货物流");
                JsonNode input=read(note);validateReturnLogistics(input);
                var history=mapper.timeline(row.getCaseId());validateRequestedType(row,input,history);
                if(history.stream().anyMatch(e->Set.of("RETURN_LOGISTICS","USER_RETURN_LOGISTICS","RETURN_ACCEPT","MOCK_REFUND").contains(String.valueOf(e.get("action")))))throw new BusinessException("物流已登记或已进入履约，请联系人工核实更正，勿重复寄件");
                ObjectNode clean=json.createObjectNode();clean.put("type","return_refund");clean.put("carrier",input.path("carrier").asText().strip());clean.put("trackingNo",input.path("trackingNo").asText().strip());
                note=encode(clean);to=from;
            }
            case "RETURN_LOGISTICS", "RETURN_PROGRESS", "RETURN_ACCEPT", "MOCK_REFUND" -> {
                requireState(row,"IN_PROGRESS");
                if(!actor.id().equals(task(row).get("handler")))throw new BusinessException("仅当前任务处理人可操作");
                JsonNode input=read(note);if(input==null||!input.isObject())throw new BusinessException("履约参数必须为对象");String type=input.path("type").asText();
                if(!Set.of("refund","return_refund").contains(type))throw new BusinessException("仅支持退款或退货退款");
                var history=mapper.timeline(row.getCaseId());
                validateRequestedType(row,input,history);
                if(history.stream().anyMatch(e->Set.of("RETURN_LOGISTICS","USER_RETURN_LOGISTICS","RETURN_PROGRESS","RETURN_ACCEPT","MOCK_REFUND").contains(String.valueOf(e.get("action")))&&!type.equals(read(String.valueOf(e.get("note"))).path("type").asText())))throw new BusinessException("办理类型已登记，不能改类型绕过退货验收");
                if(action.equals("RETURN_LOGISTICS")){
                    if(history.stream().anyMatch(e->"RETURN_ACCEPT".equals(e.get("action"))))throw new BusinessException("已验收的退货物流不可覆盖");
                    validateReturnLogistics(input);
                    var previous=history.stream().filter(e->Set.of("RETURN_LOGISTICS","USER_RETURN_LOGISTICS").contains(e.get("action"))).reduce((a,b)->b);
                    if(previous.isPresent()){
                        JsonNode old=read(String.valueOf(previous.get().get("note")));
                        if(old.path("carrier").asText().strip().equals(input.path("carrier").asText().strip())&&old.path("trackingNo").asText().strip().equals(input.path("trackingNo").asText().strip()))
                            throw new BusinessException("该退货物流已登记，请更新物流进度或登记退货验收，不要重复登记");
                        if(input.path("result").asText().isBlank())throw new BusinessException("更正已登记物流须填写更正原因");
                    }
                    ObjectNode clean=json.createObjectNode();clean.put("type",type);clean.put("carrier",input.path("carrier").asText().strip());clean.put("trackingNo",input.path("trackingNo").asText().strip());
                    if(previous.isPresent())clean.put("correctionReason",input.path("result").asText().strip());note=encode(clean);
                }else if(action.equals("RETURN_PROGRESS")){
                    if(!type.equals("return_refund")||history.stream().noneMatch(e->Set.of("RETURN_LOGISTICS","USER_RETURN_LOGISTICS").contains(e.get("action"))))throw new BusinessException("须先登记退货物流");
                    if(history.stream().anyMatch(e->"RETURN_ACCEPT".equals(e.get("action"))))throw new BusinessException("已验收物流不可继续修改运输状态");
                    if(!Set.of("IN_TRANSIT","DELIVERED","EXCEPTION").contains(input.path("logisticsStatus").asText())||input.path("result").asText().isBlank())throw new BusinessException("请填写运输状态和核实说明");
                    ObjectNode progress=json.createObjectNode();progress.put("type",type);progress.put("logisticsStatus",input.path("logisticsStatus").asText());progress.put("result",input.path("result").asText());progress.put("source","MANUAL_VERIFIED");note=encode(progress);
                }else if(action.equals("RETURN_ACCEPT")){
                    if(!Set.of("NOT_EXECUTED","PENDING").contains(CaseRefundWorkflow.state(row.getCaseId(),row.getPlanVersion(),history).get("refundStatus")))throw new BusinessException("退款已开始，验收记录不能变更，请人工核实");
                    if(!type.equals("return_refund")||history.stream().noneMatch(e->Set.of("RETURN_LOGISTICS","USER_RETURN_LOGISTICS").contains(e.get("action"))))throw new BusinessException("须先登记退货物流");
                    if(input.path("result").asText().isBlank()||!input.path("accepted").isBoolean())throw new BusinessException("请填写验收结果并明确是否通过");
                    if(input.has("received")&&(!input.path("received").isBoolean()||!input.path("received").asBoolean()))throw new BusinessException("须先确认收到退货");
                    if(input.has("condition")&&!Set.of("INTACT","DAMAGED","UNKNOWN").contains(input.path("condition").asText()))throw new BusinessException("商品验收状态无效");
                    if(input.has("evidenceRefs")){JsonNode refs=input.path("evidenceRefs");if(!refs.isArray()||refs.size()>3)throw new BusinessException("验收证据引用超限");for(JsonNode ref:refs)if(!ref.isTextual()||ref.asText().isBlank()||ref.asText().length()>200)throw new BusinessException("验收证据引用无效");}
                }else{
                    if(!Set.of("NOT_EXECUTED","FAILED").contains(CaseRefundWorkflow.state(row.getCaseId(),row.getPlanVersion(),history).get("refundStatus")))throw new BusinessException("退款已进入分步流程或已完成，不能通过旧接口重复执行");
                    if(!mockRefundEnabled)throw new BusinessException("模拟退款开关默认关闭；本接口不执行真实退款");
                    if(input.has("simulateFailure")&&!input.path("simulateFailure").isBoolean())throw new BusinessException("模拟失败标志必须为布尔值");
                    var latestAcceptance=history.stream().filter(e->"RETURN_ACCEPT".equals(e.get("action"))).reduce((a,b)->b).orElse(Map.of());
                    if(type.equals("return_refund")&&!read(String.valueOf(latestAcceptance.getOrDefault("note","{}"))).path("accepted").asBoolean())throw new BusinessException("退货尚未验收通过");
                    String refundId=UUID.nameUUIDFromBytes((row.getCaseId()+":"+row.getPlanVersion()).getBytes(StandardCharsets.UTF_8)).toString();
                    if(history.stream().anyMatch(e->"MOCK_REFUND".equals(e.get("action"))&&"SUCCEEDED".equals(read(String.valueOf(e.get("note"))).path("status").asText())))throw new BusinessException("模拟退款已经成功，不允许重复执行");
                    ObjectNode outcome=json.createObjectNode();outcome.put("type",type);outcome.put("failureReason",input.path("simulateFailure").asBoolean()?input.path("result").asText("模拟渠道故障，请由处理人核实重试"):"");outcome.put("refundId",refundId);outcome.put("mode","MOCK");outcome.put("executionAllowed",false);outcome.put("status",input.path("simulateFailure").asBoolean()?"FAILED":"SUCCEEDED");note=encode(outcome);
                }
                to="IN_PROGRESS"; // Records fulfillment evidence; never claims bank settlement.
            }
            default -> throw new BusinessException("不支持的案件操作");
        }
        long expected=row.getVersion();row.setVersion(expected+1);row.setState(to);
        if(mapper.update(row,expected)!=1)throw new BusinessException("案件并发更新冲突，请刷新");
        audit(row,actor,action,from,request.requestId(),hash,note);
        return view(mapper.lock(row.getCaseId()),false);
    }

    private String risk(JsonNode report){
        JsonNode actions=report.path("recommendedActions");
        if(!actions.isArray()||actions.isEmpty()||actions.size()>20)throw new BusinessException("诊断方案为空或超限");
        if("RETURN_GUIDANCE".equals(report.path("requestedOperation").asText()))return "HIGH";
        boolean low="AFTERSALES_CONSULT".equals(report.path("caseType").asText())
                &&"NOT_OBSERVED".equals(report.path("diagnosis").path("status").asText())
                &&"SUCCESS".equals(report.path("policyEvidence").path("status").asText());
        for(JsonNode a:actions)low&=LOW_ACTIONS.contains(a.path("code").asText());
        return low?"LOW":"HIGH";
    }
    private Map<String,Object> plan(JsonNode report,String risk,String supplement){
        List<Map<String,Object>> actions=new ArrayList<>();
        for(JsonNode a:report.path("recommendedActions")){
            String code=a.path("code").asText();if(!LABELS.containsKey(code))code="MANUAL_REVIEW";
            actions.add(Map.of("code",code,"title",LABELS.get(code),"executionAllowed",false));
        }
        return Map.of("risk",risk,"actions",actions,"reasons",report.path("diagnosis"),
                "policyEvidence",report.path("policyEvidence"),"userSupplement",supplement,"executionAllowed",false);
    }
    private AftersalesCase authorized(Actor actor,AftersalesCase row){
        if(row==null||(!actor.admin()&&!actor.id().equals(row.getUserId())))throw new BusinessException("案件不存在或无权访问");return row;
    }
    private Map<String,Object> summary(AftersalesCase row){
        return Map.of("caseId",row.getCaseId(),"orderId",row.getOrderId(),"state",row.getState(),"version",row.getVersion(),
                "planVersion",row.getPlanVersion(),"risk",row.getRisk(),"executionAllowed",false,
                "capabilities",Map.of("mockRefundEnabled",mockRefundEnabled,"realRefundExecutionEnabled",false));
    }
    private Map<String,Object> view(AftersalesCase row,boolean replay){
        Map<String,Object> v=new LinkedHashMap<>(summary(row));v.put("diagnosis",read(row.getDiagnosisJson()));
        v.put("createdAt",row.getCreatedAt());v.put("updatedAt",row.getUpdatedAt());
        v.put("plans",mapper.plans(row.getCaseId()));v.put("tasks",mapper.tasks(row.getCaseId()));v.put("timeline",mapper.timeline(row.getCaseId()));
        var history=mapper.timeline(row.getCaseId());var fulfillment=fulfillment(history);var refund=CaseRefundWorkflow.state(row.getCaseId(),row.getPlanVersion(),history);if(!"NOT_EXECUTED".equals(refund.get("refundStatus")))fulfillment.putAll(refund);v.put("fulfillment",fulfillment);
        String application=String.valueOf(history.stream().filter(e->Set.of("CONFIRM","AMEND").contains(e.get("action"))).reduce((a,b)->b).map(e->e.get("note")).orElse(""));
        if(application.startsWith("{")){JsonNode a=read(application);v.put("applicationReason",a.path("reason").asText());v.put("applicationMaterials",a.path("materials"));v.put("submittedOrderStatus",a.path("orderStatus"));v.put("requestedType",a.path("requestedType").asText(""));}
        else{v.put("applicationReason",application);v.put("applicationMaterials",List.of());}
        if(v.get("requestedType") instanceof String type&&!type.isBlank())fulfillment.put("requestedType",type);
        v.put("replayed",replay);v.put("sourceMessageId",row.getSourceMessageId());return v;
    }
    private String applicationNote(String note,Integer status){
        ObjectNode result=json.createObjectNode();String reason=note;JsonNode materials=json.createArrayNode();
        if(note.startsWith("{")){JsonNode input=read(note);reason=input.path("reason").asText();materials=input.path("materials");
            if(!materials.isArray()||materials.size()>2)throw new BusinessException("最多填写两项申请材料说明");
            for(JsonNode m:materials)if(!m.isTextual()||m.asText().isBlank()||m.asText().length()>350)throw new BusinessException("申请材料说明无效或过长");
        }
        if(reason.isBlank()||reason.length()>1000)throw new BusinessException("请填写不超过1000字的真实申请原因");
        if(note.startsWith("{")){JsonNode input=read(note);if(input.has("requestedType")){String type=input.path("requestedType").asText();if(!Set.of("refund","return_refund","exchange").contains(type))throw new BusinessException("申请类型仅支持退款、退货退款或人工换货");result.put("requestedType",type);}}
        result.put("reason",reason);result.set("materials",materials);if(status==null)result.putNull("orderStatus");else result.put("orderStatus",status);
        String encoded=encode(result);if(encoded.length()>2000)throw new BusinessException("申请原因与材料总长度超限，请精简后提交");return encoded;
    }
    private void validateRequestedType(AftersalesCase row,JsonNode input,List<Map<String,Object>> history){
        if(input==null||!input.isObject())throw new BusinessException("履约参数必须为对象");
        var application=history.stream().filter(e->Set.of("CONFIRM","AMEND").contains(e.get("action"))).reduce((a,b)->b);
        if(application.isPresent()){String value=String.valueOf(application.get().get("note"));if(value.startsWith("{")){String type=read(value).path("requestedType").asText();if(!type.isBlank()&&!type.equals(input.path("type").asText()))throw new BusinessException("履约类型与用户确认申请不同，不能绕过审核变更");}}
        var refund=CaseRefundWorkflow.state(row.getCaseId(),row.getPlanVersion(),history);
        if(!"NOT_EXECUTED".equals(refund.get("refundStatus"))&&refund.containsKey("type")&&!refund.get("type").equals(input.path("type").asText()))throw new BusinessException("退款类型已锁定");
    }
    private void validateReturnLogistics(JsonNode input){
        if(input==null||!input.isObject()||!"return_refund".equals(input.path("type").asText())||!input.path("carrier").isTextual()||input.path("carrier").asText().isBlank()||input.path("carrier").asText().length()>80||!input.path("trackingNo").asText().matches("(?=.*[A-Za-z0-9])[A-Za-z0-9-]{5,60}"))throw new BusinessException("请填写退货物流公司及有效运单号");
    }
    private Map<String,Object> fulfillment(List<Map<String,Object>> history){
        Map<String,Object> result=new LinkedHashMap<>();result.put("executionAllowed",false);result.put("refundStatus","NOT_EXECUTED");result.put("logisticsStatus","NOT_REGISTERED");
        for(var e:history){String action=String.valueOf(e.get("action"));
            if(Set.of("RETURN_LOGISTICS","USER_RETURN_LOGISTICS","RETURN_PROGRESS","RETURN_ACCEPT","MOCK_REFUND").contains(action)){
                JsonNode n=read(String.valueOf(e.get("note")));result.put("type",n.path("type").asText());
                if(Set.of("RETURN_LOGISTICS","USER_RETURN_LOGISTICS").contains(action)){result.put("carrier",n.path("carrier").asText());result.put("trackingNo",n.path("trackingNo").asText());result.put("logisticsStatus","REGISTERED");result.put("logisticsSource","USER_OR_ADMIN_RECORDED");}
                if(action.equals("RETURN_PROGRESS")){result.put("logisticsStatus",n.path("logisticsStatus").asText());result.put("logisticsNote",n.path("result").asText());result.put("logisticsSource","MANUAL_VERIFIED");}
                if(action.equals("RETURN_ACCEPT")){result.put("acceptance",n.path("accepted").asBoolean()?"ACCEPTED":"REJECTED");result.put("acceptanceNote",n.path("result").asText());result.put("returnReceived",n.path("received").asBoolean(true));result.put("returnCondition",n.path("condition").asText("UNKNOWN"));result.put("acceptanceEvidence",n.path("evidenceRefs"));}
                if(action.equals("MOCK_REFUND")){result.put("refundMode","MOCK");result.put("refundStatus",n.path("status").asText());result.put("refundId",n.path("refundId").asText());result.put("failureReason",n.path("failureReason").asText());}
            }
        }
        return result;
    }
    private void newTask(AftersalesCase row,int attempt){mapper.task(Map.of("taskId",UUID.randomUUID().toString(),"caseId",row.getCaseId(),"planVersion",row.getPlanVersion(),"attempt",attempt));}
    private Map<String,Object> task(AftersalesCase row){Map<String,Object> t=mapper.latestTask(row.getCaseId());if(t==null||((Number)t.get("planVersion")).longValue()!=row.getPlanVersion())throw new BusinessException("人工任务不存在");return t;}
    private void audit(AftersalesCase row,Actor actor,String action,String from,String request,String hash,String note){
        Map<String,Object> e=new LinkedHashMap<>();e.put("eventId",UUID.randomUUID().toString());e.put("caseId",row.getCaseId());
        e.put("caseVersion",row.getVersion());e.put("planVersion",row.getPlanVersion());e.put("requestId",request);e.put("requestHash",hash);
        e.put("actorType",actor.type());e.put("actorId",actor.id());e.put("action",action);e.put("fromState",from);e.put("toState",row.getState());e.put("note",note);mapper.audit(e);
    }
    private void requireState(AftersalesCase row,String state){if(!state.equals(row.getState()))throw new BusinessException("非法案件状态流转");}
    private void requireNote(String note){if(note.isBlank())throw new BusinessException("请填写审批、处理结果或补充说明");}
    private void checkId(String id){try{if(id==null||!UUID.fromString(id).toString().equals(id))throw new IllegalArgumentException();}catch(IllegalArgumentException e){throw new BusinessException("案件或请求ID格式不合法");}}
    private String encode(Object value){try{return json.writeValueAsString(json.convertValue(value,Object.class));}catch(Exception e){throw new BusinessException("案件数据序列化失败",e);}}
    private JsonNode read(String value){try{return json.readTree(value);}catch(Exception e){throw new BusinessException("案件记录无效",e);}}
    private String sha(String value){try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8)));}catch(Exception e){throw new IllegalStateException(e);}}
}
