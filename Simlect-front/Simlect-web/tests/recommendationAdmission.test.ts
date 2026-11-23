import test from 'node:test';
import assert from 'node:assert/strict';
import {admittedProducts,consumerReasons} from '../src/utils/recommendationAdmission.ts';
test('unknown/demo/test cards never imply real commercial recommendation',()=>{assert.deepEqual(admittedProducts([{dataClass:'UNKNOWN'},{dataClass:'DEMO'},{dataClass:'TEST'},{}]),[]);});
test('real card needs field-level live provenance',()=>{const p={dataClass:'REAL',dataProvenance:{sourceType:'LIVE_API',fieldSources:{price:'LIVE_API',sku:'LIVE_API',stock:'LIVE_API'}}};assert.equal(admittedProducts([p]).length,1);p.dataProvenance.fieldSources.stock='SYNTHETIC';assert.equal(admittedProducts([p]).length,0);});
test('consumer reasons deduplicate without exposing objects',()=>{assert.deepEqual(consumerReasons(['同一规格','同一规格',{},null]),['同一规格']);});
test('approved local storefront cards display without pretending to be supplier REAL data',()=>{const p={dataClass:'LOCAL_STORE',dataProvenance:{catalogueStatus:'LOCAL_STORE',sourceType:'PUBLIC_DATASET',fieldSources:{price:'MANUAL',sku:'MANUAL',stock:'SYNTHETIC'}}};assert.equal(admittedProducts([p]).length,1);p.dataProvenance.catalogueStatus='';assert.equal(admittedProducts([p]).length,0)});
