package com.simlect.api.support;

import java.util.List;
import java.util.*;
import java.text.Normalizer;
import java.util.regex.Pattern;

/** Deterministic accessory exclusions, applied before pagination/counting. */
public final class ProductQueryIntent {
    private ProductQueryIntent() {}
    public static final Map<String,List<String>> BRANDS=Map.ofEntries(
        Map.entry("苹果",List.of("苹果","apple","iphone")),Map.entry("三星",List.of("三星","samsung","galaxy")),
        Map.entry("华为",List.of("华为","huawei")),Map.entry("小米",List.of("小米","xiaomi","redmi","红米")),
        Map.entry("荣耀",List.of("荣耀","honor")),Map.entry("OPPO",List.of("oppo")),Map.entry("vivo",List.of("vivo")),
        Map.entry("联想",List.of("联想","lenovo")),Map.entry("索尼",List.of("索尼","sony")));
    private static final List<List<String>> CATEGORIES=List.of(
        List.of("手机壳","手机保护壳","phone case","mobile cover"),List.of("笔记本","笔记本电脑","laptop"),
        List.of("耳机","headphone","headset","earphone"),List.of("手机","智能手机","smartphone","iphone","galaxy"),
        List.of("茶杯","茶水杯","teacup"),List.of("保温杯","vacuum cup"),List.of("电脑","computer"),
        List.of("台灯","阅读灯","desk lamp"),List.of("键盘","keyboard"));
    /** AND between concepts, OR between their aliases. Values remain parameterized. */
    public static List<List<String>> groups(String raw){
        String text=Normalizer.normalize(raw==null?"":raw,Normalizer.Form.NFKC).trim().toLowerCase(Locale.ROOT);
        if(text.length()>200)throw new IllegalArgumentException("搜索词过长");
        List<List<String>> groups=new ArrayList<>();
        List<String> brandTerms=new ArrayList<>();
        for(var aliases:BRANDS.values())if(aliases.stream().anyMatch(text::contains))brandTerms.addAll(aliases);
        if(!brandTerms.isEmpty())groups.add(brandTerms.stream().distinct().toList());
        for(var aliases:CATEGORIES)if(aliases.stream().anyMatch(text::contains)){groups.add(aliases);break;}
        String rest=text;
        for(var group:groups)for(var alias:group.stream().sorted(Comparator.comparingInt(String::length).reversed()).toList())rest=rest.replace(alias," ");
        var capacity=Pattern.compile("(?i)(\\d+)\\s*(g|gb|tb)(?![a-z])").matcher(rest);
        while(capacity.find()){String n=capacity.group(1);String unit=capacity.group(2).toLowerCase(Locale.ROOT);groups.add(unit.equals("tb")?List.of(n+"tb"):List.of(n+"g",n+"gb"));}
        rest=rest.replaceAll("(?i)\\d+\\s*(?:gb|g|tb)(?![a-z])"," ");
        for(String token:rest.split("[\\s,，、/;；]+"))if(!token.isBlank())groups.add(List.of(token));
        if(groups.size()>12)throw new IllegalArgumentException("搜索条件过多");
        return groups.stream().distinct().toList();
    }
    public static List<List<String>> sqlGroups(String raw){return groups(raw).stream().map(g->g.stream().map(t->t.replace("!","!!").replace("%","!%").replace("_","!_")).toList()).toList();}
    /** Title prefix is catalogue evidence, never compatibility/description inference. */
    public static Map<String,String> brandEvidence(String title,List<String> values){
        Set<String> found=new HashSet<>();
        for(var e:BRANDS.entrySet())if(values.stream().anyMatch(v->e.getValue().stream().anyMatch(a->a.equalsIgnoreCase(v.trim()))))found.add(e.getKey());
        if(found.size()==1)return Map.of("value",found.iterator().next(),"source","PROPERTY_VALUE");
        if(!values.isEmpty())return Map.of(); // Conflicting explicit data must not be replaced by a title.
        String prefix=(title==null?"":title).replaceFirst("^\\s*\\[[^]]{1,8}]\\s*","").stripLeading().toLowerCase(Locale.ROOT);
        if(prefix.matches(".*(?:适用|适配|兼容|专用|\\bfor\\b|compatible).*"))return Map.of();
        for(var e:BRANDS.entrySet())for(String a:e.getValue()){
            String boundary=a.matches("[a-z]+")?"(?:[^a-z]|$).*":".*";
            if(prefix.matches("^"+Pattern.quote(a)+boundary)){
                if(a.equals("苹果")&&!prefix.matches(".*(?:iphone|ipad|mac|airpods|手机|电脑|平板|耳机).*"))continue;
                found.add(e.getKey());
            }
        }
        return found.size()==1?Map.of("value",found.iterator().next(),"source","PRODUCT_NAME_PREFIX"):Map.of();
    }
    public static List<String> excludedNames(String query) {
        if (query == null) return List.of();
        String normalized=query.toLowerCase(Locale.ROOT);
        // An explicitly requested accessory is a valid result in its own right.
        if (query.matches(".*(壳|套|包|架|贴膜|配件).*") || CATEGORIES.get(0).stream().anyMatch(normalized::contains)) return List.of();
        if (CATEGORIES.get(2).stream().anyMatch(normalized::contains)) return List.of("手机壳", "保护壳", "保护套", "耳机套", "耳机包", "耳机架", "耳机支架", "音箱", "音响");
        if (CATEGORIES.get(3).stream().anyMatch(normalized::contains)) return List.of("手机壳", "保护壳", "保护套", "手机支架", "手机贴膜", "手机配件", "记录仪", "摄像头", "监控", "路由器", "打印机", "投影", "音箱", "充电宝", "电子题库", "视频会员", "背包");
        return List.of();
    }
}

