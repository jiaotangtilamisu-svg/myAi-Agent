package com.simlect.biz;
import com.simlect.annotation.AdminSensitiveConfirm;
import com.simlect.controller.admin.ProductInfoController;
import com.simlect.component.ProductBloomFilterComponent;
import com.simlect.component.RedisComponent;
import com.simlect.entity.po.*;
import com.simlect.entity.query.*;
import com.simlect.exception.BusinessException;
import com.simlect.mappers.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import java.util.*;
import static org.mockito.Mockito.*;
import static org.junit.jupiter.api.Assertions.*;

@ExtendWith(MockitoExtension.class)
class CataloguePublicationServiceTest {
 @Mock ProductInfoMapper<ProductInfo,ProductInfoQuery> products;
 @Mock ProductSkuMapper<ProductSku,ProductSkuQuery> skus;
 @Mock ProductPropertyValueMapper<ProductPropertyValue,ProductPropertyValueQuery> properties;
 @Mock SysCategoryMapper<SysCategory,SysCategoryQuery> categories;
 @Mock PublicCatalogueMapper provenance;
 @Mock ProductBloomFilterComponent bloom;
 @Mock RedisComponent redis;
 @Spy @InjectMocks CataloguePublicationService service;
 @AfterEach void clear(){if(TransactionSynchronizationManager.isSynchronizationActive())TransactionSynchronizationManager.clearSynchronization();}
 Map<String,Object> plan(){return service.preview();}
 @Test void reviewedResourceHasExactly100MatchedProducts(){var p=plan();assertEquals(100,((List<?>)p.get("products")).size());CataloguePublicationService.validate(p);}
 @Test void invalidPlanCannotReachDatabase(){assertThrows(BusinessException.class,()->service.publish("forged"));verifyNoInteractions(products,skus,provenance);}
 @Test void rolledBackSourceCannotPublish(){when(provenance.lockAboBatch()).thenReturn("ROLLED_BACK");assertThrows(BusinessException.class,()->service.publish("ABO31_STOREFRONT_V1"));verifyNoInteractions(products,skus);}
 @Test void duplicateIdsAreRejected(){var p=plan();var list=(List<Map<String,Object>>)p.get("products");list.set(1,new HashMap<>(list.get(0)));assertThrows(IllegalArgumentException.class,()->CataloguePublicationService.validate(p));}
 @Test void untrustedImagePathIsRejected(){var p=plan();((Map)((List)p.get("products")).get(0)).put("cover","../../secret");assertThrows(IllegalArgumentException.class,()->CataloguePublicationService.validate(p));}
 @Test void unknownOrZeroPriceCannotPublish(){var p=plan();((Map)((List)p.get("products")).get(0)).put("price","0");assertThrows(IllegalArgumentException.class,()->CataloguePublicationService.validate(p));}
 @Test void partialImportNeverOverwritesExistingProduct(){when(provenance.lockAboBatch()).thenReturn("COMMITTED");when(products.selectByProductId("ABOB0896KVCJY")).thenReturn(new ProductInfo());assertThrows(BusinessException.class,()->service.publish("ABO31_STOREFRONT_V1"));verify(products,never()).insertBatch(any());verifyNoInteractions(skus);}
 @Test void publicationKeepsSkuPriceSameAndCreatesNoStock(){
  when(provenance.lockAboBatch()).thenReturn("COMMITTED");when(provenance.bindAboProduct(anyString(),anyString())).thenReturn(1);
  doNothing().when(service).verifyBackup(any());TransactionSynchronizationManager.initSynchronization();
  var r=service.publish("ABO31_STOREFRONT_V1");assertEquals(0,r.get("stockCreated"));assertEquals(0,r.get("embeddingRequests"));
  ArgumentCaptor<List<ProductInfo>> infos=ArgumentCaptor.forClass(List.class);verify(products).insertBatch(infos.capture());
  ArgumentCaptor<List<ProductSku>> skuList=ArgumentCaptor.forClass(List.class);verify(skus).insertBatch(skuList.capture());
  for(int i=0;i<100;i++){assertEquals(infos.getValue().get(i).getProductId(),skuList.getValue().get(i).getProductId());assertEquals(infos.getValue().get(i).getMinPrice(),skuList.getValue().get(i).getPrice());assertNull(skuList.getValue().get(i).getStock());}
  verify(products,never()).deleteByProductId(anyString());verifyNoInteractions(bloom,redis);
 }
 @Test void provenanceFailureAbortsAndMethodIsTransactional()throws Exception{
  when(provenance.lockAboBatch()).thenReturn("COMMITTED");doNothing().when(service).verifyBackup(any());
  assertThrows(BusinessException.class,()->service.publish("ABO31_STOREFRONT_V1"));
  assertNotNull(CataloguePublicationService.class.getMethod("publish",String.class).getAnnotation(Transactional.class));verifyNoInteractions(bloom,redis);
 }
 @Test void noBackupMeansNoPublication(){var p=plan();p.put("backupFile","nonexistent-stage31-backup");assertThrows(BusinessException.class,()->service.verifyBackup(p));}
 @Test void adminPublicationRequiresExistingSensitiveConfirmation()throws Exception{assertNotNull(ProductInfoController.class.getMethod("publishPublicCatalogue",String.class).getAnnotation(AdminSensitiveConfirm.class));}
}
