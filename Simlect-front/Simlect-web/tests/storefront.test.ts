import test from 'node:test';
import assert from 'node:assert/strict';
import {diverseProducts,visibleCatalogueRoots} from '../src/utils/storefront.ts';
import {resolveImageUrl} from '../src/utils/image.ts';

test('reference taxonomy keeps all nine departments independent of first-page products',()=>{
 const ids=['10001','10002','10003','10004','10005','10006','10007','10011','64617'];
 const roots=[{categoryId:'A310'},...ids.map(categoryId=>({categoryId}))];
 assert.deepEqual(visibleCatalogueRoots(roots,[{categoryId:'20003'}]).map(c=>c.categoryId),ids);
});
test('mixed local and remote gallery covers retain each original image',()=>{
 assert.equal(resolveImageUrl('catalogue/reference/a.img,https://www.simlect.com/image2',{index:1}),'https://www.simlect.com/image2');
 assert.equal(resolveImageUrl('https://www.simlect.com/image1,https://www.simlect.com/image2',{index:1}),'https://www.simlect.com/image2');
});
test('homepage balances actual categories without duplicating or mutating products',()=>{
 const items=[{categoryId:'cases',price:19.9},{categoryId:'cases',price:29.9},{categoryId:'cups',price:39.9},{categoryId:'headsets',price:89.9}];
 const before=JSON.stringify(items),result=diverseProducts(items);
 assert.deepEqual(result.slice(0,3).map(p=>p.categoryId),['cases','cups','headsets']);
 assert.equal(new Set(result).size,4);assert.equal(JSON.stringify(items),before);assert.equal(result[3],items[1]);
});
test('retained offline demo category is not shown as current homepage merchandise',()=>{
 const roots=[{categoryId:'old',children:[{categoryId:'demo'}]},{categoryId:'new',children:[{categoryId:'cups'}]}];
 assert.deepEqual(visibleCatalogueRoots(roots,[{categoryId:'cups'}]),[roots[1]]);
 assert.deepEqual(visibleCatalogueRoots(roots,[]),roots);
});
