package com.simlect.config;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** Only deployment configuration may select the separate provenance schema. */
@Component
public class CatalogueSchemaGuard {
    @Value("${mybatis.configuration-properties.catalogueSchema:simlect_data_governance}")
    private String schema;

    @PostConstruct
    public void validate() {
        if (schema == null || !schema.matches("[A-Za-z][A-Za-z0-9_]{0,63}")) {
            throw new IllegalStateException("Invalid catalogue schema identifier");
        }
    }
}
