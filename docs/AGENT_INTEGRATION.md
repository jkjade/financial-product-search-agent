# HyperCLOVA X Agent 연동 가이드 v2.5.1

`GET /tools/catalog`에서 Function Calling 형식의 9개 도구 JSON Schema를 제공합니다.

```text
사용자 질문
→ HyperCLOVA X 의도 해석·도구 선택
→ search / aggregate / rank / compare / detail
→ PostgreSQL 결정론적 실행
→ 원본 근거·개별 기준일·품질 플래그 반환
→ HyperCLOVA X 최종 답변
```

## 핵심 원칙

- HyperCLOVA X 외 다른 LLM은 연결하지 않습니다.
- 모델이 SQL을 직접 생성하지 않고 검증된 도구 스키마만 호출합니다.
- 도구 인수의 알 수 없는 필드는 `extra=forbid`로 거부합니다.
- 도구 오류는 모델에 구조화된 오류로 돌려주어 한정된 횟수 내에서 수정 호출할 수 있습니다.
- `think_trace`는 내부 사고과정이 아니라 사용 도구·상태·반환 건수의 실행 요약입니다.

실행 순서는 `PHASE3_HANDOFF.md`를 따릅니다.
