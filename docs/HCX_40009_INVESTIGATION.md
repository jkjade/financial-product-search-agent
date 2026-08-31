# HCX `40009 Unsupported function` 원인 분석 (2026-08-28)

## 요약

`{"error":{"message":"Unsupported function","code":"40009"}}` 는 우리 쪽 요청 스키마
문제(중첩 `$defs`/`$ref`, `anyOf`, enum 크기 등)가 아니라 **HyperCLOVA X(CLOVA Studio)
백엔드 쪽에서, 멀티라운드 tool-calling 대화 이력에 특정 짧은 문자열 값이 다시
전송(replay)될 때 그 요청을 확정적으로 거부하는 버그/특이 동작**으로 재현됐다.
그중 가장 확실하게 재현된 값이 바로 우리 `route_query` 도구가 정상 설계상
**아주 자주 반환하는 값인 `"ALL"`** 이다. 그래서 "너무 자주 발생한다"는 체감이
정확하다 — 애매하거나 여러 상품군을 동시에 다루는 질문(비교/집계/포괄 질문)마다
`route_query`가 `product_types: ["ALL"]`을 반환하고, 그 결과가 다음 라운드
요청의 대화 이력(assistant tool_calls + tool 응답)에 그대로 실려 나가는 순간
높은 확률로 40009가 뜬다.

부가적으로, 현재 재시도 로직은 이 실패에 대해 **아무 도움이 안 된다** — 8번
재시도가 전부 동일한 페이로드를 그대로 다시 보내는데, 이 실패는 네트워크
일시 장애가 아니라 페이로드 내용에 결정적으로 종속되기 때문에 8번 다 똑같이
실패하고 사용자는 그냥 30~45초를 헛되이 기다리게 된다.

## 조사 방법

1. 코드 리뷰: `src/agent/hcx_client.py`, `src/agent/tool_registry.py`,
   `src/api/models.py` 의 도구 스키마 생성/재시도 로직 확인.
2. 실제로 HCX에 전송되는 tool 카탈로그를 로컬에서 그대로 생성해 구조 분석
   (pydantic `model_json_schema()` 결과에 `$defs`/`$ref`/`anyOf`/`format` 존재 확인).
3. **실 엔드포인트에 대해 통제된 재현 테스트 다수 실행** (`.env`의 실 API 키 사용).
   같은 페이로드를 반복 전송, 필드를 하나씩 바꿔가며 결과를 비교하는 방식으로
   원인 변수를 격리했다.
4. CLOVA Studio 공식 문서(`clovastudio-chatcompletionsv3-fc`, `clovastudio-troubleshoot-c4xx`)
   확인.

## 배제된 가설

- **도구 스키마가 복잡해서(= `$defs`/`$ref`/`anyOf`/`format: date`) 실패한다** → 배제.
  실제 카탈로그에 이 구조가 전부 존재하지만, 동일한 스키마를 1라운드(대화 이력 없음)로
  보내면 항상 200이 온다. 또한 4개 필드-스코프 도구(search_products 등)의 enum
  스키마를 서로 다른 두 페이로드 사이에서 맞바꿔봐도(작은 12필드 ↔ 큰 56필드)
  성공/실패 여부가 전혀 안 바뀌었다 — 스키마 내용은 원인이 아니다.
- **enum 라벨 중복(`dur`/`fn_effective_duration`이 둘 다 "듀레이션")** → 실사용 경로에서는
  발생 안 함. `fields_for_domains()`가 실제 도메인별 컬럼 목록으로 필드를 좁히기
  때문에, 이 두 필드가 같은 도메인에 동시에 노출되는 경우가 없었다
  (`DOMESTIC_BOND`엔 `dur`만, `DOMESTIC_ETF`엔 `fn_effective_duration`만 존재).
  코드 품질상 잠재 위험은 맞지만 이 40009와는 무관.
- **`thinking`/추론 파라미터 충돌** → 공식 문서상 "function calling은 reasoning과
  동시 사용 불가"라는 문구가 있지만, 우리 요청은애초에 `thinking` 필드를 아예
  안 보낸다(옵션, 기본값 비활성으로 추정). 재현 테스트에서 이 필드 유무가
  결과에 영향을 준 적이 없었다.
- **순수 네트워크/부하 일시 장애(진짜 "transient")** → 배제까지는 아니지만 부차적.
  같은 페이로드를 새 요청으로 반복 전송했을 때 도메인이 하나로 좁혀진 정상
  케이스(`DOMESTIC_BOND` 단일값)도 100%는 아니고 약 80~90% 성공률을 보였다
  (이건 진짜 HCX 쪽 일반적인 잡음으로 보임). 하지만 `"ALL"` 케이스는 이 배경
  잡음과 별개로 **반복 실험에서 지속적으로 훨씬 높은 실패율**을 보였다(아래 재현 참고).

## 확정된 재현 (핵심 증거)

동일한 시간대에 두 페이로드를 **번갈아** 실 엔드포인트로 보내 배경 변동(부하,
캐시 상태 등)을 통제했다. 유일한 차이는 이전 라운드 assistant `tool_calls` /
`tool` 메시지에 들어있는 `route_query` 결과값 하나뿐:

```
messages[2] (assistant.tool_calls[0].function.arguments)
messages[3] (tool.content)
= {"product_types": ["ALL"]}          ← A
= {"product_types": ["DOMESTIC_BOND"]} ← B
```

시스템 프롬프트, user 메시지, 10개 도구 스키마(바이트 단위로 동일)는 전부 같다.

```
round0_ALL: 400   round0_ok: 200
round1_ALL: 400   round1_ok: 200
round2_ALL: 400   round2_ok: 200
round3_ALL: 400   round3_ok: 200
```
(같은 실험을 시간 간격을 두고 재실행해도 동일하게 재현: ALL 5/5 실패, B 4/4 성공 — 1건은 429였음.)

즉 `product_types: ["ALL"]`이 대화 이력에 실리기만 하면, 그 다음 라운드 요청은
스키마·시스템 프롬프트·질문 내용과 무관하게 거의 항상 `40009`가 난다.

### 실제 운영 코드로 재현

앱의 `HCXAgentClient.answer()`를 가짜 tool executor로 그대로 돌려서 실제 흐름에서도
재현했다:

```
질문: "국내ETF랑 해외ETF 수익률(1년) 비교해서 어느쪽이 평균적으로 더 높은지 그룹별로 집계해줘"
1라운드: route_query({"product_types": ["DOMESTIC_ETF","OVERSEAS_ETF"]}) → 200
2라운드: (10개 도구 그대로 재노출) → 400 40009, 8번 재시도 전부 400
```
`route_query`가 두 값 이상을 반환해 `resolved_domain()`이 `None`을 반환하는
경우도 실패율이 높았다(다만 정확히 `"ALL"` 단일값일 때가 가장 깔끔하게 100%에
가깝게 재현됨).

### 왜 "ALL"인가 — 정확한 규칙은 못 찾음

`"ALL"`, `""`(빈 문자열), `"all"`, `"AL"`, `"ALLX"`, `"XALL"`, `"CALL"`, `"ALLA"`는
반복 실험에서 실패했고, `"PUBLIC_FUND"`, `"NONE"`, `"XYZ_NOT_REAL"`, `"SMALL"`,
`"NULL"`, `"TRUE"`, `"FALSE"`, 정상 operator/sort 값들(`eq`/`gt`/`asc`/...)은
성공했다. 부분 문자열("ALL"을 포함하는 "SMALL"은 성공, "CALL"은 실패)이나 길이,
대소문자만으로는 깔끔하게 설명되지 않는 패턴이라, **HCX 백엔드의 캐시/토큰화
레이어에서 발생하는 것으로 추정되는 벤더 사이드 버그**로 결론짓는다. 우리
쪽에서 이 규칙을 100% 예측해서 막을 수는 없고, 확실히 확인된 고위험 값은
`"ALL"`과 빈 문자열이다.

## 이게 왜 "너무 자주" 나는가

`route_query`의 `product_types` enum 1번째 값이 `"ALL"`이고, 시스템 프롬프트/도구
설명에 "도메인이 불명확하면 ALL을 쓰세요"라고 명시돼 있다(`src/api/models.py`의
`RouteQueryRequest`, `RouteProductType` 참고). 즉:

- 여러 상품군을 비교/합산하는 질문
- 도메인이 모호한 포괄적 질문
- 그냥 "상품", "금융상품" 같은 일반 질의

이런 아주 흔한 질문 패턴마다 모델이 정상적으로 `"ALL"`을 선택하고, 그 값이
다음 라운드 대화 이력에 그대로 replay되면서 40009를 유발한다. 버그 자체는
드문 확률이 아니라 **우리 도구 설계가 의도적으로 자주 만들어내는 값**과
정확히 겹쳐서 체감 빈도가 높은 것.

## 부수적으로 발견한 문제 (원인은 아니지만 상황을 악화시킴)

`src/agent/hcx_client.py:88` — `_request()`가 재시도 루프 **밖에서** 헤더(및
`X-NCP-CLOVASTUDIO-REQUEST-ID`)를 한 번만 만들고, 8번의 재시도 전부 같은
요청 ID를 재사용한다:

```python
def _request(self, messages, tools):
    ...
    headers = ncp_headers(self.settings.api_key)   # UUID 한 번만 생성
    for attempt in range(attempts):
        with httpx.Client(timeout=...) as client:
            response = client.post(..., headers=headers, ...)  # 매 시도 동일 헤더
```

이번 40009는 요청 ID를 새로 발급해도(직접 재현 테스트에서는 매번 새 UUID를
썼음) 여전히 재현되므로 이 자체가 40009의 원인은 아니다. 다만 (a) 일반적인
모범 사례에 어긋나고 (b) 만약 NCP 쪽에 요청 ID 기반 캐싱/dedup이 조금이라도
관여한다면 재시도가 "새 시도"로 인식되지 않을 가능성을 열어두므로 고쳐두는
편이 안전하다.

## 권장 대응 (구현 여부는 확인 후 진행)

1. **(무해, 바로 적용 가능)** 재시도마다 `ncp_headers()`를 새로 호출해 요청 ID를
   매 attempt마다 새로 발급.
2. **(효과 큼)** 40009가 뜨면 무조건 동일 페이로드로 8번 재시도하는 대신,
   실패 원인이 직전 라운드에서 echo된 `route_query` 결과값(특히 `"ALL"`)에
   있다고 의심되면 그 값을 대화 이력에 다른 표기로 저장해 재시도 — 예를 들어
   `messages`에 실제로 쓰이는 문자열만 `"ALL"` → `"ALL_TYPES"` 같은 내부 전용
   표기로 바꿔서 저장하고(모델이 다시 그 값을 참조할 필요는 없음 — `route_query`는
   대화당 한 번만 호출하도록 시스템 프롬프트가 이미 강제), 우리 쪽 `resolved_domain()`
   / `ensure_domain_filter()` 로직은 원래 dict(직렬화 전 값)로 그대로 판단하게 유지.
   즉 "모델이 실제로 뱉은 원본 arguments"는 실행/판단에 쓰고, "대화 이력에
   되돌려 보내는 문자열"만 안전한 표기로 치환.
3. **(운영 완화)** 40009를 받으면 8번 동일 재시도 대신 1~2회만 짧게 재시도하고
   바로 실패 처리 — 어차피 컨텐츠 결정적 실패는 재시도로 해결 안 되므로, 사용자
   대기시간만 줄여준다. 일반적인 배경 잡음성 실패(20% 내외)는 1~2회 재시도로도
   충분히 커버됨.
4. **(근본 대응)** 재현 페이로드(위 "확정된 재현" 절)를 그대로 NCP/CLOVA Studio
   기술지원에 제출 — 바이트 단위로 동일한 두 요청 중 값 하나만 다른데 한쪽만
   100%에 가깝게 실패하는 깔끔한 재현 케이스라 벤더 쪽에서 조사하기 좋다.

어느 것부터 반영할지, 혹은 2번(치환 방식)까지 지금 바로 구현할지 알려주면
이어서 진행하겠습니다.

## 후기 (2026-08-29)

위 권장 대응 2번(문자열 치환)이 아니라 더 근본적인 방향으로 처리했다: `route_query`
자체에서 `"ALL"` sentinel을 완전히 제거하고, 항상 1~4개의 구체 도메인 리스트를
반환하도록 스키마와 시스템 프롬프트를 바꿨다(`src/api/models.py`의
`RouteProductType`/`RouteQueryRequest`). 도메인이 여러 개(2~4개) 선택됐을 때
필드를 어떻게 노출할지의 기준도 다시 정의했다 — canonical 필드 기준으로 "같은
개념"이라고 우리가 판단해서 묶는 대신, **컬럼 코멘트(라벨) 문자열이 완전히
일치하는지**만으로 도메인 간 필드 호환성을 판단한다(`shared_label_map`,
`src/query/field_domains.py`). 이 변경에 맞춰 `src/services/query_engine.py`의
SQL 실행 계층도 임의의 도메인 서브셋을 `UNION ALL`로 묶어 조회할 수 있게 확장했다
(`resolve_catalog_source`/`cross_domain_union_sql_for`).

이로써 이 문서의 확정 재현 케이스(`product_types: ["ALL"]`가 대화 이력에 실리는
경우)는 구조적으로 더 이상 발생하지 않는다. `route_query`의 tool_call 자체가
메인 대화 이력에 남아있는 한 남는 잔여 리스크(2개 이상 도메인 결과도 실패율이
다소 높았다는 관찰)는 별도 후속 작업(`route_query`를 메인 히스토리에서 완전
분리)으로 다루기로 했다.
