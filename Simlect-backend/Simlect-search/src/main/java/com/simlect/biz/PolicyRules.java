package com.simlect.biz;

import com.simlect.entity.po.KnowledgeDocument;
import com.simlect.exception.BusinessException;
import java.net.URI;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.Set;

/** Pure eligibility rules. Database catalog, not stale vector metadata, grants eligibility. */
public final class PolicyRules {
    private PolicyRules() {}
    public static final Set<String> CATEGORIES=Set.of("LAW","INDUSTRY_REFERENCE","PLATFORM_DEMO");
    public static void validate(KnowledgeDocument d) {
        if(!CATEGORIES.contains(d.getCategory()))throw new BusinessException("政策类别不合法");
        if(!Set.of("UNVERIFIED","VALID","INVALID").contains(d.getSourceStatus()))throw new BusinessException("来源状态不合法");
        if(d.getIssuer()==null||d.getIssuer().length()>200||d.getOriginalUrl()==null||d.getOriginalUrl().length()>1000)throw new BusinessException("发布机构或原始网址不合法");
        if(d.getEffectiveFrom()==null)throw new BusinessException("必须指定UTC生效时间");
        if(d.getEffectiveUntil()!=null&&!d.getEffectiveUntil().isAfter(d.getEffectiveFrom()))throw new BusinessException("失效时间必须晚于生效时间");
        try {
            String host=URI.create(d.getOriginalUrl()).getHost();
            if(host!=null&&(host.equalsIgnoreCase("jd.com")||host.toLowerCase(java.util.Locale.ROOT).endsWith(".jd.com")||host.equalsIgnoreCase("jingdong.com")||host.toLowerCase(java.util.Locale.ROOT).endsWith(".jingdong.com"))&&!"INDUSTRY_REFERENCE".equals(d.getCategory()))throw new BusinessException("京东政策只能归类为行业对标参考");
        } catch(IllegalArgumentException e){throw new BusinessException("原始网址格式不合法");}
        if(!"PLATFORM_DEMO".equals(d.getCategory())) {
            try {var u=URI.create(d.getOriginalUrl());if(!"https".equalsIgnoreCase(u.getScheme())||u.getHost()==null)throw new IllegalArgumentException();}
            catch(Exception e){throw new BusinessException("法律法规或行业参考必须保留HTTPS原始网址");}
            if(d.getIssuer().isBlank()||d.getPublishedOn()==null)throw new BusinessException("必须保留发布机构及发布日期");
        }
    }
    public static boolean effective(KnowledgeDocument d) {
        LocalDateTime now=LocalDateTime.now(ZoneOffset.UTC);
        return "VALID".equals(d.getSourceStatus()) && d.getEffectiveFrom()!=null && !now.isBefore(d.getEffectiveFrom())
            && (d.getEffectiveUntil()==null||now.isBefore(d.getEffectiveUntil()));
    }
    public static boolean reviewed(KnowledgeDocument d) {
        return d.isApproved()&&d.getReviewedRevision()==d.getRevision()&&!d.getReviewedBy().isBlank();
    }
    public static boolean retrievable(KnowledgeDocument d,String category) {
        return d!=null&&"PUBLISHED".equals(d.getState())&&reviewed(d)&&effective(d)
            && "READY".equals(d.getIndexState())&&d.getIndexedRevision()==d.getRevision()
            && (category==null ? !"INDUSTRY_REFERENCE".equals(d.getCategory()) : category.equals(d.getCategory()));
    }
}
