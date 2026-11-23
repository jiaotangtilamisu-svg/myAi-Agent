package com.simlect.mappers;

import com.simlect.entity.po.SysCategory;
import org.apache.ibatis.annotations.Param;

import java.util.List;

public interface SysCategoryMapper<T,P> extends BaseMapper<T,P> {
    @org.apache.ibatis.annotations.Select({"<script>SELECT category_id AS categoryId,category_name AS categoryName FROM sys_category WHERE category_id IN <foreach collection='ids' item='id' open='(' separator=',' close=')'>#{id}</foreach></script>"})
    List<java.util.Map<String,Object>> selectAgentNames(@Param("ids") List<String> ids);

	 Integer updateByCategoryId(@Param("bean") T t,@Param("categoryId") String categoryId);

	 Integer deleteByCategoryId(@Param("categoryId") String categoryId);

	 T selectByCategoryId(@Param("categoryId") String categoryId);

	List<T> selectByPCategoryId(@Param("pCategoryId") String pCategoryId);

	Integer selectMaxSort(@Param("pCategoryId")String pId);

	void updateBatch(@Param("categoryList")List<SysCategory> categoryList);

	String selectNameByCategoryId(@Param("categoryId") String categoryId);

}
