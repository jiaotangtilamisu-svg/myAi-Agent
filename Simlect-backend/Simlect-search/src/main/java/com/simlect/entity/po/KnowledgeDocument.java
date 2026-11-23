package com.simlect.entity.po;

import lombok.Data;

@Data
public class KnowledgeDocument {
    private String documentId;
    private String title;
    private String filename;
    private String source;
    private long revision;
    private boolean approved;
    private String state;
    private long indexedRevision;
    private String category = "PLATFORM_DEMO";
    private String issuer = "";
    private String originalUrl = "";
    private java.time.LocalDate publishedOn;
    private java.time.LocalDateTime effectiveFrom;
    private java.time.LocalDateTime effectiveUntil;
    private String sourceStatus = "UNVERIFIED";
    private long reviewedRevision;
    private String reviewedBy = "";
    private String indexState = "NOT_INDEXED";
}
