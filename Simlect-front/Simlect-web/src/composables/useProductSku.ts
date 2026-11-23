import { computed, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { productApi } from '@/api/modules';
import { isProductOnSale, pickDefaultSku } from '@/utils/product';
import { MAX_CART_QTY } from '@/constants/validation';
import { knownStock, priceText, skuPrice, purchasableSku } from '@/utils/trustedProduct';

export function useProductSku(getProductId: () => string) {
  const loading = ref(true);
  const productInfo = ref<Record<string, any> | null>(null);
  const productPropertyList = ref<any[]>([]);
  const skuList = ref<any[]>([]);
  const quantity = ref(1);
  const selectedSku = ref<Record<string, any>>({});
  const selectedProperty = reactive<Record<string, string>>({});

  const displayPrice = computed(() =>
    priceText(skuPrice(selectedSku.value, productInfo.value))
  );

  const maxBuy = computed(() => {
    const stock = knownStock(selectedSku.value) ?? 0;
    return Math.max(1, Math.min(stock, MAX_CART_QTY));
  });

  const coverImage = computed(() => {
    const cover = productInfo.value?.cover;
    if (!cover) return '';
    return String(cover).split(',')[0]?.trim() || '';
  });

  const buildSkuKey = (map: Record<string, string>) =>
    productPropertyList.value.map((p) => map[p.propertyId]).filter(Boolean).join('-');

  const initDefaultSku = () => {
    selectedSku.value = {};
    Object.keys(selectedProperty).forEach(k => delete selectedProperty[k]);
    const sku = pickDefaultSku(skuList.value);
    if (!sku) return;
    selectedSku.value = sku;
    const ids = String(selectedSku.value.propertyValueIds || '').split('-');
    productPropertyList.value.forEach((prop, index) => {
      const valId = ids[index];
      if (valId) selectedProperty[prop.propertyId] = valId;
    });
    quantity.value = 1;
  };

  const selectProperty = (property: Record<string, any>, propertyValue: Record<string, any>) => {
    const temp = { ...selectedProperty, [property.propertyId]: propertyValue.propertyValueId };
    const key = buildSkuKey(temp);
    const matched = skuList.value.find((sku) => sku.propertyValueIds === key);
    if (!matched) {
      ElMessage.warning('该规格组合暂不可售');
      return;
    }
    if (matched.stock === 0) {
      ElMessage.warning('该规格已售罄');
      return;
    }
    selectedProperty[property.propertyId] = propertyValue.propertyValueId;
    selectedSku.value = matched;
    if (knownStock(matched) != null && quantity.value > matched.stock) quantity.value = Math.max(1, matched.stock);
  };

  const load = async () => {
    const productId = getProductId();
    if (!productId) return;

    loading.value = true;
    try {
      const data = await productApi.getProduct(productId);
      productInfo.value = data?.productInfo || null;
      if (productInfo.value && !isProductOnSale(productInfo.value)) {
        ElMessage.warning('该商品已下架');
        productInfo.value = null;
        productPropertyList.value = [];
        skuList.value = [];
        return;
      }
      productPropertyList.value = data?.productPropertyList || [];
      skuList.value = data?.skuList || [];
      initDefaultSku();
    } finally {
      loading.value = false;
    }
  };

  const validateSku = () => {
    if (!selectedSku.value?.propertyValueIds) {
      ElMessage.warning('请选择商品规格');
      return false;
    }
    if (!purchasableSku(selectedSku.value)) { ElMessage.warning("价格或库存未知，或已售罄，暂不能加入购物车"); return false; }
    return true;
  };

  return {
    loading,
    productInfo,
    productPropertyList,
    skuList,
    quantity,
    selectedSku,
    selectedProperty,
    displayPrice,
    maxBuy,
    coverImage,
    selectProperty,
    load,
    validateSku
  };
}
