package com.simlect.controller.aftersales;

import com.simlect.biz.AftersalesCaseService.Actor;
import com.simlect.component.RedisComponent;
import com.simlect.entity.dto.TokenUserInfoDTO;
import com.simlect.entity.enums.ResponseCodeEnum;
import com.simlect.exception.BusinessException;
import com.simlect.utils.AuthCookieHelper;
import jakarta.annotation.Resource;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.stereotype.Component;

@Component
public class CaseAuthentication {
    @Resource private RedisComponent redis;
    @Resource private AuthCookieHelper cookies;
    public Actor user(HttpServletRequest request){
        String token=cookies.resolveWebToken(request);
        TokenUserInfoDTO user=token==null||token.isBlank()?null:redis.getTokenUserInfo(token);
        if(user==null)throw new BusinessException(ResponseCodeEnum.CODE_901);
        return new Actor(user.getUserId(),false);
    }
    public Actor admin(HttpServletRequest request){
        String token=cookies.resolveAdminToken(request);
        Object account=token==null||token.isBlank()?null:redis.getLoginInfo4Admin(token);
        if(!(account instanceof String value)||value.isBlank())throw new BusinessException(ResponseCodeEnum.CODE_901);
        return new Actor((String)account,true);
    }
}
