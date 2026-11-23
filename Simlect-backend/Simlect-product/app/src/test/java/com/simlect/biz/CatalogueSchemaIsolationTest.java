package com.simlect.biz;

import com.simlect.config.CatalogueSchemaGuard;
import com.simlect.mappers.PublicCatalogueMapper;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class CatalogueSchemaIsolationTest {
    @Test void mapperUsesDeploymentSchemaInsteadOfFormalSourceDatabase() {
        var configuration=new Configuration();
        var vars=new Properties();vars.setProperty("catalogueSchema","q34_unit_data_governance");
        configuration.setVariables(vars);configuration.addMapper(PublicCatalogueMapper.class);
        var sql=configuration.getMappedStatement(PublicCatalogueMapper.class.getName()+".localBindings").getBoundSql(Map.of("ids",List.of("DEMO34A1"))).getSql();
        assertTrue(sql.contains("q34_unit_data_governance.source_record"));
        assertFalse(sql.contains("simlect_data_governance"));
        assertFalse(sql.contains("DEMO34A1"));
    }
    @Test void invalidConfiguredIdentifierFailsClosed() {
        var guard=new CatalogueSchemaGuard();
        for(String value:Arrays.asList(null,"","schema;DROP DATABASE x","a.b","a`")) {
            ReflectionTestUtils.setField(guard,"schema",value);
            assertThrows(IllegalStateException.class,guard::validate);
        }
        ReflectionTestUtils.setField(guard,"schema","simlect_data_governance");
        assertDoesNotThrow(guard::validate);
    }
}
