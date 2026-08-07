# 중간 처리 파일

최종 파이프라인은 상품군별 격리 Worker가 정제한 행을 PostgreSQL `COPY`로 직접 스트리밍합니다.
따라서 대용량 중간 CSV를 이 폴더에 저장하지 않습니다.

전처리 품질 보고서와 실행 manifest는 `data/reports/`에 생성됩니다.
