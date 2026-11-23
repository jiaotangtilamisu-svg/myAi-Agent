"""Conservative routing. Composite means independently identifiable clauses, not every turn."""

import re
import unicodedata

from app.shopping.requirements import CATEGORIES, BRANDS
from app.supervisor.contracts import Task


def signals(text):
    if not isinstance(text,str) or len(text)>2000:return False,False
    text=re.sub(r'(?:不要|不用|别|无需|不需要)\s*(?:再|帮我|给我)?\s*(?:推荐|搜索|比较|选购)[^，,。；;]*(?=[，,。；;]|$)','',text)
    from app.domain.aftersales_intent import classify
    business_intent=classify(text)
    after = bool(business_intent) or bool(
        re.search(
            r"售后|退款|退货|能退|可退|能换|换货|保修|维修|订单|物流|快递|包裹|未发货|没发货|扣款|支付异常|质量(?:问题|异常|不好|差)|破损|坏了|瑕疵",
            text,
        )
    )
    buying = bool(
        re.search(
            r"推荐|想买|选[个款台]|导购|预算|对比|比较|比一下|比一比|哪个好|哪个更好|有什么区别|更便宜|续航更长|想要.*色|不要.*品牌|搜索|最好|优先|换成|改成|还是选择|只要有现货|再推荐",
            text,
        )
    )
    if not after and "购买" in text:
        buying = True
    if (
        after
        and re.search(r"推荐.*(?:方案|政策|处理)|推荐售后", text)
        and not any(a in text for aliases in CATEGORIES.values() for a in aliases)
        and not re.search(r"预算|购买|想买|商品比较", text)
    ):
        buying = False
    if not after and (
        any(a in text for aliases in CATEGORIES.values() for a in aliases)
        or any(a.lower() in text.lower() for aliases in BRANDS.values() for a in aliases)
        or re.search(r"白色|黑色|不[要考虑].*(?:华为|小米|苹果|联想)", text)
    ):
        buying = True
    return after, buying


def plan(text, last_route=None):
    if not isinstance(text,str) or len(text)>500 or not text.strip():
        return {"tasks":[],"reason":"INVALID_INPUT","question":"请分开说明具体问题，每条任务不超过500字。"}
    text=unicodedata.normalize('NFKC',text)
    if re.search(r"退的钱|退款金额|退款后|到账后|同价位|审批通过后", text):
        return {
            "tasks": [],
            "reason": "DEPENDENT_TASK",
            "question": "请分别说明需要核实的售后问题和购物预算；不能把尚未确认的退款或审批结果作为购物条件。",
        }
    after, buying = signals(text)
    if after and buying:
        clauses = [
            s.strip(" ，,。；;")
            for s in re.split(
                r"另外|同时|顺便|然后|以及|并且|还想|再帮我|并帮我|并(?=推荐|查询|查看|申请)|[；;，,]|和(?=推荐|查询|搜索|比较)", text
            )
            if s.strip(" ，,。；;")
        ]
        grouped = {"aftersales": [], "shopping": []}
        for clause in clauses:
            a, s = signals(clause)
            if a == s:
                return {
                    "tasks": [],
                    "reason": "AMBIGUOUS_COMPOSITE",
                    "question": "请把售后问题与选购要求分开说明，我会分别查询后统一整理。",
                }
            grouped["aftersales" if a else "shopping"].append(clause)
        if all(grouped.values()):
            return {
                "tasks": [
                    Task(agent=k, text="；".join(v)).model_dump()
                    for k, v in grouped.items()
                ],
                "reason": "COMPOSITE",
                "question": None,
            }
        return {
            "tasks": [],
            "reason": "AMBIGUOUS_COMPOSITE",
            "question": "这次主要想处理售后还是选购商品？也可以分别列出两项要求。",
        }
    if after or buying:
        return {
            "tasks": [
                Task(
                    agent="aftersales" if after else "shopping", text=text
                ).model_dump()
            ],
            "reason": "EXPLICIT",
            "question": None,
        }
    if re.fullmatch(
        r"(?:继续|再试试|接着说|然后呢|还有吗|刚才那个呢)[？?。！!]*", text.strip()
    ) and last_route in {"aftersales", "shopping"}:
        return {
            "tasks": [Task(agent=last_route, text=text).model_dump()],
            "reason": "CONTEXT_FOLLOWUP",
            "question": None,
        }
    return {
        "tasks": [],
        "reason": "UNCLEAR",
        "question": "你想查询售后/订单问题，还是搜索、比较和选购商品？请补充具体需求。",
    }
