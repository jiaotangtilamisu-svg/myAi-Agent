"""Offline Chinese merchandising and local-stock setup plan; no paid APIs or DB writes."""
import json,re,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
DESIGNS=dict(zip(
 'Wooden Art|Kitty with Glitter|Head Phone|Kitty|Butterflies|Never be Alone|Floral|Cute Pink Cat|Sea View|Two Number|Horizontal Arrow Texture|Color Mash|Dark Flowers Photography|Panda Texture|Sparkle Coffee|Hanging Flowerpot|Birds|Multicolor Box|Panda Experation|Jar at Sea Serface|Number Ten|Couples Sitting at Dark|Pink Flower Patterns|Sparkle Girl Boss|Desert Plant|Circle Patternn|No Hate On Wooden Block|Wooden Blocks Checks|Woodcutter|Cactus|Foil Paper Texture|Iron Impression|Like On Wooden Block|Toy Car|Blue Oil Color|Wax Color|Girl Boss On Wood|Sky Photography|Take It Easy|Water Drop On Glass|Orange Canvas|Love Print On Cloth Pattern|Police Booth|Skull Flower|Squirrel|Multicolour Texture|Old Time Gate|Water Drop Reflection|Super Girl|Autumn Scene|Patternn|Gold Yellow Paint|Candle Light|Ball Heart|Couple Sitting On Moon|Cute Puppy|Wooden Design|Butterfly Design|Black Pattern Alphabet-J|Button Jeans Alphabet-X|Black Pattern Alphabet-C|Abstract|Steam Train|Gilliter Lollipops|Sleepy Kitten|Butterflies Neon Light|Autumn Girl|Photography|Blue Pattern Alphabet-Z|Pink Sparkle|Stars|Half Fill|Colored Paris|Stone Heart|Boy and Girl|Solar System|White Flower|Alone|Multicolor Cute Love Red Pattern Design|Multicolor Black Pattern Alphabet-V|Monkey with Skart|Babby Kitty'.split('|'),
 '木纹艺术|闪亮猫咪|耳机图案|猫咪|蝴蝶|陪伴文字|花卉|粉色猫咪|海景|数字2|横向箭头|拼色|暗色花卉|熊猫|咖啡图案|悬挂花盆|小鸟|彩色方块|熊猫表情|海边瓶子|数字10|夜色情侣|粉色花卉|闪亮文字|沙漠植物|圆形纹样|木板文字|木纹格子|伐木图案|仙人掌|锡纸纹理|金属纹理|木板点赞|玩具汽车|蓝色油彩|蜡彩图案|木纹文字|天空|轻松文字|玻璃水滴|橙色画布|爱心布纹|警亭|骷髅花卉|松鼠|多彩纹理|复古大门|水滴倒影|女孩图案|秋日风景|纹样|金黄色油彩|烛光|爱心球|月亮情侣|小狗|木纹|蝴蝶|黑色字母J|牛仔字母X|黑色字母C|抽象图案|蒸汽火车|闪亮棒棒糖|瞌睡小猫|霓虹蝴蝶|秋日女孩|摄影图案|蓝色字母Z|闪亮粉色|星星|半满图案|彩色巴黎|石头爱心|男孩女孩|太阳系|白色花卉|独处文字|红色爱心|黑色字母V|猴子|幼猫'.split('|')))
BRANDS={'Samsung':'三星','Xiaomi':'小米','Apple':'苹果','Huawei':'华为','Motorola':'摩托罗拉','Nokia':'诺基亚','Lenovo':'联想','Asus':'华硕','Sony':'索尼','LeTV':'乐视','Mi Redmi':'小米 Redmi'}
COLORS={'Clear':'透明','champagne':'香槟色','Yeşil':'绿色','Others':'其他','Multicolor':'彩色','multi-colored':'彩色','Multicolour':'彩色'}

def chinese(row):
    source=row['productName'];kind=row['kind']
    if kind=='DRINKING_CUP':
        return 'AmazonBasics 玻璃水杯套装（15盎司·6只装）' if '15-Ounce' in source else 'AmazonBasics 玻璃水杯套装（16件装）'
    if kind=='HEADPHONES':
        return 'AmazonBasics 游戏耳机（适用Xbox One、PS4）' if 'Gaming' in source else 'AmazonBasics 头戴式蓝牙耳机（香槟色）'
    match=re.search(r'Designer (.+?) (?:3D Printed|UV Printed|Printed) (?:Hard|Soft) Back',source)
    design=DESIGNS.get(match[1],'印花') if match else '印花'
    model=source.split('Mobile Cover for ',1)[-1]
    model=re.sub(r'\s*\(D\d+\)\s*$','',model)
    for en,cn in BRANDS.items():model=model.replace(en,cn)
    return f'Solimo {design}手机壳（适用{model}）'

def build():
    old=json.loads((ROOT/'Simlect-backend/Simlect-product/app/src/main/resources/catalogue/abo-storefront.json').read_text(encoding='utf8'))
    rows=[]
    for p in old['products']:
        name=chinese(p)
        if len(name)>200 or '手机壳' not in name and p['kind']=='CELLULAR_PHONE_CASE':raise ValueError('INVALID_CHINESE_MERCHANDISING')
        spec=p['specification']
        for en,cn in COLORS.items():spec=spec.replace(en,cn)
        rows.append({'productId':p['productId'],'sourceId':p['sourceId'],'productName':name,
                     'productDesc':name+'\n规格：'+spec+'\n请按设备型号选择对应规格。' if p['kind']=='CELLULAR_PHONE_CASE' else name+'\n规格：'+spec,
                     'specification':spec,'initialStock':100 if p['kind']=='CELLULAR_PHONE_CASE' else 50,
                     'skuHash':p['skuHash'],'price':p['price'],'kind':p['kind']})
    return {'planId':'ABO31_COMMERCE_READY_V1','products':rows,'stockNature':'LOCAL_CONFIGURED_TEST_STOCK','overwriteExistingStock':False}

if __name__=='__main__':
    p=ROOT/'Simlect-backend/Simlect-product/app/src/main/resources/catalogue/abo-commerce-ready.json'
    plan=build()
    proof=json.loads((ROOT/'.cache/stage31/commerce-ready/backup/manifest.json').read_text())
    if hashlib.sha256(Path(proof['file']).read_bytes()).hexdigest()!=proof['sha256']:raise ValueError('BACKUP_REQUIRED')
    plan.update(backupFile=proof['file'],backupSha256=proof['sha256'])
    p.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'products':len(plan['products']),'exampleNames':[x['productName'] for x in plan['products'][:4]]},ensure_ascii=False))
