package com.simlect.mappers;

import com.simlect.entity.po.AftersalesCase;
import org.apache.ibatis.annotations.*;
import java.util.*;

public interface AftersalesCaseMapper {
    @Select("SELECT * FROM aftersales_case WHERE case_id=#{id}")
    AftersalesCase get(String id);
    @Select("SELECT * FROM aftersales_case WHERE case_id=#{id} FOR UPDATE")
    AftersalesCase lock(String id);
    @Select("SELECT * FROM aftersales_case WHERE user_id=#{user} AND source_message_id=#{message} FOR UPDATE")
    AftersalesCase bySource(@Param("user") String user,@Param("message") long message);
    @Insert("INSERT INTO aftersales_case(case_id,user_id,order_id,source_message_id,request_hash,state,version,plan_version,risk,diagnosis_json) VALUES(#{caseId},#{userId},#{orderId},#{sourceMessageId},#{requestHash},#{state},#{version},#{planVersion},#{risk},#{diagnosisJson}) ON DUPLICATE KEY UPDATE case_id=case_id")
    void insert(AftersalesCase row);
    @Update("UPDATE aftersales_case SET state=#{row.state},risk=#{row.risk},version=#{row.version},plan_version=#{row.planVersion},updated_at=NOW(3) WHERE case_id=#{row.caseId} AND version=#{expected}")
    int update(@Param("row") AftersalesCase row,@Param("expected") long expected);
    @Select({"<script>SELECT * FROM aftersales_case WHERE 1=1 <if test='user != null'>AND user_id=#{user}</if> <if test='state != null'>AND state=#{state}</if> ORDER BY updated_at DESC,case_id LIMIT #{size} OFFSET #{offset}</script>"})
    List<AftersalesCase> list(@Param("user") String user,@Param("state") String state,@Param("offset") int offset,@Param("size") int size);
    @Select({"<script>SELECT * FROM aftersales_case WHERE order_id=#{order} <if test='user != null'>AND user_id=#{user}</if> <if test='state != null'>AND state=#{state}</if> ORDER BY updated_at DESC,case_id LIMIT #{size} OFFSET #{offset}</script>"})
    List<AftersalesCase> listForOrder(@Param("user") String user,@Param("state") String state,@Param("order") String order,@Param("offset") int offset,@Param("size") int size);
    @Insert("INSERT INTO aftersales_plan(case_id,version,risk,content_json) VALUES(#{id},#{version},#{risk},#{content})")
    void plan(@Param("id") String id,@Param("version") long version,@Param("risk") String risk,@Param("content") String content);
    @Select("SELECT version,risk,content_json AS content,created_at AS createdAt FROM aftersales_plan WHERE case_id=#{id} ORDER BY version FOR UPDATE")
    List<Map<String,Object>> plans(String id);
    @Select("SELECT content_json FROM aftersales_plan WHERE case_id=#{id} AND version=#{version}")
    String planContent(@Param("id") String id,@Param("version") long version);
    @Insert("INSERT INTO aftersales_manual_task(task_id,case_id,plan_version,attempt,state) VALUES(#{taskId},#{caseId},#{planVersion},#{attempt},'PENDING')")
    void task(Map<String,Object> task);
    @Select("SELECT task_id AS taskId,case_id AS caseId,plan_version AS planVersion,attempt,state,handler,result_note AS resultNote,started_at AS startedAt,finished_at AS finishedAt FROM aftersales_manual_task WHERE case_id=#{id} ORDER BY plan_version DESC,attempt DESC LIMIT 1")
    Map<String,Object> latestTask(String id);
    @Select("SELECT task_id AS taskId,plan_version AS planVersion,attempt,state,handler,result_note AS resultNote,started_at AS startedAt,finished_at AS finishedAt FROM aftersales_manual_task WHERE case_id=#{id} ORDER BY plan_version,attempt FOR UPDATE")
    List<Map<String,Object>> tasks(String id);
    @Update("UPDATE aftersales_manual_task SET state='IN_PROGRESS',handler=#{handler},started_at=NOW(3) WHERE task_id=#{id} AND state='PENDING'")
    int claim(@Param("id") String id,@Param("handler") String handler);
    @Update("UPDATE aftersales_manual_task SET state='CANCELLED',finished_at=NOW(3) WHERE case_id=#{id} AND state='PENDING'")
    int cancelPendingTasks(String id);
    @Update("UPDATE aftersales_manual_task SET state=#{state},result_note=#{note},finished_at=NOW(3) WHERE task_id=#{id} AND state='IN_PROGRESS' AND handler=#{handler}")
    int finish(@Param("id") String id,@Param("handler") String handler,@Param("state") String state,@Param("note") String note);
    @Insert("INSERT INTO aftersales_audit(event_id,case_id,case_version,plan_version,request_id,request_hash,actor_type,actor_id,action,from_state,to_state,note) VALUES(#{eventId},#{caseId},#{caseVersion},#{planVersion},#{requestId},#{requestHash},#{actorType},#{actorId},#{action},#{fromState},#{toState},#{note})")
    void audit(Map<String,Object> event);
    @Select("SELECT request_hash AS requestHash,case_version AS caseVersion,actor_type AS actorType,actor_id AS actorId,action FROM aftersales_audit WHERE case_id=#{id} AND request_id=#{request}")
    Map<String,Object> command(@Param("id") String id,@Param("request") String request);
    @Select("SELECT event_id AS eventId,case_version AS caseVersion,plan_version AS planVersion,actor_type AS actorType,actor_id AS actorId,action,from_state AS fromState,to_state AS toState,note,created_at AS createdAt FROM aftersales_audit WHERE case_id=#{id} ORDER BY case_version FOR UPDATE")
    List<Map<String,Object>> timeline(String id);
}
