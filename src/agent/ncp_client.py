"""NAVER Cloud Platform CLOVA Studio API 공용 헬퍼.

HCX(function-calling)와 임베딩 클라이언트가 같은 API 키(HCX_API_KEY)와 같은 형태의
요청 헤더를 쓰기 때문에, 두 클라이언트에 각자 복붙돼 있던 부분을 여기로 모았다.
"""

from __future__ import annotations

import os
import uuid


def ncp_api_key_from_env() -> str | None:
    """HCX_API_KEY를 읽는다. 비어 있으면 None (두 클라이언트 모두 같은 키를 씀)."""
    api_key = os.getenv("HCX_API_KEY", "").strip()
    return api_key or None


def ncp_headers(api_key: str) -> dict[str, str]:
    """CLOVA Studio 요청에 공통으로 필요한 헤더."""
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-NCP-CLOVASTUDIO-REQUEST-ID": str(uuid.uuid4()),
    }
