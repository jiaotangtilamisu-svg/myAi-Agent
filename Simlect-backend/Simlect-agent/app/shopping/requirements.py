"""Shopping constraints only; numbers extracted here are budgets, never product facts."""

import re
import unicodedata
from copy import deepcopy
from decimal import Decimal

CATEGORIES = {
    "手机壳": ("手机保护壳", "手机壳", "保护套"),
    "笔记本": ("笔记本电脑", "轻薄本", "游戏本"),
    "茶杯": ("茶杯", "喝茶的杯子"),
    "保温杯": ("保温杯",),
    "水杯": ("水杯", "运动水壶", "杯子"),
    "手机": ("智能手机", "手机", "手几"),
    "耳机": ("蓝牙耳机", "耳机", "耳几"),
    "音箱": ("蓝牙音箱", "桌面音响", "音箱", "音响"),
    "香水": ("香水",),
    "吉他": ("吉他",),
    "电脑": ("台式电脑", "电脑"),
    "平板": ("平板电脑", "平板"),
    "键盘": ("机械键盘", "键盘"),
    "鼠标": ("鼠标",),
    "零食": ("零食",),
    "鞋": ("运动鞋", "鞋"),
    "台灯": ("台灯", "阅读灯", "书桌灯"),
    "家电": ("家电", "家用电器"),
}
# A canonical category name is always a valid surface form, not only its aliases.
CATEGORIES = {name: tuple(dict.fromkeys((name, *aliases))) for name, aliases in CATEGORIES.items()}
BRANDS = {
    "华为": ("华为", "huawei"),
    "小米": ("小米", "xiaomi", "redmi", "红米"),
    "苹果": ("苹果", "apple", "iphone"),
    "荣耀": ("荣耀", "honor"),
    "OPPO": ("OPPO",),
    "vivo": ("vivo",),
    "联想": ("联想", "lenovo"),
    "戴尔": ("戴尔", "dell"),
    "惠普": ("惠普", "hp"),
    "三星": ("三星", "samsung", "galaxy"),
    "索尼": ("索尼", "sony"),
    "华硕": ("华硕", "asus"),
}
COLORS = ("白色", "黑色", "银色", "蓝色", "红色", "灰色", "绿色", "粉色")
SCENES = ("办公", "游戏", "学习", "通勤", "旅行", "摄影", "运动", "日常")
NUMBER = r"(\d+(?:\.\d+)?\s*[万千kK]?|[零〇一二两三四五六七八九十百千万]+)"
CURRENCY = r"(?:人民币\s*)?(?:元|块钱|块|人民币)?"
NON_MONEY_SUFFIX = r"(?!\s*(?:[\d零〇一二两三四五六七八九十百千万个件只台]|GB|TB|G|mAh|Hz|小时|厘米|毫米|cm|mm|英寸|毫升|ml))"


def amount(text):
    value = str(text).replace(" ", "").lower()
    if re.fullmatch(r"[零〇一二两三四五六七八九十百千万]+", value):
        digits = dict(zip("零〇一二两三四五六七八九", (0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9)))
        total = section = digit = 0
        if not any(c in value for c in "十百千万"):
            return str(int("".join(str(digits[c]) for c in value)))
        for c in value:
            if c in digits:
                digit = digits[c]
            elif c == "万":
                total += (section + digit) * 10000
                section = digit = 0
            else:
                section += (digit or 1) * {"十": 10, "百": 100, "千": 1000}[c]
                digit = 0
        return str(total + section + digit)
    scale = (
        10000 if value.endswith("万") else 1000 if value.endswith(("千", "k")) else 1
    )
    return str(Decimal(value.rstrip("万千k")) * scale)


def _understand(text: str, previous=None, baseline=None) -> dict:
    comparing = bool(re.search(r"对比|比较|比一下|比一比|哪个好|哪个更好|有什么区别", text))
    positions = list(dict.fromkeys(int(Decimal(amount(n))) for n in re.findall(r"第([零〇一二两三四五六七八九十\d]+)(?:个|款|台|件|(?=和|与|、|及|第|[，,。？?]|$))",text))) if comparing else []
    front=re.search(r'前([一二两三\d]+)(?:款|个|台)',text) if comparing and not positions else None
    if front:positions=list(range(1,min(int(Decimal(amount(front[1]))),4)+1))
    old = previous or {}
    # A complete new recommendation is not an implicit continuation of an old
    # budget/colour. Explicit follow-ups still retain their shopping constraints.
    fresh = bool(re.search(r"推荐|想买|搜索", text)) and any(
        alias in text for aliases in CATEGORIES.values() for alias in aliases
    ) and not re.search(r"再|更|刚才|上次|继续|同样|改为|改成|换成|追加|不要|排除", text)
    req = deepcopy(old) if not (fresh or re.search(r"重新选|清空条件|重新开始", text)) else {}
    for key, default in {
        "category": None,
        "categoryId": None,
        "keyword": None,
        "budgetMin": None,
        "budgetMax": None,
        "budgetMaxExclusive": False,
        "budgetMinExclusive": False,
        "brands": [],
        "preferredBrands": [],
        "preferredAttributes": {},
        "requireInStock": False,
        "excludeBrands": [],
        "scenes": [],
        "attributes": {},
        "excludeColors": [],
        "preferences": [],
        "cheaperThan": None,
        "batteryAboveHours": None,
        "minBatteryHours": None,
        "requestedCount": 3,
    }.items():
        req.setdefault(key, deepcopy(default))
    # Earlier turns may have misclassified business facts as catalogue attributes.
    # These facts must be queried from Product/Stock, never treated as user SKU specs.
    req["attributes"] = {k: v for k, v in req["attributes"].items()
                         if not re.search(r"库存|价格|售价|预算|现货|stock|price", k, re.I)}
    if re.search(r"真实(?:商品|商业|业务)|不要(?:演示|测试)|排除(?:演示|测试)", text):
        req["requireRealData"] = True
    category_matches = [
        (len(alias), name)
        for name, aliases in CATEGORIES.items()
        for alias in aliases
        for occurrence in re.finditer(re.escape(alias),text)
        if not re.search(r"(?:不要|不买|不考虑|排除)\s*$",text[max(0,occurrence.start()-8):occurrence.start()])
    ]
    category = max(category_matches, default=(0, None))[1]
    if category:
        if req["category"] and req["category"] != category:
            req["attributes"], req["cheaperThan"], req["batteryAboveHours"] = (
                {},
                None,
                None,
            )
        req["category"] = category
        req["categoryId"] = None
        req["keyword"] = category
    count = re.search(NUMBER + r"\s*(?:款|个|件|种|台|副)(?!月|小时)", text)
    if count and not comparing:
        req["requestedCount"] = min(12, max(1, int(Decimal(amount(count[1])))))
    cid = re.search(
        r"(?:品类ID|分类ID|categoryId)\s*[:：=]?\s*([A-Za-z0-9_-]{1,64})",
        text,
        re.IGNORECASE,
    )
    if cid:
        req["categoryId"] = cid[1]
    keyword = re.search(r"(?:关键词|搜索)\s*[:：]?\s*([^，,。\n]{1,40})", text)
    if keyword:
        req["keyword"] = keyword[1].strip()
    if not category and not keyword:
        generic = re.search(
            r"(?:想买|买个|换成|推荐(?:一下)?)\s*([^，,。！？\n]{1,24})", text
        )
        term = re.split(r"预算|不超过|最多", generic[1])[0].strip() if generic else None
        if (
            not term
            and not req["keyword"]
            and re.fullmatch(r"[\u4e00-\u9fffA-Za-z]{2,12}", text)
            and not any(w in text for w in (*COLORS, "预算", "便宜", "续航", "对比"))
        ):
            term = text
        if term and req.get('category') and (term.lower() in {a.lower() for aliases in BRANDS.values() for a in aliases} or (re.search(r'只推荐|只看|只要',text) and re.search(r'现货|库存',text))):term=None
        if term and re.fullmatch(NUMBER+r"\s*(?:款|个|件|台|种)(?:商品)?",term):term=None
        if term:
            req["keyword"], req["category"], req["categoryId"] = term, None, None
    if re.search(r"不限预算|不限制预算|取消预算", text):
        req["budgetMin"] = req["budgetMax"] = req["cheaperThan"] = None
        req["budgetMinExclusive"] = req["budgetMaxExclusive"] = False
    span = re.search(r"(?<![A-Za-z0-9_.-])"+NUMBER + r"\s*" + CURRENCY + r"\s*(?:到|至|[-~～])\s*" + NUMBER + r"(?![\d个件只台])", text)
    if span and re.match(
        r"\s*(?:小时|GB|G|Hz|英寸|mAh|厘米|毫米|cm|mm|毫升|ml|升|L)", text[span.end() :], re.IGNORECASE
    ):
        span = None
    cap = re.search(
        r"(?:预算(?:提高到|降低到|调整到|改到|改成|改为|调整为|是|为)?|不能超过|不超过|最多(?:花)?|上限|控制在|不到)\s*[:：]?\s*(?:人民币)?\s*"
        + NUMBER + NON_MONEY_SUFFIX,
        text,re.I,
    )
    suffix = re.search(NUMBER + r"\s*" + CURRENCY + r"\s*(?:以内|以下)", text)
    floor = re.search(r"(?:至少|不低于|不少于|最低价(?:格)?|下限)\s*" + NUMBER + r"\s*" + CURRENCY + NON_MONEY_SUFFIX, text,re.I)
    # "预算8000元以上" is a lower bound, unlike an unqualified "预算8000元".
    if cap and '预算' in cap[0] and re.match(r"\s*"+CURRENCY+r"\s*(?:以上|及以上|往上|及往上|起步|起)",text[cap.end():]):
        cap=None
    if span:
        req["budgetMin"], req["budgetMax"] = amount(span[1]), amount(span[2])
    elif cap or suffix:
        req["budgetMax"] = amount((cap or suffix)[1])
        req["cheaperThan"] = None
        # "200以内" specifies a new range, not the previous range's lower bound.
        if not floor and not re.search(r"上限|最高价|预算(?:提高到|降低到|调整到|改到)", text):
            req["budgetMin"] = None
    if span or cap or suffix:
        req["budgetMaxExclusive"] = False
    if cap and "不到" in cap[0]:
        req["budgetMaxExclusive"] = True
    strict_upper = re.search(r"(?<!不)(?<!不能)低于\s*" + NUMBER + r"\s*" + CURRENCY + NON_MONEY_SUFFIX, text,re.I)
    if strict_upper:
        req["budgetMax"] = amount(strict_upper[1])
        req["budgetMaxExclusive"] = True
    lower_suffix=re.search(NUMBER+r"\s*"+CURRENCY+r"\s*(?:以上|及以上|往上|及往上|起步|起)(?![\u4e00-\u9fff]*mAh)",text,re.I)
    strict_floor=re.search(r"(?<!不)(?<!不能)(?:高于|超过)\s*"+NUMBER+r"\s*"+CURRENCY+NON_MONEY_SUFFIX,text,re.I)
    if floor or lower_suffix or strict_floor:
        chosen=floor or lower_suffix or strict_floor
        req['budgetMin']=amount(chosen[1]);req['budgetMinExclusive']=bool(strict_floor and not (floor or lower_suffix))
        req['cheaperThan']=None
        if re.search(r'价格(?:提高|调整|改)|预算(?:提高|调整|改)',text) and not (cap or suffix or span):req['budgetMax']=None;req['budgetMaxExclusive']=False
    elif span: req['budgetMinExclusive']=False
    if re.search(r"不限品牌|清空品牌", text):
        req["brands"], req["excludeBrands"], req["preferredBrands"] = [], [], []
    if re.search(r'(?:除了|除开).{1,20}都可以',text):req['brands']=[];req['preferredBrands']=[]
    positive_brands = []
    soft_brands = []
    for brand, aliases in BRANDS.items():
        for alias in aliases:
            if alias.lower() not in text.lower():
                continue
            if re.search(
                r"(?:不要|排除|不考虑|不买|不选|除了|除开|别(?:推荐|选)?)\s*" + re.escape(alias), text, re.IGNORECASE
            ):
                req["excludeBrands"] = list(
                    dict.fromkeys([*req["excludeBrands"], brand])
                )
                req["brands"] = [b for b in req["brands"] if b != brand]
                req["preferredBrands"] = [b for b in req["preferredBrands"] if b != brand]
            elif re.search(r"(?:优先(?:考虑)?|偏好|最好(?:是)?)\s*"+re.escape(alias),text,re.I):
                soft_brands.append(brand)
                req["excludeBrands"] = [b for b in req["excludeBrands"] if b != brand]
            else:
                positive_brands.append(brand)
                req["excludeBrands"] = [b for b in req["excludeBrands"] if b != brand]
    if soft_brands: req["preferredBrands"] = list(dict.fromkeys(soft_brands))
    if positive_brands:
        req["brands"] = list(dict.fromkeys(positive_brands))
        if re.search(r"换成|改成|改为",text):req["preferredBrands"]=[]
    custom = re.search(
        r"(?:品牌偏好|品牌)\s*[:：]\s*([A-Za-z0-9\u4e00-\u9fff-]{1,20})", text
    )
    if custom:
        if custom[0].startswith("品牌偏好"):
            req["preferredBrands"] = [custom[1]]
            req["brands"] = []
        else:
            req["brands"] = [custom[1]]
    for color in COLORS:
        if color in text:
            if re.search(r"(?:不要|排除|不考虑)\s*" + color, text):
                req["excludeColors"] = list(
                    dict.fromkeys([*req["excludeColors"], color])
                )
                if req["attributes"].get("颜色") == color:
                    req["attributes"].pop("颜色")
            elif re.search(r"(?:优先(?:考虑)?|偏好|最好(?:是)?)\s*"+color,text):
                req["preferredAttributes"]["颜色"] = color
                req["attributes"].pop("颜色",None)
            else:
                req["attributes"]["颜色"] = color
                req["excludeColors"] = [c for c in req["excludeColors"] if c != color]
    for key, pattern in {"材质":r"(不锈钢|陶瓷|玻璃|硅胶|纯棉|真皮|塑料|木质)","尺寸":r"(\d+(?:\.\d+)?\s*(?:英寸|厘米|cm|毫米|mm))",
                         "容量":r"(\d+(?:\.\d+)?\s*(?:毫升|ml|升|L))(?![A-Za-z])",
                         "功率":r"(\d+(?:\.\d+)?\s*(?:千瓦|kW|瓦|W))(?![A-Za-z])",
                         "处理器":r"(?:处理器|CPU)\s*[:：]?\s*((?:i[3579]|r[3579])(?:[- ]\d{3,5}[A-Za-z]{0,3})?)",
                         "耳机类型":r"(头戴式|半入耳式|入耳式|骨传导)","连接方式":r"(蓝牙|有线|2\.4G无线)"}.items():
        match=re.search(pattern,text,re.I)
        if re.search(r"(?:不限|取消|不限制)(?:\S{0,3})"+key,text):
            req["attributes"].pop(key,None);req["preferredAttributes"].pop(key,None)
        elif match:
            if re.search(r"(?:优先(?:考虑)?|偏好|最好(?:是)?)\s*"+re.escape(match[1]),text):
                req["preferredAttributes"][key]=match[1];req["attributes"].pop(key,None)
            else: req["attributes"][key]=match[1]
    if re.search(r"不限颜色|取消颜色|颜色不限",text):
        req["attributes"].pop("颜色",None);req["preferredAttributes"].pop("颜色",None);req["excludeColors"]=[]
    if re.search(r"必须有货|只要有货|只要有现货|仅看现货|只看有库存|当前有库存|必须现货|只推荐有现货|只看现货|只要现货",text):req["requireInStock"]=True
    if re.search(r"不限制库存|取消现货|库存不限",text):req["requireInStock"]=False
    ram = re.search(r"(\d+)\s*(?:GB|G)\s*(?:内存|运存)", text, re.IGNORECASE) or re.search(r"(?:内存|运存)\s*[:：]?\s*(\d+)\s*(?:GB|G)",text,re.I)
    if ram:
        req["attributes"]["内存"] = ram[1] + "GB"
    capacity=next((m for m in re.finditer(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(GB|TB|G)(?![A-Za-z])",text,re.I) if not re.match(r"\s*(?:内存|运存)",text[m.end():]) and not re.search(r'(?:内存|运存)\s*[:：]?\s*$',text[max(0,m.start()-8):m.start()])),None)
    if capacity:
        val=capacity[1]+('TB' if capacity[2].upper()=='TB' else 'GB')
        if re.search(r"(?:最好(?:是|有)?|优先(?:考虑)?|偏好)\s*(?:有)?"+re.escape(capacity[0]),text,re.I):
            req['preferredAttributes']['存储容量']=val;req['attributes'].pop('存储容量',None)
        else:req['attributes']['存储容量']=val;req['preferredAttributes'].pop('存储容量',None)
    model=re.search(r"型号\s*[:：]\s*([A-Za-z0-9][A-Za-z0-9 _-]{0,30})",text)
    if model:req['attributes']['型号']=model[1].strip()
    minimum_battery = re.search(
        r"续航(?:至少|不低于|不少于|达到)?\s*(\d+(?:\.\d+)?)\s*小时", text
    )
    if minimum_battery:
        req["minBatteryHours"] = minimum_battery[1]
    for scene in SCENES:
        if scene in text:
            req["scenes"] = list(dict.fromkeys([*req["scenes"], scene]))
    for preference in ("轻便", "轻薄", "安静", "防水", "便宜", "续航", "外观好看", "性价比", "拍照"):
        if preference in text:
            req["preferences"] = list(dict.fromkeys([*req["preferences"], preference]))
    if "库存充足" in text:
        req["preferences"] = list(dict.fromkeys([*req["preferences"], "库存充足"]))
    clarification = None
    approximate=re.search(NUMBER+r"\s*"+CURRENCY+r"\s*(?:左右|上下|附近)",text)
    if approximate:
        req['budgetTarget']=amount(approximate[1]);req['budgetMax']=old.get('budgetMax')
        clarification='已记录目标价约'+req['budgetTarget']+'元，请说明可接受的最低价和最高价；不会自行放宽预算。'
    req['currency']='CNY'
    if re.search(r"美元|欧元|USD|EUR", text, re.IGNORECASE):
        clarification = "目前按商城人民币标价筛选，请提供人民币预算。"
    if re.search(r"预算\s*[:：]?\s*-\d", text):
        clarification = "预算不能为负数，请确认预算。"
    if "更便宜" in text:
        prices = [
            Decimal(p["price"]) for p in baseline or [] if p.get("price") is not None
        ]
        if prices:
            req["cheaperThan"] = str(min(prices))
        else:
            clarification = "上轮没有可核实价格，请给出希望控制的最高预算。"
    if re.search(r"续航更长|更长.*续航", text):
        hours = [
            Decimal(p["batteryHours"])
            for p in baseline or []
            if p.get("batteryHours") is not None
        ]
        if hours:
            req["batteryAboveHours"] = str(max(hours))
        else:
            clarification = (
                "上轮缺少同单位的标称续航数据，无法判断更长；请补充期望续航或具体型号。"
            )
    if (
        req["budgetMin"] is not None
        and req["budgetMax"] is not None
        and Decimal(req["budgetMin"]) > Decimal(req["budgetMax"])
    ):
        clarification = "预算下限高于上限，请确认预算范围。"
    # Generic catalogue requests are constraints, not literal product names.
    # Never relax an explicit category/keyword such as "搜索保温杯".
    broad = not category and not cid and bool(re.search(r"商品|好物|商城", text))
    candidate = str(req.get("keyword") or "")
    broad_term = re.fullmatch(
        r"(?:请|帮我|搜索|当前|本|实际|在售|的|所有|全部|一款|几款|适合|日常|使用|商品|好物|商城|根据|我|需求|推荐|优先|考虑|且|有|库存|充足|元|以内|以下|[\d\s，,。])*",
        candidate,
    )
    if broad and broad_term:
        req["keyword"] = ""
        req["catalogBrowse"] = True
    elif category or cid or keyword:
        req["catalogBrowse"] = False
    if not req["keyword"] and not req["categoryId"] and not req.get("catalogBrowse"):
        clarification = (
            clarification
            or "想选什么商品或品类？也可以直接提供搜索关键词；预算等其他条件可稍后补充。"
        )
    return {
        "requirements": req,
        "clarification": clarification,
        "compare": comparing,
        "comparisonPositions": positions,
    }


def understand(text: str, previous=None, baseline=None) -> dict:
    """Reject malformed or excessive requirements before model/tool invocation."""
    issue=None
    if not isinstance(text,str) or len(text)>2000:
        issue='请输入不超过2000字的购物需求，分开说明品类和预算。';text=''
    text=unicodedata.normalize('NFKC',text)
    if re.search(r'(?:(?:预算|价格|售价|不超过|最多|上限|不高于|最低|不低于)\s*[:：]?\s*-\s*\d|(?:^|[，,\s])-\s*\d+(?:到|至|~)|(?<![\d])-[0-9.]+\s*(?:元|块钱|块)?\s*(?:以内|以下))',text):
        issue='预算不能为负数，请确认预算。'
    if previous is not None:
        if not isinstance(previous,dict):issue='购物条件无法恢复，请重新说明品类与预算。'
        else:
            for key in ('category','categoryId','keyword'):
                if previous.get(key) is not None and not isinstance(previous[key],str):issue='购物条件无法恢复，请重新说明品类与预算。'
            for key in ('requireInStock','budgetMaxExclusive','budgetMinExclusive','catalogBrowse','requireRealData'):
                if key in previous and type(previous[key]) is not bool:issue='购物条件无法恢复，请重新说明品类与预算。'
            if 'requestedCount' in previous and (type(previous['requestedCount']) is not int or not 1<=previous['requestedCount']<=12):issue='购物条件无法恢复，请重新说明品类与预算。'
            for key in ('attributes','preferredAttributes'):
                if key in previous and (not isinstance(previous[key],dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in previous[key].items())):issue='购物条件无法恢复，请重新说明品类与预算。'
            for key in ('brands','excludeBrands','preferredBrands','excludeColors','preferences','scenes'):
                if key in previous and (not isinstance(previous[key],list) or any(not isinstance(v,str) for v in previous[key])):issue='购物条件无法恢复，请重新说明品类与预算。'
            for key in ('budgetMin','budgetMax','cheaperThan','minBatteryHours','batteryAboveHours'):
                value=previous.get(key)
                if value is not None:
                    try:
                        n=Decimal(str(value))
                        if isinstance(value,bool) or not n.is_finite() or n<0:raise ValueError()
                    except (ValueError,ArithmeticError):issue='购物条件无法恢复，请重新说明品类与预算。'
    if baseline is not None:
        if not isinstance(baseline,list) or any(not isinstance(b,dict) for b in baseline):issue='上轮商品数据无法恢复，请重新查询。'
        else:
            for b in baseline:
                for key in ('price','batteryHours'):
                    if b.get(key) is not None:
                        try:
                            n=Decimal(str(b[key]))
                            if isinstance(b[key],bool) or not n.is_finite() or n<0:raise ValueError()
                        except (ValueError,ArithmeticError):issue='上轮商品数据无法恢复，请重新查询。'
    if issue:
        result=_understand('');result.update(clarification=issue,inputRejected=True);return result
    result=_understand(text,previous,baseline)
    old=previous or {}
    result['fieldEvidence']={key:{'source':'CURRENT_TEXT' if value!=old.get(key) else 'VERIFIED_SESSION_CONTEXT','quote':text[:180] if value!=old.get(key) else None,'confidence':'RULE_VALIDATED'} for key,value in result['requirements'].items() if key in {'category','brands','budgetMin','budgetMax','attributes','preferredAttributes','requireInStock','currency'}}
    return result
