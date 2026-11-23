<!-- [zh] SFC 区块开始（单文件组件 template/script/style 三段） -->
<template>
  <!-- [zh] 开始标签 `<div>` -->
  <div v-if="showAi" class="bubble-row ai">
    <!-- [zh] 开始标签 `<div>` -->
    <div class="ai-avatar-mini">
      <!-- [zh] 开始标签 `<el-icon>` -->
      <el-icon :size="16"><Service /></el-icon>
    <!-- [zh] 闭合标签 `</div>` -->
    </div>
    <!-- [zh] 开始标签 `<div>` -->
    <div class="bubble ai-bubble" :class="{ 'is-wide': isWideBubble }">
      <!-- [zh] 开始标签 `<div>` -->
      <div v-if="messageStatus === 0 && !hasRenderableContent" class="cancel-tip">已取消回复</div>
      <!-- [zh] SFC 区块开始（单文件组件 template/script/style 三段） -->
      <template v-else>
      <p v-if="executions.length" role="status" class="agent-execution-status">
        <span v-for="entry in executions" :key="entry.agent">{{ agentLabel(entry.agent) }}：{{ phaseLabel(entry.status) }}　</span>
      </p>
      <template v-if="policyAnswer">
        <p role="status">{{ policyNotice(policyAnswer) }}</p>
        <MarkdownContent :content="displayText" :agent-rich="agentRich" />
        <details aria-label="完整政策证据">
          <summary>完整政策来源（{{ policyAnswer.hits.length }}条）</summary>
          <section v-for="hit in policyAnswer.hits" :key="hit.chunkId">
            <p>{{ hit.documentName }} / 版本 {{ hit.revision }} / {{ hit.section }}</p>
            <p>文档ID：{{ hit.documentId }}；Chunk ID：{{ hit.chunkId }}</p>
            <p>来源：{{ hit.source }}；发布机构：{{ hit.issuer || '未提供' }}</p>
            <a v-if="policySourceUrl(hit.originalUrl)" :href="policySourceUrl(hit.originalUrl)" target="_blank" rel="noopener noreferrer">官方原始来源</a>
            <blockquote style="white-space: pre-wrap">{{ hit.text }}</blockquote>
          </section>
        </details>
      </template>
      <template v-else-if="supervisorPayload">
        <MarkdownContent :content="supervisorPayload.intro" />
        <AgentProductList v-if="supervisorPayload.products.length" :list="supervisorPayload.products" />
        <el-button size="small" plain :loading="evidenceLoading" @click="loadSupervisorEvidence">查看详细依据</el-button>
        <p v-if="evidenceError">{{ evidenceError }}</p>
        <section v-if="fullReport" aria-label="完整查询依据">
          <p v-if="fullOrder">订单：{{ fullOrder.orderId || '未确定' }}；{{ fullOrder.orderFacts?.queryStatus === 'SUCCESS' ? '已取得本人订单事实' : '订单事实尚未核实' }}</p>
          <p v-for="(reason, index) in (fullOrder?.diagnosis?.reasons || [])" :key="`reason-${index}`">{{ reason }}</p>
          <p v-for="(reason, index) in (fullOrder?.diagnosis?.conflicts || [])" :key="`conflict-${index}`">证据冲突：{{ reason }}</p>
          <p v-for="(reason, index) in (fullOrder?.diagnosis?.uncertainties || [])" :key="`unknown-${index}`">待核实：{{ reason }}</p>
          <div v-for="(hit, index) in fullPolicies" :key="hit.chunkId || index">
            <p>{{ hit.documentName }} / 版本 {{ hit.revision }} / {{ hit.section }}；来源：{{ hit.source }}</p>
            <blockquote>{{ hit.text }}</blockquote>
          </div>
          <div v-for="product in fullProducts" :key="product.productId">
            <p>{{ product.productName }}；数据时间：{{ product.queryTime }}</p>
            <p v-for="(sku, index) in product.skus" :key="sku.sku_id || index">
              {{ sku.sku_name || sku.sku_id || '规格名称未知' }}；价格：{{ sku.price ?? '未知' }}{{ sku.price != null ? '元' : '' }}；{{ stockText(sku) }}
            </p>
          </div>
          <p>审批通过仅允许人工处理；本助手没有执行交易、退款或审批。</p>
        </section>
      </template>
      <!-- [zh] SFC 区块开始（单文件组件 template/script/style 三段） -->
      <template v-else-if="productList?.length">
        <!-- [zh] 开始标签 `<MarkdownContent>` -->
        <MarkdownContent
          v-if="productIntro"
          class="product-intro"
          :content="productIntro"
        />
        <!-- [zh] 开始标签 `<p>` -->
        <p v-else class="biz-title">为您推荐以下商品</p>
        <!-- [zh] 开始标签 `<AgentProductList>` -->
        <AgentProductList :list="productList" />
      </template>
      <!-- [zh] SFC 区块开始（单文件组件 template/script/style 三段） -->
      <template v-else-if="isProductSearchEmpty">
        <!-- [zh] 开始标签 `<p>` -->
        <p class="biz-title">商品搜索</p>
        <!-- [zh] 开始标签 `<p>` -->
        <p class="empty-hint">未找到符合条件的商品，请调整关键词或预算；不会用无关商品补足。</p>
      </template>
      <!-- [zh] SFC 区块开始（单文件组件 template/script/style 三段） -->
      <template v-else-if="orderList?.length">
        <!-- [zh] 开始标签 `<p>` -->
        <p class="biz-title">为您查询到以下订单</p>
        <!-- [zh] 开始标签 `<AgentOrderList>` -->
        <AgentOrderList :list="orderList" />
      </template>
      <!-- [zh] SFC 区块开始（单文件组件 template/script/style 三段） -->
      <template v-else-if="actionConfirmCard">
        <!-- [zh] 开始标签 `<AgentConfirmCard>` -->
        <AgentConfirmCard :card="actionConfirmCard" @updated="onActionCardUpdated" />
      </template>
      <!-- [zh] SFC 区块开始（单文件组件 template/script/style 三段） -->
      <template v-else-if="isOrderSearchEmpty">
        <!-- [zh] 开始标签 `<p>` -->
        <p class="biz-title">订单查询</p>
        <!-- [zh] 开始标签 `<p>` -->
        <p class="empty-hint">未查询到相关订单，请核对订单号或稍后再试。</p>
      </template>
      <!-- [zh] SFC 区块开始（单文件组件 template/script/style 三段） -->
      <template v-else-if="isStreaming && streamText">
        <!-- [zh] 开始标签 `<p>` -->
        <p class="stream-text">
          <!-- [zh] 开始标签 `<span>` -->
          <span>{{ streamText }}</span>
          <!-- [zh] 开始标签 `<span>` -->
          <span class="stream-cursor" aria-hidden="true" />
        <!-- [zh] 闭合标签 `</p>` -->
        </p>
      </template>
      <!-- [zh] SFC 区块开始（单文件组件 template/script/style 三段） -->
      <template v-else-if="isStreaming || waiting">
        <!-- [zh] 开始标签 `<p>` -->
        <p class="typing">正在为您查询，请稍候…</p>
      </template>
      <!-- [zh] SFC 区块开始（单文件组件 template/script/style 三段） -->
      <template v-else-if="displayText">
        <!-- [zh] 开始标签 `<MarkdownContent>` -->
        <MarkdownContent :content="displayText" :agent-rich="agentRich" />
      </template>
      <p v-if="messageStatus === 3 && hasRenderableContent" class="interrupt-tip">回复已中断，以上为已生成内容</p>
      <details v-if="messageStatus===2 && fullOrder && !supervisorPayload" aria-label="订单核实与完整政策依据">
        <summary>查看订单核实与完整政策依据</summary>
        <p v-for="(reason,i) in fullOrder.diagnosis?.reasons || []" :key="`fact-${i}`">{{reason}}</p>
        <p v-for="(reason,i) in fullOrder.diagnosis?.uncertainties || []" :key="`pending-${i}`">待核实：{{reason}}</p>
        <section v-for="(hit,i) in fullPolicies" :key="hit.chunkId || i">
          <p>{{hit.documentName}} / 版本{{hit.revision}} / {{hit.section}}</p>
          <p>文档ID：{{hit.documentId}}；Chunk ID：{{hit.chunkId}}</p>
          <a v-if="policySourceUrl(hit.originalUrl || hit.source)" :href="policySourceUrl(hit.originalUrl || hit.source)" target="_blank" rel="noopener noreferrer">官方来源</a>
          <blockquote style="white-space:pre-wrap">{{hit.text}}</blockquote>
        </section>
        <p v-if="policyView.error" role="alert">{{policyView.error}}</p><p v-else-if="!fullPolicies.length">当前没有可用政策原文，具体条件仍需人工核实。</p>
      </details>
      <AgentCasePanel v-if="messageStatus===2 && (fullOrder || showSavedCases || supervisorPayload?.showCaseProgress===true || supervisorPayload?.canCreateCase===true)" :order-id="caseOrderId" :message-id="Number(data.messageId)" :suggested-type="fullOrder?.suggestedApplicationType" :eligible="(fullOrder?.orderFacts?.queryStatus==='SUCCESS' && fullOrder?.businessIntent!=='CANCEL_ORDER') || supervisorPayload?.canCreateCase===true" />
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { Service } from '@element-plus/icons-vue';
import { consumerProductCopy } from '@/utils/consumerProductCopy';
import MarkdownContent from '@/components/common/MarkdownContent.vue';
import AgentProductList from '@/components/agent/AgentProductList.vue';
import AgentOrderList from '@/components/agent/AgentOrderList.vue';
import AgentCasePanel from '@/components/agent/AgentCasePanel.vue';
import AgentConfirmCard, { type ActionConfirmCardData } from '@/components/agent/AgentConfirmCard.vue';
import { cleanAgentActionStreamText, containsAgentTable, stripEmbeddedProductJson } from '@/utils/agentMessageRender';
import { agentApi } from '@/api/modules';
import { parseSupervisor, validExecution, agentLabel, phaseLabel } from '@/utils/agentExecution';
import { parsePolicyAnswer, policyNotice, policySourceUrl, uniquePolicyHits } from '@/utils/agentPolicy';

const props = defineProps<{
  data: Record<string, any>;
  waiting?: boolean;
}>();

const messageStatus = computed(() => Number(props.data.status ?? 2));
const policyAnswer = computed(() => messageStatus.value === 2 ? parsePolicyAnswer(props.data.bizData, Number(props.data.messageId)) : null);

const isStreaming = computed(() => messageStatus.value === 1);
const supervisorPayload = computed(() => isStreaming.value ? null : parseSupervisor(props.data.assistantMessage));
const executions = computed(() => supervisorPayload.value?.agents || (Array.isArray(props.data.agentStatuses) ? props.data.agentStatuses.filter(validExecution) : []));
const fullReport = ref<Record<string, any> | null>(null);
const persistedReport=computed(()=>{try{const v=typeof props.data.bizData==='string'?JSON.parse(props.data.bizData):props.data.bizData;return v?.fullReport || null}catch{return null}});
const evidenceLoading = ref(false);
const evidenceError = ref('');
const fullOrder = computed(() => {
  const report=(fullReport.value || persistedReport.value)?.results?.aftersales?.data?.diagnosis;
  if(report)return report;
  try {const saved=typeof props.data.bizData==='string'?JSON.parse(props.data.bizData):props.data.bizData;return saved?.aftersalesDiagnosis || null;}catch{return null;}
});
const policyView = computed(()=>{try{return {hits:uniquePolicyHits(fullOrder.value?.policyEvidence?.hits || (fullReport.value || persistedReport.value)?.results?.aftersales?.data?.policy?.hits || []),error:''}}catch{return {hits:[],error:'政策证据内容存在冲突，暂不能作为依据，请重新查询。'}}});
const fullPolicies=computed(()=>policyView.value.hits);
const showSavedCases=computed(()=>{try{const v=typeof props.data.bizData==='string'?JSON.parse(props.data.bizData):props.data.bizData;return v?.showCaseProgress===true}catch{return false}});
const caseOrderId=computed(()=>{try{const v=typeof props.data.bizData==='string'?JSON.parse(props.data.bizData):props.data.bizData;return fullOrder.value?.orderId || v?.caseOrderId || persistedReport.value?.results?.aftersales?.data?.caseOrderId || undefined}catch{return undefined}});
const fullProducts = computed(() => (fullReport.value || persistedReport.value)?.results?.shopping?.data?.shopping?.recommendations || []);
const stockText = (sku: Record<string, any>) => sku.stock_query_status === 'SUCCESS' && Number.isInteger(sku.stock) && sku.stock >= 0 ? `库存：${sku.stock}` : '库存待确认';
const loadSupervisorEvidence = async () => {
  evidenceLoading.value = true; evidenceError.value = '';
  try { fullReport.value = persistedReport.value || await agentApi.supervisorResult(Number(props.data.messageId)); }
  catch { evidenceError.value = '完整证据暂不可用或已过期，请重新查询。'; }
  finally { evidenceLoading.value = false; }
};

const parseJsonList = (raw?: string | null) => {
  if (!raw || typeof raw !== 'string') return null;
  const text = raw.trim();
  if (!text.startsWith('[') && !text.startsWith('{')) return null;
  try {
    const parsed = JSON.parse(text);
    if (Array.isArray(parsed)) return parsed;
    if (parsed && Array.isArray(parsed.list)) return parsed.list;
    return null;
  } catch {
    return null;
  }
};

const isEmptyJsonList = (raw?: string | null) => {
  const parsed = parseJsonList(raw);
  if (parsed !== null) return parsed.length === 0;
  return typeof raw === 'string' && raw.trim() === '[]';
};

const isProductBiz = (bizType?: string | null) =>
  bizType === 'product_search' ||
  bizType === 'product_search.txt' ||
  bizType === 'BROWSE_RECOMMEND';

const isOrderBiz = (bizType?: string | null) =>
  bizType === 'query_order' || bizType === 'query_order.txt';

const looksLikeOrderCards = (list: unknown[] | null) => {
  if (!list?.length) return false;
  const first = list[0] as Record<string, unknown> | null;
  return !!(first && typeof first === 'object' && (first.orderId || first.order_id));
};

const parseJsonObject = (raw?: string | null) => {
  if (!raw || typeof raw !== 'string') return null;
  const text = raw.trim();
  if (!text.startsWith('{')) return null;
  try {
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
};

const actionConfirmCard = ref<ActionConfirmCardData | null>(null);

const syncActionConfirmCard = () => {
  if (isStreaming.value) {
    actionConfirmCard.value = null;
    return;
  }
  const parsed = parseJsonObject(props.data.assistantMessage);
  if (parsed?.type === 'ACTION_CONFIRM') {
    actionConfirmCard.value = {
      ...(parsed as ActionConfirmCardData),
      status: Number((parsed as ActionConfirmCardData).status ?? 0)
    };
    return;
  }
  actionConfirmCard.value = null;
};

watch(
  () => [props.data.assistantMessage, props.data.bizType, props.data.status, props.waiting] as const,
  () => syncActionConfirmCard(),
  { immediate: true }
);

const onActionCardUpdated = (card: ActionConfirmCardData) => {
  actionConfirmCard.value = card;
};

const productSearchPayload = computed(() => {
  if (isStreaming.value) return null;
  const raw = props.data.assistantMessage;
  if (!raw || typeof raw !== 'string') return null;
  const text = raw.trim();
  if (!text.startsWith('{')) return null;
  try {
    const parsed = JSON.parse(text);
    if (parsed?.type === 'PRODUCT_SEARCH_RESULT' && Array.isArray(parsed.products)) {
      return {
        intro: typeof parsed.intro === 'string' ? parsed.intro.trim() : '',
        products: parsed.products
      };
    }
  } catch {
    return null;
  }
  return null;
});

const productList = computed(() => {
  if (isStreaming.value) return null;
  const wrapped = productSearchPayload.value;
  const fromWrapped = (wrapped?.products || []).filter(
    (p: any) => p?.productId && (p?.productName || p?.product_name)
  );
  if (fromWrapped.length) return fromWrapped;
  const raw = props.data.assistantMessage;
  const parsed = parseJsonList(raw);
  if (!parsed?.length) return null;
  const usable = parsed.filter((p: any) => p?.productId && (p?.productName || p?.product_name));
  if (!usable.length) return null;
  if (isProductBiz(props.data.bizType)) return usable;
  if (usable[0]?.productId && usable[0]?.productName) return usable;
  return null;
});

const productIntro = computed(() =>
  stripEmbeddedProductJson(productSearchPayload.value?.intro || '')
);

const isProductSearchEmpty = computed(() => {
  if (isStreaming.value || props.waiting) return false;
  if (!isProductBiz(props.data.bizType)) return false;
  if (productSearchPayload.value) return !productSearchPayload.value.products.length;
  return isEmptyJsonList(props.data.assistantMessage);
});

const orderList = computed(() => {
  if (isStreaming.value) return null;
  const parsed = parseJsonList(props.data.assistantMessage);
  if (looksLikeOrderCards(parsed)) return parsed;
  if (!isOrderBiz(props.data.bizType)) return null;
  if (!parsed?.length) return null;
  return parsed;
});

const isOrderSearchEmpty = computed(() => {
  if (isStreaming.value || props.waiting) return false;
  if (!isOrderBiz(props.data.bizType)) return false;
  if (looksLikeOrderCards(parseJsonList(props.data.assistantMessage))) return false;
  return isEmptyJsonList(props.data.assistantMessage);
});

const streamText = computed(() => cleanAgentActionStreamText(props.data.assistantMessage));

const displayText = computed(() => {
  if (productList.value?.length || orderList.value?.length) return '';
  if (actionConfirmCard.value) return '';
  if (isProductSearchEmpty.value || isOrderSearchEmpty.value) return '';
  const parsed = parseJsonObject(props.data.assistantMessage);
  if (parsed?.type === 'ACTION_CONFIRM') return '';
  if (parsed?.type === 'PRODUCT_SEARCH_RESULT') return '';
  let text = (props.data.assistantMessage || '').trim();
  if (text === '[]') return '';
  // Hide bare product-id JSON arrays the model sometimes dumps.
  const asList = parseJsonList(text);
  if (
    asList?.length &&
    asList.every((p: any) => p?.productId && !(p?.productName || p?.product_name))
  ) {
    return '';
  }
  text = stripEmbeddedProductJson(text);
  return consumerProductCopy(text);
});

const agentRich = computed(
  () =>
    props.data.bizType === 'query_logistics' ||
    props.data.bizType === 'product_consult' ||
    containsAgentTable(displayText.value)
);

const showAi = computed(() => {
  if (messageStatus.value === 0) return hasRenderableContent.value;
  if (props.waiting) return true;
  if (isStreaming.value) return true;
  if (messageStatus.value === 3) return hasRenderableContent.value;
  if (productList.value?.length || orderList.value?.length) return true;
  if (actionConfirmCard.value) return true;
  if (isProductSearchEmpty.value || isOrderSearchEmpty.value) return true;
  if (displayText.value) return true;
  return false;
});

const hasRenderableContent = computed(
  () =>
    !!(productList.value?.length ||
      orderList.value?.length ||
      actionConfirmCard.value ||
      isProductSearchEmpty.value ||
      isOrderSearchEmpty.value ||
      displayText.value ||
      props.waiting ||
      (isStreaming.value && streamText.value))
);

const isWideBubble = computed(
  () =>
    !!(
      productList.value?.length ||
      orderList.value?.length ||
      actionConfirmCard.value ||
      isProductSearchEmpty.value ||
      isOrderSearchEmpty.value ||
      agentRich.value
    )
);
</script>

/* [zh] 样式声明 */
<style scoped lang="scss">
/* [zh] 样式规则 `@use '@/styles/variables' as *;` */
@use '@/styles/variables' as *;

/* [zh] 样式规则 `.bubble-row.ai {` */
.bubble-row.ai {
  /* [zh] 样式规则 `display: flex;` */
  display: flex;
  /* [zh] 样式规则 `justify-content: flex-start;` */
  justify-content: flex-start;
  /* [zh] 样式规则 `align-items: flex-start;` */
  align-items: flex-start;
  /* [zh] 样式规则 `gap: 8px;` */
  gap: 8px;
  /* [zh] 样式规则 `width: 100%;` */
  width: 100%;
  /* [zh] 样式规则 `box-sizing: border-box;` */
  box-sizing: border-box;
  /* [zh] 样式规则 `margin-bottom: 8px;` */
  margin-bottom: 8px;
/* [zh] 样式规则 `}` */
}

/* [zh] 样式规则 `.bubble {` */
.bubble {
  /* [zh] 样式规则 `width: fit-content;` */
  width: fit-content;
  /* [zh] 样式规则 `max-width: min(75%, 520px);` */
  max-width: min(75%, 520px);
  /* [zh] 样式规则 `padding: 9px 12px;` */
  padding: 9px 12px;
  /* [zh] 样式规则 `font-size: 13px;` */
  font-size: 13px;
  /* [zh] 样式规则 `line-height: 1.45;` */
  line-height: 1.45;
  /* [zh] 样式规则 `border-radius: 12px;` */
  border-radius: 12px;
  /* [zh] 样式规则 `word-break: break-word;` */
  word-break: break-word;
  /* [zh] 样式规则 `flex: 0 1 auto;` */
  flex: 0 1 auto;
  /* [zh] 样式规则 `min-width: 0;` */
  min-width: 0;
/* [zh] 样式规则 `}` */
}

/* [zh] 样式规则 `.ai-avatar-mini {` */
.ai-avatar-mini {
  /* [zh] 样式规则 `width: 28px;` */
  width: 28px;
  /* [zh] 样式规则 `height: 28px;` */
  height: 28px;
  /* [zh] 样式规则 `flex-shrink: 0;` */
  flex-shrink: 0;
  /* [zh] 样式规则 `border-radius: 50%;` */
  border-radius: 50%;
  /* [zh] 样式规则 `background: $color-card;` */
  background: $color-card;
  /* [zh] 样式规则 `color: $color-primary;` */
  color: $color-primary;
  /* [zh] 样式规则 `display: grid;` */
  display: grid;
  /* [zh] 样式规则 `place-items: center;` */
  place-items: center;
  /* [zh] 样式规则 `box-shadow: $shadow-xs;` */
  box-shadow: $shadow-xs;
/* [zh] 样式规则 `}` */
}

/* [zh] 样式规则 `.ai-bubble {` */
.ai-bubble {
  /* [zh] 样式规则 `background: $color-card;` */
  background: $color-card;
  /* [zh] 样式规则 `color: $color-text-body;` */
  color: $color-text-body;
  /* [zh] 样式规则 `border-bottom-left-radius: 4px;` */
  border-bottom-left-radius: 4px;
  /* [zh] 样式规则 `box-shadow: $shadow-xs;` */
  box-shadow: $shadow-xs;

  /* [zh] 样式规则 `&.is-wide {` */
  &.is-wide {
    /* [zh] 样式规则 `width: auto;` */
    width: auto;
    /* [zh] 样式规则 `max-width: calc(100% - 36px);` */
    max-width: calc(100% - 36px);
    /* [zh] 样式规则 `flex: 1 1 auto;` */
    flex: 1 1 auto;
    /* [zh] 样式规则 `min-width: 0;` */
    min-width: 0;
  /* [zh] 样式规则 `}` */
  }
/* [zh] 样式规则 `}` */
}

/* [zh] 样式规则 `.biz-title {` */
.biz-title {
  /* [zh] 样式规则 `margin: 0 0 8px;` */
  margin: 0 0 8px;
  /* [zh] 样式规则 `font-size: 13px;` */
  font-size: 13px;
  /* [zh] 样式规则 `color: $color-text-title;` */
  color: $color-text-title;
/* [zh] 样式规则 `}` */
}

/* [zh] 样式声明 */
.typing,
/* [zh] 样式声明 */
.cancel-tip,
/* [zh] 样式声明 */
.interrupt-tip,
/* [zh] 样式规则 `.empty-hint {` */
.empty-hint {
  /* [zh] 样式规则 `margin: 0;` */
  margin: 0;
  /* [zh] 样式规则 `font-size: 13px;` */
  font-size: 13px;
  /* [zh] 样式规则 `color: $color-text-muted;` */
  color: $color-text-muted;
/* [zh] 样式规则 `}` */
}

/* [zh] 样式规则 `.interrupt-tip {` */
.interrupt-tip {
  /* [zh] 样式规则 `margin-top: 8px;` */
  margin-top: 8px;
  /* [zh] 样式规则 `font-size: 12px;` */
  font-size: 12px;
  /* [zh] 样式规则 `color: $color-text-muted;` */
  color: $color-text-muted;
/* [zh] 样式规则 `}` */
}

/* [zh] 样式规则 `.empty-hint {` */
.empty-hint {
  /* [zh] 样式规则 `line-height: 1.55;` */
  line-height: 1.55;
/* [zh] 样式规则 `}` */
}

/* [zh] 样式规则 `.product-intro {` */
.product-intro {
  /* [zh] 样式规则 `margin: 0 0 8px;` */
  margin: 0 0 8px;
/* [zh] 样式规则 `}` */
}

/* [zh] 样式规则 `.stream-text {` */
.stream-text {
  /* [zh] 样式规则 `margin: 0;` */
  margin: 0;
  /* [zh] 样式规则 `font-size: 13px;` */
  font-size: 13px;
  /* [zh] 样式规则 `line-height: 1.55;` */
  line-height: 1.55;
  /* [zh] 样式规则 `color: $color-text-body;` */
  color: $color-text-body;
  /* [zh] 样式规则 `white-space: pre-wrap;` */
  white-space: pre-wrap;
  /* [zh] 样式规则 `word-break: break-word;` */
  word-break: break-word;
/* [zh] 样式规则 `}` */
}

/* [zh] 样式规则 `.stream-cursor {` */
.stream-cursor {
  /* [zh] 样式规则 `display: inline-block;` */
  display: inline-block;
  /* [zh] 样式规则 `width: 2px;` */
  width: 2px;
  /* [zh] 样式规则 `height: 1em;` */
  height: 1em;
  /* [zh] 样式规则 `margin-left: 2px;` */
  margin-left: 2px;
  /* [zh] 样式规则 `vertical-align: text-bottom;` */
  vertical-align: text-bottom;
  /* [zh] 样式规则 `background: $color-primary;` */
  background: $color-primary;
  /* [zh] 样式规则 `animation: blink 0.9s step-end infinite;` */
  animation: blink 0.9s step-end infinite;
/* [zh] 样式规则 `}` */
}

/* [zh] 样式规则 `@keyframes blink {` */
@keyframes blink {
  /* [zh] 样式规则 `50% {` */
  50% {
    /* [zh] 样式规则 `opacity: 0;` */
    opacity: 0;
  /* [zh] 样式规则 `}` */
  }
/* [zh] 样式规则 `}` */
}

/* [zh] 样式规则 `:deep(.markdown-content) {` */
:deep(.markdown-content) {
  /* [zh] 样式规则 `font-size: 13px;` */
  font-size: 13px;
  /* [zh] 样式规则 `line-height: 1.45;` */
  line-height: 1.45;
  /* [zh] 样式规则 `max-width: 100%;` */
  max-width: 100%;

  /* [zh] 样式规则 `p {` */
  p {
    /* [zh] 样式规则 `margin: 0;` */
    margin: 0;

    /* [zh] 样式规则 `& + p {` */
    & + p {
      /* [zh] 样式规则 `margin-top: 6px;` */
      margin-top: 6px;
    /* [zh] 样式规则 `}` */
    }
  /* [zh] 样式规则 `}` */
  }
/* [zh] 样式规则 `}` */
}

/* [zh] 样式规则 `.ai-bubble:not(.is-wide) :deep(.markdown` */
.ai-bubble:not(.is-wide) :deep(.markdown-content) {
  /* [zh] 样式规则 `width: fit-content;` */
  width: fit-content;
/* [zh] 样式规则 `}` */
}

/* [zh] 样式规则 `:deep(.agent-orders) {` */
:deep(.agent-orders) {
  /* [zh] 样式规则 `font-size: 12px;` */
  font-size: 12px;
/* [zh] 样式规则 `}` */
}
</style>
