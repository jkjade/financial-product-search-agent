"""1회성 온톨로지 재구조화 스크립트 (2026-09 시점: field_labels.py 제거를 위한 마이그레이션).

목적: TTL을 필드 라벨/코멘트의 유일한 소스로 만들기 위해,
  1) 여러 도메인에서 같은 canonical 슬러그(fp:column)를 재사용하면서 서로 다른
     rdfs:comment를 갖던 필드들을 "컬럼 코멘트가 완전히 같은 경우에만 같은 필드"
     원칙에 따라 도메인별 subject로 쪼갠다 (컬럼 코멘트가 정말 같으면 common.ttl에
     하나만 남긴다).
  2) 사람이 손으로 만든 fp:alias(동의어)를 전부 지우고, 원본 raw 엑셀 컬럼 코드
     (field_labels.py의 RAW_COLUMNS, 즉 데이터에 실제로 존재하는 컬럼명)만
     fp:alias로 남긴다.
  3) ranking_semantics(사람이 판단한 "보수가 낮은"→fee_rate asc 류 매핑)를 삭제한다.
  4) field_labels.py가 199개 필드 전부를 커버하는데 TTL은 130개만 커버하던 격차를
     메운다 — 이때 field_labels.py 텍스트를 맹신하지 않고, 가능하면 원본
     data/raw/*_schema.xlsx의 진짜 컬럼코멘트를 우선한다(세션 중 size_amount가
     field_labels.py에서 4도메인에 동일한 문구로 뭉개져 있던 게 원본과 다르다는 걸
     실측으로 확인했기 때문).

이 스크립트는 1회 실행 후 폐기한다 — 재실행 금지. 실행 후 ontology/*.ttl 5개는
사람이 직접 손으로 유지한다(이전 scripts/generate_ontology.py와 같은 성격).

실행 완료(2026-09) 후 src/query/field_labels.py 자체를 삭제했으므로, 이 스크립트는
이제 import 단계에서부터 실패한다 — generate_ontology.py가 term_map.json 삭제 후
그런 것처럼, 이 파일도 "TTL이 처음에 이런 절차로 재구조화됐다"는 기록용으로만
남겨둔다. 새 필드/코멘트를 추가할 때는 이 스크립트가 아니라 ontology/*.ttl을
직접 편집한다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import openpyxl
from rdflib import OWL, RDF, RDFS, Graph, Namespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.query.fields import FIELD_SPECS  # noqa: E402
from src.query.field_domains import classify_field_domains  # noqa: E402
from src.query.field_labels import FIELD_LABELS, RAW_COLUMNS, label_for_field  # noqa: E402

FP = Namespace("https://example.org/financial-product-agent/ontology#")
ONTOLOGY_DIR = PROJECT_ROOT / "ontology"

DOMAIN_FILES = {
    "DOMESTIC_BOND": "bond_kr.ttl",
    "DOMESTIC_ETF": "etf_kr.ttl",
    "OVERSEAS_ETF": "etf_gl.ttl",
    "PUBLIC_FUND": "fund_pub.ttl",
}
DOMAIN_CLASS = {
    "DOMESTIC_BOND": "fp:Bond",
    "DOMESTIC_ETF": "fp:DomesticETF",
    "OVERSEAS_ETF": "fp:OverseasETF",
    "PUBLIC_FUND": "fp:PublicFund",
}
DOMAIN_SUFFIX = {
    "DOMESTIC_BOND": "DomesticBond",
    "DOMESTIC_ETF": "DomesticEtf",
    "OVERSEAS_ETF": "OverseasEtf",
    "PUBLIC_FUND": "PublicFund",
}
KIND_TO_XSD = {
    "text": "xsd:string",
    "numeric": "xsd:decimal",
    "date": "xsd:date",
    "boolean": "xsd:boolean",
}

SCHEMA_XLSX = {
    "DOMESTIC_BOND": "data/raw/prbd01n001_schema.xlsx",
    "DOMESTIC_ETF": "data/raw/pref01n001_schema.xlsx",
    "OVERSEAS_ETF": "data/raw/pref02n001_schema.xlsx",
    "PUBLIC_FUND": "data/raw/prfd01n001_schema.xlsx",
}


def snake_to_camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


# ---------------------------------------------------------------------------
# 1. 원본 schema.xlsx 읽기 (도메인별 {raw_컬럼명: 컬럼코멘트})
# ---------------------------------------------------------------------------


def load_schema_comments() -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for domain, rel_path in SCHEMA_XLSX.items():
        wb = openpyxl.load_workbook(PROJECT_ROOT / rel_path, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
        header = rows[0]
        col_idx = header.index("컬럼명")
        comment_idx = header.index("컬럼코멘트")
        d: dict[str, str] = {}
        for r in rows[1:]:
            if r is None or r[col_idx] is None:
                continue
            colname = str(r[col_idx]).strip()
            comment = str(r[comment_idx]).strip() if r[comment_idx] is not None else ""
            if comment:
                d[colname] = comment
        result[domain] = d
    return result


# ---------------------------------------------------------------------------
# 2. 기존 TTL 5개 파일을 "각각 독립적으로" 파싱해서 파일별 원본 comment/label 복구
#    (load_ontology_graph()처럼 합쳐서 읽으면 이미 늦음 — set 병합으로 뭉개짐)
# ---------------------------------------------------------------------------


def load_existing_declarations() -> dict[str, dict[str, dict]]:
    """반환: {파일이름: {canonical_column: {"subject": str, "comment": str|None,
    "label": str|None, "range": str|None}}}"""
    result: dict[str, dict[str, dict]] = {}
    for domain, filename in DOMAIN_FILES.items():
        g = Graph()
        g.parse(ONTOLOGY_DIR / filename, format="turtle")
        by_column: dict[str, dict] = {}
        for prop in g.subjects(RDF.type, OWL.DatatypeProperty):
            column = g.value(prop, FP.column)
            if column is None:
                continue
            comment = g.value(prop, RDFS.comment)
            label = g.value(prop, RDFS.label)
            range_ = g.value(prop, RDFS.range)
            local = str(prop).rsplit("#", 1)[-1]
            by_column[str(column)] = {
                "subject": local,
                "comment": str(comment) if comment else None,
                "label": str(label) if label else None,
                "label_lang": label.language if label is not None else None,
                "range": str(range_).rsplit("#", 1)[-1] if range_ else None,
            }
        result[filename] = by_column
    # common.ttl도 같은 방식으로 (도메인 파일은 아니지만 공용 필드가 여기 있음)
    g = Graph()
    g.parse(ONTOLOGY_DIR / "common.ttl", format="turtle")
    by_column = {}
    for prop in g.subjects(RDF.type, OWL.DatatypeProperty):
        column = g.value(prop, FP.column)
        if column is None:
            continue
        comment = g.value(prop, RDFS.comment)
        label = g.value(prop, RDFS.label)
        range_ = g.value(prop, RDFS.range)
        local = str(prop).rsplit("#", 1)[-1]
        by_column[str(column)] = {
            "subject": local,
            "comment": str(comment) if comment else None,
            "label": str(label) if label else None,
            "label_lang": label.language if label is not None else None,
            "range": str(range_).rsplit("#", 1)[-1] if range_ else None,
        }
    result["common.ttl"] = by_column
    return result


# ---------------------------------------------------------------------------
# 3. 필드별 진짜 컬럼코멘트 결정 (우선순위: RAW_COLUMNS 매핑된 raw 컬럼의 원본
#    schema.xlsx 코멘트 > canonical 이름 그대로 schema.xlsx에서 조회 > 원본에 없으면
#    field_labels.py 텍스트로 폴백)
# ---------------------------------------------------------------------------


def raw_columns_for(field: str, domain: str) -> list[str]:
    """RAW_COLUMNS에 등록된 이 필드/도메인의 실제 raw 컬럼명들(파이프 구분 전부)."""
    raw = RAW_COLUMNS.get(field, {}).get(domain)
    if raw:
        return raw.split("|")
    return [field]


def true_comment(field: str, domain: str, schema_comments: dict[str, dict[str, str]], report: dict) -> tuple[str, str]:
    """반환: (comment, source) — source는 'schema_raw_columns' | 'schema_canonical_name' | 'field_labels_fallback'"""
    candidates = raw_columns_for(field, domain)
    for raw in candidates:
        comment = schema_comments[domain].get(raw)
        if comment:
            source = "schema_raw_columns" if field in RAW_COLUMNS else "schema_canonical_name"
            fl_text = label_for_field(field, domain)
            if fl_text and fl_text != comment:
                report["mismatches"].append((field, domain, raw, comment, fl_text))
            return comment, source
    # 원본에 없음 -> field_labels.py 폴백 (파이프라인 파생 필드로 간주)
    fl_text = label_for_field(field, domain)
    report["not_found_in_schema"].append((field, domain, candidates))
    return fl_text, "field_labels_fallback"


# ---------------------------------------------------------------------------
# 4. 필드별로 도메인을 comment 기준으로 그룹핑
# ---------------------------------------------------------------------------


def build_field_plan(schema_comments: dict[str, dict[str, str]], report: dict) -> dict[str, dict]:
    """도메인마다 독립된 선언을 만든다 — 코멘트가 우연히 같아도 TTL 구조에서
    미리 "같은 필드"라고 병합하지 않는다(2026-09 세션 결정: "같다"는 판단은 항상
    shared_label_map()이 런타임에 코멘트 텍스트를 비교해서 알아서 하는 것이지,
    온톨로지 저작 시점에 사람/스크립트가 미리 계산해서 구조에 박아넣는 게 아니다 —
    dur/fn_effective_duration이 이미 이 방식으로 정확히 동작하고 있었다)."""
    classification = classify_field_domains(None)
    plan: dict[str, dict] = {}
    for field in FIELD_SPECS:
        domains = classification.get(field, [])
        if not domains:
            report["no_domain"].append(field)
            continue
        per_domain_comment: dict[str, str] = {}
        per_domain_source: dict[str, str] = {}
        for d in domains:
            comment, source = true_comment(field, d, schema_comments, report)
            per_domain_comment[d] = comment
            per_domain_source[d] = source
        plan[field] = {
            "domains": domains,
            "comment_by_domain": per_domain_comment,
            "source_by_domain": per_domain_source,
        }
    return plan


# ---------------------------------------------------------------------------
# 5. TTL 블록 텍스트 생성
# ---------------------------------------------------------------------------


def render_block(subject: str, domains: list[str], comment: str, field: str, range_xsd: str) -> str:
    """필드 선언에는 fp:column(데이터에 있는 컬럼명)과 rdfs:comment(데이터에 있는
    컬럼코멘트) 딱 두 가지 실질 정보만 담는다(2026-09 세션 결정, 재확인). rdfs:label은
    아예 안 쓴다 — canonical 필드명을 그대로 반복하는 것조차 fp:column과 완전히
    겹치는 중복이라 제거한다(fp:alias도 이미 없음). 클래스/관계(product_type 등)의
    rdfs:label은 이것과 무관하게 그대로 유지된다(ontology.py의 _class_terms 참고)."""
    domain_triples = " ; ".join(f"rdfs:domain {DOMAIN_CLASS[d]}" for d in domains)
    lines = [
        f"fp:{subject} a owl:DatatypeProperty ;",
        f"    {domain_triples} ; rdfs:range {range_xsd} ;",
        f'    rdfs:comment "{comment}"@ko ;',
        f'    fp:column "{field}" .',
    ]
    return "\n".join(lines)


def main() -> None:
    schema_comments = load_schema_comments()
    existing = load_existing_declarations()
    report: dict = {
        "mismatches": [],
        "not_found_in_schema": [],
        "no_domain": [],
        "new_fields": [],
        "split_fields": [],
        "coincidentally_identical_but_still_split": [],
    }
    plan = build_field_plan(schema_comments, report)

    range_by_field = {name: KIND_TO_XSD[spec.kind] for name, spec in FIELD_SPECS.items()}

    # 파일별로 새로 생성할 블록들을 모은다 (common.ttl에는 이번 마이그레이션 대상
    # 필드를 절대 추가하지 않는다 — 도메인이 몇 개든 항상 도메인별 파일에 각자
    # 선언한다)
    blocks_by_file: dict[str, list[str]] = {f: [] for f in DOMAIN_FILES.values()}

    was_covered = set()
    for filename, by_column in existing.items():
        was_covered |= set(by_column)

    for field, info in plan.items():
        domains = info["domains"]
        comment_by_domain = info["comment_by_domain"]
        range_xsd = range_by_field[field]

        if field not in was_covered:
            report["new_fields"].append(field)
        if len(domains) > 1:
            report["split_fields"].append((field, domains, comment_by_domain))
            if len(set(comment_by_domain.values())) == 1:
                # 우연히 코멘트가 같더라도 구조적으로 병합하지 않는다 — 참고용으로만 기록.
                # shared_label_map()이 런타임에 이 코멘트 텍스트 동일성을 보고 알아서 묶는다.
                report["coincidentally_identical_but_still_split"].append(
                    (field, domains, next(iter(comment_by_domain.values())))
                )

        for d in domains:
            fname = DOMAIN_FILES[d]
            subject = snake_to_camel(field) if len(domains) == 1 else snake_to_camel(field) + DOMAIN_SUFFIX[d]
            block = render_block(subject, [d], comment_by_domain[d], field, range_xsd)
            blocks_by_file[fname].append(block)

    # ---- 리포트 출력 ----
    print("=" * 80)
    print(f"전체 FIELD_SPECS: {len(FIELD_SPECS)}개")
    print(f"신규 추가된 필드(기존 TTL에 전혀 없었음): {len(report['new_fields'])}개")
    print(f"  {sorted(report['new_fields'])}")
    print(f"여러 도메인에 걸친 필드(전부 도메인별로 분리 — 구조적 병합 없음): {len(report['split_fields'])}개")
    for f, ds, cbd in report["split_fields"]:
        print(f"  {f}: {cbd}")
    print(f"⚠️ 그 중 코멘트가 우연히 같은 필드(참고용, TTL엔 여전히 분리 선언됨 — shared_label_map이 런타임에 알아서 묶음): {len(report['coincidentally_identical_but_still_split'])}개")
    for f, ds, c in report["coincidentally_identical_but_still_split"]:
        print(f"  {f} ({ds}): {c!r}")
    print(f"field_labels.py 텍스트와 원본 schema.xlsx가 서로 다른 경우: {len(report['mismatches'])}개")
    for f, d, raw, schema_c, fl_c in report["mismatches"]:
        print(f"  {f}/{d} (raw={raw}): schema.xlsx={schema_c!r} vs field_labels.py={fl_c!r}")
    print(f"원본 schema.xlsx에서 못 찾아 field_labels.py로 폴백한 경우: {len(report['not_found_in_schema'])}개")
    for f, d, candidates in report["not_found_in_schema"]:
        print(f"  {f}/{d}: 후보 raw컬럼 {candidates} 못 찾음")
    if report["no_domain"]:
        print(f"⚠️ 어느 도메인에도 안 속하는 필드: {report['no_domain']}")

    # ---- 파일 쓰기 ----
    write_ttl_files(blocks_by_file)


def write_ttl_files(blocks_by_file: dict[str, list[str]]) -> None:
    header = (
        '@prefix fp: <https://example.org/financial-product-agent/ontology#> .\n'
        '@prefix owl: <http://www.w3.org/2002/07/owl#> .\n'
        '@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n'
        '@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n'
        '@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n\n\n'
    )

    # common.ttl: 헤더 + Product/ETF/도메인 클래스 + 참조 클래스 + ObjectProperty 전부
    # 원본 그대로 보존(RankingSemantic 블록만 삭제) + 새로 생성된 공용 필드 블록
    common_preamble = '''fp:Product a owl:Class ; rdfs:label "금융상품"@ko ;
    rdfs:comment "네 도메인 파일(bond_kr/etf_kr/etf_gl/fund_pub)의 공통 상위 클래스."@ko .
fp:ETF a owl:Class ; rdfs:subClassOf fp:Product ; rdfs:label "ETF"@ko .

fp:Bond a owl:Class ; rdfs:subClassOf fp:Product ;
    rdfs:label "채권"@ko ;
    fp:alias "국내채권", "국내 채권", "채권", "bond" ;
    fp:productType "DOMESTIC_BOND" .
fp:DomesticETF a owl:Class ; rdfs:subClassOf fp:ETF ;
    rdfs:label "국내 ETF"@ko ;
    fp:alias "국내etf", "국내 etf", "한국 etf", "domestic etf" ;
    fp:productType "DOMESTIC_ETF" .
fp:OverseasETF a owl:Class ; rdfs:subClassOf fp:ETF ;
    rdfs:label "해외 ETF"@ko ;
    fp:alias "해외etf", "해외 etf", "미국 etf", "overseas etf", "foreign etf" ;
    fp:productType "OVERSEAS_ETF" .
fp:PublicFund a owl:Class ; rdfs:subClassOf fp:Product ;
    rdfs:label "공모펀드"@ko ;
    fp:alias "공모펀드", "공모 펀드", "펀드", "public fund" ;
    fp:productType "PUBLIC_FUND" .

fp:AssetManager a owl:Class ; rdfs:label "운용사/발행사"@ko .
fp:AssetClass a owl:Class ; rdfs:label "자산군"@ko .
fp:InvestmentRegion a owl:Class ; rdfs:label "투자지역"@ko .
fp:Currency a owl:Class ; rdfs:label "통화"@ko .
fp:RiskGrade a owl:Class ; rdfs:label "위험/신용등급"@ko .
fp:BenchmarkIndex a owl:Class ; rdfs:label "기초지수/벤치마크"@ko .
fp:ExternalDocument a owl:Class ; rdfs:label "외부 근거 문서"@ko .
fp:ConstituentSecurity a owl:Class ; rdfs:label "ETF 구성종목"@ko .

fp:managedBy a owl:ObjectProperty ;
    rdfs:domain fp:Product ; rdfs:range fp:AssetManager ;
    rdfs:label "운용/발행 주체"@ko ;
    fp:alias "운용하는", "운용사", "발행한", "managed by", "issued by" .
fp:manages a owl:ObjectProperty ;
    owl:inverseOf fp:managedBy ;
    rdfs:domain fp:AssetManager ; rdfs:range fp:Product ;
    rdfs:label "운용/발행하는 상품"@ko ;
    fp:alias "운용 상품", "운용하는 상품", "manages" .
fp:hasAssetClass a owl:ObjectProperty ;
    rdfs:domain fp:Product ; rdfs:range fp:AssetClass ;
    rdfs:label "자산군"@ko ;
    fp:alias "자산군", "투자자산", "has asset class" .
fp:investsInRegion a owl:ObjectProperty ;
    rdfs:domain fp:Product ; rdfs:range fp:InvestmentRegion ;
    rdfs:label "투자지역"@ko ;
    fp:alias "투자지역", "투자하는 지역", "invests in" .
fp:denominatedIn a owl:ObjectProperty ;
    rdfs:domain fp:Product ; rdfs:range fp:Currency ;
    rdfs:label "표시통화"@ko ;
    fp:alias "통화", "표시통화", "denominated in" .
fp:hasRiskGrade a owl:ObjectProperty ;
    rdfs:domain fp:Product ; rdfs:range fp:RiskGrade ;
    rdfs:label "위험/신용등급"@ko ;
    fp:alias "위험등급", "신용등급", "has risk grade" .
fp:tracksIndex a owl:ObjectProperty ;
    rdfs:domain fp:Product ; rdfs:range fp:BenchmarkIndex ;
    rdfs:label "추종 지수/벤치마크"@ko ;
    fp:alias "추종", "기초지수", "벤치마크", "tracks index" .
fp:holdsSecurity a owl:ObjectProperty ;
    rdfs:domain fp:ETF ; rdfs:range fp:ConstituentSecurity ;
    rdfs:label "구성종목으로 보유"@ko ;
    fp:alias "구성종목", "편입종목", "보유종목", "holds", "contains security" .
fp:heldBy a owl:ObjectProperty ;
    owl:inverseOf fp:holdsSecurity ;
    rdfs:domain fp:ConstituentSecurity ; rdfs:range fp:ETF ;
    rdfs:label "편입된 ETF"@ko ;
    fp:alias "편입한 etf", "포함하는 etf", "held by" .
'''
    # common.ttl에는 이번 마이그레이션 대상 필드(FIELD_SPECS)를 절대 추가하지 않는다
    # — 도메인이 몇 개든 항상 도메인별 파일에 각자 선언한다("같다"는 판단은 항상
    # shared_label_map()이 런타임에 하는 것이지 TTL 구조에 미리 박아넣지 않는다).
    # 199개 FIELD_SPECS에 없는 기존 common.ttl 필드(etf_sector, dividend_cycle 등)만
    # 원래 파일에서 그대로 읽어와 보존한다.
    preserved = extract_untracked_datatype_blocks("common.ttl")

    content = header + common_preamble
    if preserved:
        content += "\n" + "\n\n".join(preserved)
    (ONTOLOGY_DIR / "common.ttl").write_text(content.rstrip() + "\n", encoding="utf-8")

    class_line = {
        "bond_kr.ttl": 'fp:Bond a owl:Class ; rdfs:subClassOf fp:Product ; rdfs:label "채권"@ko .',
        "etf_kr.ttl": 'fp:DomesticETF a owl:Class ; rdfs:subClassOf fp:ETF ; rdfs:label "국내 ETF"@ko .',
        "etf_gl.ttl": 'fp:OverseasETF a owl:Class ; rdfs:subClassOf fp:ETF ; rdfs:label "해외 ETF"@ko .',
        "fund_pub.ttl": 'fp:PublicFund a owl:Class ; rdfs:subClassOf fp:Product ; rdfs:label "공모펀드"@ko .',
    }
    for filename in DOMAIN_FILES.values():
        preserved = extract_untracked_datatype_blocks(filename)
        content = header + class_line[filename] + "\n\n" + "\n\n".join(blocks_by_file[filename])
        if preserved:
            content += "\n\n" + "\n\n".join(preserved)
        (ONTOLOGY_DIR / filename).write_text(content.rstrip() + "\n", encoding="utf-8")


def extract_untracked_datatype_blocks(filename: str) -> list[str]:
    """FIELD_SPECS에 없는 DatatypeProperty 블록(원본 그대로, alias만 제거)을 뽑아온다."""
    text = (ONTOLOGY_DIR / filename).read_text(encoding="utf-8")
    blocks = re.split(r"\n\s*\n", text)
    result = []
    for block in blocks:
        block = block.strip()
        if not block or not block.startswith("fp:") or "a owl:DatatypeProperty" not in block:
            continue
        m = re.search(r'fp:column\s+"([^"]+)"', block)
        if not m:
            continue
        column = m.group(1)
        if column in FIELD_SPECS:
            continue  # 이건 새로 생성된 블록으로 대체됨
        # alias 라인 제거(필드 alias는 전부 없앤다는 원칙)
        block = re.sub(r'\s*;\s*\n\s*fp:alias[^.]*\.', ' .', block)
        block = re.sub(r'\s*fp:alias[^.]*\.\n?', '', block)
        result.append(block)
    return result


if __name__ == "__main__":
    main()
