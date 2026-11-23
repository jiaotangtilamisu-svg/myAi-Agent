import test from 'node:test';
import assert from 'node:assert/strict';
import { dataOriginLabel } from '../src/utils/dataProvenance.ts';
test('missing provenance is never promoted to live commerce',()=>assert.equal(dataOriginLabel(null),'业务来源未登记'));
test('historical records are visibly historical',()=>assert.match(dataOriginLabel({sourceType:'PUBLIC_DATASET'}),/非当前交易/));
test('synthetic fields stay visible in a manual catalogue',()=>assert.match(dataOriginLabel({sourceType:'MANUAL',fieldSources:{price:'SYNTHETIC'}}),/含合成字段/));
test('unknown type does not claim live API',()=>assert.equal(dataOriginLabel({sourceType:'UNKNOWN'}),'业务来源未登记'));
