"""WeCom OAuth provider implementation (企业内部应用网页授权)."""

import logging
from urllib.parse import parse_qs, urlparse

import httpx

from app.core.config import settings
from app.utils.oauth_providers.base import OAuthProvider, OAuthUserInfo

logger = logging.getLogger(__name__)

WECOM_GET_TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
WECOM_GET_USERINFO_URL = "https://qyapi.weixin.qq.com/cgi-bin/user/getuserinfo"
WECOM_GET_USER_URL = "https://qyapi.weixin.qq.com/cgi-bin/user/get"


class WecomProvider(OAuthProvider):

    @property
    def name(self) -> str:
        return "wecom"

    def _resolve_credentials(
        self, redirect_uri: str | None = None, client_id: str | None = None,
    ) -> tuple[str, str, str, str]:
        corp_id = settings.WECOM_CORP_ID
        app_secret = settings.WECOM_APP_SECRET
        actual_redirect_uri = redirect_uri or settings.WECOM_REDIRECT_URI
        agent_id = settings.WECOM_AGENT_ID

        if client_id and client_id != agent_id:
            logger.warning("企业微信 client_id(AgentId) 不匹配配置: %s", client_id)

        if not corp_id or not app_secret or not actual_redirect_uri or not agent_id:
            raise ValueError("企业微信 OAuth 配置不完整，请检查 WECOM_* 环境变量")

        parsed = urlparse(actual_redirect_uri)
        q = parse_qs(parsed.query)
        redirect_corp_id = (q.get("corp_id") or [""])[0]
        if redirect_corp_id and redirect_corp_id != corp_id:
            logger.warning(
                "redirect_uri 中 corp_id(%s) 与配置(%s)不一致，将使用配置中的 corp_id",
                redirect_corp_id,
                corp_id,
            )
        return corp_id, app_secret, actual_redirect_uri, agent_id

    async def _get_access_token(self, corp_id: str, app_secret: str) -> str:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                WECOM_GET_TOKEN_URL,
                params={"corpid": corp_id, "corpsecret": app_secret},
            )
            data = resp.json()
            if data.get("errcode") != 0:
                raise ValueError(f"企业微信获取 access_token 失败: {data}")
            access_token = data.get("access_token") or ""
            if not access_token:
                raise ValueError(f"企业微信 access_token 为空: {data}")
            return access_token

    async def exchange_code(
        self, code: str, redirect_uri: str | None = None, client_id: str | None = None
    ) -> OAuthUserInfo:
        corp_id, app_secret, _actual_redirect_uri, _agent_id = self._resolve_credentials(redirect_uri, client_id)
        access_token = await self._get_access_token(corp_id, app_secret)

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                WECOM_GET_USERINFO_URL,
                params={"access_token": access_token, "code": code},
            )
            user_info = resp.json()
            if user_info.get("errcode") != 0:
                raise ValueError(f"企业微信 code 换用户失败: {user_info}")

            user_id = user_info.get("UserId") or ""
            if not user_id:
                raise ValueError(f"企业微信未返回 UserId: {user_info}")

            detail_resp = await client.get(
                WECOM_GET_USER_URL,
                params={"access_token": access_token, "userid": user_id},
            )
            detail = detail_resp.json()
            if detail.get("errcode") != 0:
                raise ValueError(f"企业微信获取用户详情失败: {detail}")

            return OAuthUserInfo(
                provider="wecom",
                provider_user_id=user_id,
                provider_tenant_id=corp_id,
                name=detail.get("name") or user_id,
                email=detail.get("email") or None,
                avatar_url=detail.get("avatar") or None,
            )
