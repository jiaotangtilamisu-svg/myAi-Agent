package com.simlect.component;

import com.simlect.api.dto.ProductInfoDTO;
import org.junit.jupiter.api.Test;
import org.springframework.data.elasticsearch.core.mapping.SimpleElasticsearchMappingContext;
import org.springframework.data.elasticsearch.core.convert.ElasticsearchCustomConversions;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class IndexNamespaceTest {
    private String indexName() throws Exception {
        var context = new SimpleElasticsearchMappingContext();
        // Mirror Boot's conversion setup: BigDecimal is a scalar, not an entity
        // whose JDK-private fields should be reflectively mapped.
        context.setSimpleTypeHolder(new ElasticsearchCustomConversions(List.of()).getSimpleTypeHolder());
        context.afterPropertiesSet();
        return context.getRequiredPersistentEntity(ProductInfoDTO.class).getIndexCoordinates().getIndexName();
    }

    @Test void defaultIndexRemainsCompatible() throws Exception {
        String old=System.getProperty("simlect.product.index");
        try { System.clearProperty("simlect.product.index"); assertEquals("simlect-index",indexName()); }
        finally { if(old!=null)System.setProperty("simlect.product.index",old); }
    }

    @Test void explicitJvmIndexSelectsOnlyIsolatedNamespace() throws Exception {
        String old=System.getProperty("simlect.product.index");
        try { System.setProperty("simlect.product.index","q34_unit_products"); assertEquals("q34_unit_products",indexName()); }
        finally { if(old==null)System.clearProperty("simlect.product.index"); else System.setProperty("simlect.product.index",old); }
    }
}
