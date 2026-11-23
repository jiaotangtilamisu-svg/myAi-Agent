"""Consumer wording from explicit query/filter outcomes, not model guesses."""
LABELS={'PRICE_RANGE':'已核实规格超出价格范围','UNKNOWN_PRICE_FOR_BUDGET':'规格价格未知，不能确认符合预算',
        'SKU_ATTRIBUTES':'规格属性不符合要求或缺少可核实属性','NO_STOCK':'符合条件的规格库存为零',
        'STOCK_UNKNOWN':'符合条件的规格库存待确认','STOCK_UNAVAILABLE':'库存服务暂不可用',
        'BRAND_UNKNOWN_OR_MISMATCH':'品牌不符或缺少品牌依据','EXCLUDED_OR_UNKNOWN_BRAND':'品牌被排除或无法核实品牌',
        'CATEGORY_UNKNOWN_OR_MISMATCH':'品类不符或尚未核实','CATEGORY_MISMATCH':'品类不符合要求',
        'NOT_ON_SALE':'商品未在售','UNVERIFIED_LIVE_PROVENANCE':'缺少已核实的商业数据来源'}
def explain_unmatched(result):
    if result.get('recommendations'):return ''
    if result.get('status')=='TOOL_ERROR':return '商品业务工具查询失败，暂不能核实商品或库存；这不代表商品不存在。'
    reasons=[]
    for item in result.get('excluded',[]):
        for code in [item.get('reason'),*(item.get('failureReasons') or [])]:
            if code in LABELS and LABELS[code] not in reasons:reasons.append(LABELS[code])
    retrieval=result.get('retrieval') or {}
    if any(v in {'DEGRADED','UNAVAILABLE','EMBEDDING_FAILED'} for v in retrieval.values()):
        reasons.append('部分检索服务不可用，当前结果不能证明完整目录中没有该商品')
    return '未推荐原因：'+'；'.join(reasons)+'。未放宽品类、预算或规格要求。' if reasons else ''
