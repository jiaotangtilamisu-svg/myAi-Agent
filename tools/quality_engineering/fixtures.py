"""Small raw Java-wire-shaped fixtures. No Agent helpers produce these facts."""
def product(pid='P1',price=1200,count=5,color='白色',brand='华为',category='手机',battery='20小时'):
 return {'product_id':pid,'product_name':brand+category+pid,'status':1,'product_status':'ON_SALE','query_status':'SUCCESS','min_price':price,'max_price':price,'sku_complete':True,'category_id':'C1','category_name':category,'parent_category_name':'数码','product_observed_at':'2026-11-05T00:00:00Z',
 'property_values':[{'property_name':'品牌','property_value':brand},{'property_name':'续航','property_value':battery},{'property_name':'适用场景','property_value':'办公'}],
 'skus':[{'sku_id':pid+'_1','sku_name':color,'price':price,'stock':count,'stock_query_status':'SUCCESS','specifications':[{'name':'颜色','value':color}]}]}
