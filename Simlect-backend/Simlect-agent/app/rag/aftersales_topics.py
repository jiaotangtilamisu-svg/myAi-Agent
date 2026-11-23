"""Query intent and evidence suitability, independent of legal conclusions."""
import re

TOPICS = {
    'QUALITY': (r'质量|瑕疵|破损|故障', ('质量', '瑕疵', '不符合', '修理', '更换')),
    'FREIGHT': (r'运费|邮费|寄回费用', ('运费', '运输', '费用')),
    'OPENED': (r'拆封|包装|使用过', ('拆封', '完好', '查验', '使用')),
    'SHOP_PROMISE': (r'商城承诺|商城.*期限|平台承诺|自有规则', ()),
    'NO_REASON': (r'七[天日]|7[天日]|无理由', ('七日', '七天', '无理由')),
    'REFUND': (r'退款|退钱', ('退款', '返还', '退还')),
    'REPAIR_EXCHANGE': (r'换货|维修|修理', ('更换', '修理', '退货')),
}


def topic(query):
    return next((name for name, (pattern, _) in TOPICS.items() if re.search(pattern, query)), 'GENERAL')


def applicable(query, hit):
    kind = topic(query)
    if kind == 'SHOP_PROMISE':
        # Existing PLATFORM_DEMO category is not an approved commercial promise.
        return False
    terms = TOPICS.get(kind, ('', ()))[1]
    return not terms or any(t in hit.get('text', '') for t in terms)


def keyword_filter(query):
    terms = TOPICS.get(topic(query), ('', ()))[1]
    return {'bool': {'should': [{'match_phrase': {'content': t}} for t in terms],
                     'minimum_should_match': 1}} if terms else None
