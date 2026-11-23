package com.simlect.component;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.simlect.api.support.ProductQueryIntent;
import java.util.*;

/** Shared-concept lexical recall. No query-string interpolation or paid embedding. */
public final class ProductLexicalQuery {
    private ProductLexicalQuery(){}
    private static final ObjectMapper JSON=new ObjectMapper();
    public static String json(String text){
        List<Object> must=new ArrayList<>(),not=new ArrayList<>();
        for(var group:ProductQueryIntent.groups(text)){
            List<Object> alternatives=new ArrayList<>();
            for(String term:group){
                alternatives.add(Map.of("multi_match",Map.of("query",term,"fields",List.of("productName^5","brand^8","categoryName^3","searchText^2","productDesc"),"operator","and")));
                String escaped=term.replace("\\","\\\\").replace("*","\\*").replace("?","\\?");
                alternatives.add(Map.of("wildcard",Map.of("productName.keyword",Map.of("value","*"+escaped+"*","case_insensitive",true,"boost",2))));
            }
            must.add(Map.of("bool",Map.of("should",alternatives,"minimum_should_match",1)));
        }
        for(String name:ProductQueryIntent.excludedNames(text))not.add(Map.of("wildcard",Map.of("productName.keyword",Map.of("value","*"+name+"*"))));
        Map<String,Object> bool=new LinkedHashMap<>();bool.put("must",must);bool.put("must_not",not);
        if(text!=null&&!text.isBlank())bool.put("should",List.of(Map.of("match_phrase",Map.of("productName",Map.of("query",text,"boost",10)))));
        try{return JSON.writeValueAsString(Map.of("bool",bool));}catch(JsonProcessingException e){throw new IllegalStateException(e);}
    }
}
