/** Verified read-only capabilities; no membership, rewards or transaction promises. */
export type AgentMode = 'support' | 'shopping' | 'supervisor';
export const AGENT_CAPABILITIES = [
  { id: 'own-orders', modes: ['support', 'supervisor'], text: '查询我自己的订单列表', tool: 'QUERY_ORDERS' },
  { id: 'exchange-policy', modes: ['support', 'supervisor'], text: '如何换货？请查询现有售后政策，不要提交申请', tool: 'policy_retrieval' },
  { id: 'return-policy', modes: ['support', 'supervisor'], text: '商品超过七天还能退货吗？请提供政策依据', tool: 'policy_retrieval' },
  { id: 'shopping-cup', modes: ['shopping', 'supervisor'], text: '帮我推荐20块钱以内的茶杯', tool: 'SEARCH_PRODUCTS' },
  { id: 'shopping-phone', modes: ['shopping'], text: '推荐3000元以内的手机', tool: 'SEARCH_PRODUCTS' },
  { id: 'shopping-compare', modes: ['shopping'], text: '把刚才三个商品对比一下', tool: 'GET_PRODUCT_DETAIL' },
  {id:'return-request',modes:['support','supervisor'],text:'我要退货',tool:'QUERY_ORDERS'},
  {id:'case-progress',modes:['support','supervisor'],text:'查看售后申请进度',tool:'case_query'},
  {id:'logistics',modes:['support','supervisor'],text:'查询订单物流',tool:'QUERY_LOGISTICS'},
  {id:'samsung-floor',modes:['shopping','supervisor'],text:'推荐5000元以上的三星手机',tool:'SEARCH_PRODUCTS'},
  { id: 'composite' , modes: ['supervisor'], text: '查询退货政策，另外推荐20元以内的茶杯', tool: 'aftersales+shopping' },
] as const;

export function quickQuestions(mode: AgentMode): string[] {
  return AGENT_CAPABILITIES.filter(c => (c.modes as readonly string[]).includes(mode)).map(c => c.text);
}
