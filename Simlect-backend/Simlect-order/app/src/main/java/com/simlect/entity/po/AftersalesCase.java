package com.simlect.entity.po;

import lombok.Data;
import java.util.Date;

@Data
public class AftersalesCase {
    private String caseId;
    private String userId;
    private String orderId;
    private long sourceMessageId;
    private String requestHash;
    private String state;
    private long version;
    private long planVersion;
    private String risk;
    private String diagnosisJson;
    private Date createdAt;
    private Date updatedAt;
}
