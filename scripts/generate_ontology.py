"""1회성 온톨로지 ttl 생성 스크립트 (2026-08 시점: 최초 생성 당시 스냅샷, 현재는 비활성).

FIELD_SPECS(src/query/fields.py) + 실측 도메인 분류(Postgres) + 당시
ontology/term_map.json(별칭)을 조합해서 ontology/{common,bond_kr,etf_kr,
etf_gl,fund_pub}.ttl 5개를 최초 생성했다.

이후 term_map.json은 삭제됐고(ttl 파일 자체가 유일한 소스), ttl 5개에는
그 뒤로 rdfs:comment 보강(2026-08-21 스냅샷의 공식 컬럼코멘트 반영 등)과
alias 수동 추가가 계속 쌓였다. 그래서 이 스크립트를 그대로 재실행하면
term_map.json이 없어 즉시 실패하고, 설령 입력을 복원해도 그간 손으로
누적한 rdfs:comment/fp:alias가 전부 덮어써진다 — 재실행 금지.

앱 실행 경로에는 들어가지 않는 개발용 도구이며, 현재는 "ttl 파일이
어떤 모양으로 시작됐는지"를 보여주는 기록용으로만 남겨둔다. ttl 5개에
새 필드/별칭/설명을 추가할 때는 이 스크립트가 아니라 ttl 파일을 직접
편집한다.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import database_url  # noqa: E402
from src.query.fields import FIELD_SPECS  # noqa: E402

ONTOLOGY_DIR = PROJECT_ROOT / "ontology"
TERM_MAP_PATH = ONTOLOGY_DIR / "term_map.json"
NS = "https://example.org/financial-product-agent/ontology#"

PRODUCT_TYPES = ("DOMESTIC_BOND", "DOMESTIC_ETF", "OVERSEAS_ETF", "PUBLIC_FUND")
DOMAIN_FILES = {
    "DOMESTIC_BOND": "bond_kr.ttl",
    "DOMESTIC_ETF": "etf_kr.ttl",
    "OVERSEAS_ETF": "etf_gl.ttl",
    "PUBLIC_FUND": "fund_pub.ttl",
}
# (클래스 로컬명, subClassOf, 한글 라벨)
DOMAIN_CLASS = {
    "DOMESTIC_BOND": ("Bond", "fp:Product", "채권"),
    "DOMESTIC_ETF": ("DomesticETF", "fp:ETF", "국내 ETF"),
    "OVERSEAS_ETF": ("OverseasETF", "fp:ETF", "해외 ETF"),
    "PUBLIC_FUND": ("PublicFund", "fp:Product", "공모펀드"),
}
KIND_TO_XSD = {
    "text": "xsd:string",
    "numeric": "xsd:decimal",
    "date": "xsd:date",
    "boolean": "xsd:boolean",
}

# 기존 ontology/financial_product_ontology.ttl(phase 2.5 때 작성)에 이미 있던
# 공용 참조 클래스 + object property 정의를 그대로 옮긴다 (새로 지어내는 게 아님).
COMMON_REFERENCE_CLASSES = [
    ("AssetManager", "운용사/발행사"),
    ("AssetClass", "자산군"),
    ("InvestmentRegion", "투자지역"),
    ("Currency", "통화"),
    ("RiskGrade", "위험/신용등급"),
    ("BenchmarkIndex", "기초지수/벤치마크"),
    ("ExternalDocument", "외부 근거 문서"),
    ("ConstituentSecurity", "ETF 구성종목"),
]
# (로컬명, inverseOf, domain, range, 한글 라벨)
COMMON_OBJECT_PROPERTIES = [
    ("managedBy", None, "fp:Product", "fp:AssetManager", "운용/발행 주체"),
    ("manages", "fp:managedBy", "fp:AssetManager", "fp:Product", "운용/발행하는 상품"),
    ("hasAssetClass", None, "fp:Product", "fp:AssetClass", "자산군"),
    ("investsInRegion", None, "fp:Product", "fp:InvestmentRegion", "투자지역"),
    ("denominatedIn", None, "fp:Product", "fp:Currency", "표시통화"),
    ("hasRiskGrade", None, "fp:Product", "fp:RiskGrade", "위험/신용등급"),
    ("tracksIndex", None, "fp:Product", "fp:BenchmarkIndex", "추종 지수/벤치마크"),
    ("holdsSecurity", None, "fp:ETF", "fp:ConstituentSecurity", "구성종목으로 보유"),
    ("heldBy", "fp:holdsSecurity", "fp:ConstituentSecurity", "fp:ETF", "편입된 ETF"),
]


def turtle_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def snake_to_camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.capitalize() for part in rest)


def classify_field_domains(cur) -> dict[str, list[str]]:
    """129개 필드 각각이 4개 product_type 중 실제로 어디서 채워지는지 실측."""
    fields = list(FIELD_SPECS)
    select_parts = []
    for field in fields:
        for pt in PRODUCT_TYPES:
            select_parts.append(
                f"COUNT(*) FILTER (WHERE product_type='{pt}' AND {field} IS NOT NULL) "
                f'AS "{field}__{pt}"'
            )
    sql = "SELECT " + ", ".join(select_parts) + " FROM search.product_catalog"
    cur.execute(sql)
    row = cur.fetchone()
    colnames = [d.name for d in cur.description]
    result = dict(zip(colnames, row))

    classification: dict[str, list[str]] = {}
    for field in fields:
        domains = [pt for pt in PRODUCT_TYPES if result[f"{field}__{pt}"] > 0]
        classification[field] = domains
    return classification


def target_domains_for(domains: list[str]) -> list[str]:
    """공통(4개 전부) 또는 어디서도 안 채워지는(0개) 필드는 common.ttl 하나로.
    그 외엔 실제로 채워지는 도메인 파일마다 각각 독립 선언."""
    if len(domains) in (0, len(PRODUCT_TYPES)):
        return []  # common.ttl 전용 표시
    return domains


_HANGUL_RE = re.compile(r"[가-힣]")


def field_property_block(field: str, domain_class: str, aliases: list[str]) -> str:
    spec = FIELD_SPECS[field]
    xsd_type = KIND_TO_XSD[spec.kind]
    local_name = snake_to_camel(field)
    korean_aliases = [a for a in aliases if _HANGUL_RE.search(a)]
    if korean_aliases:
        label, label_lang = korean_aliases[0], "ko"
    else:
        label, label_lang = field, "en"
    lines = [
        f"fp:{local_name} a owl:DatatypeProperty ;",
        f"    rdfs:domain {domain_class} ; rdfs:range {xsd_type} ;",
        f'    rdfs:label "{turtle_escape(label)}"@{label_lang} ;',
    ]
    if aliases:
        alias_str = ", ".join(f'"{turtle_escape(a)}"' for a in aliases)
        lines.append(f'    fp:column "{field}" ;')
        lines.append(f"    fp:alias {alias_str} .")
    else:
        lines.append(f'    fp:column "{field}" .')
    return "\n".join(lines)


def header() -> str:
    return (
        "@prefix fp: <" + NS + "> .\n"
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
        "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n"
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
    )


def build_common_ttl(
    common_fields: list[str],
    field_aliases: dict[str, list[str]],
    term_map: dict,
) -> str:
    lines = [header(), ""]
    lines.append(
        "fp:Product a owl:Class ; rdfs:label \"금융상품\"@ko ;\n"
        '    rdfs:comment "네 도메인 파일(bond_kr/etf_kr/etf_gl/fund_pub)의 공통 상위 클래스."@ko .'
    )
    lines.append('fp:ETF a owl:Class ; rdfs:subClassOf fp:Product ; rdfs:label "ETF"@ko .')
    lines.append("")

    # product_type 별 도메인 클래스 + fp:productType 주석 + fp:alias
    pt_aliases = {item["canonical"]: item["aliases"] for item in term_map["product_types"]}
    for pt in PRODUCT_TYPES:
        local, parent, label = DOMAIN_CLASS[pt]
        aliases = pt_aliases.get(pt, [])
        alias_line = ""
        if aliases:
            alias_str = ", ".join(f'"{turtle_escape(a)}"' for a in aliases)
            alias_line = f"\n    fp:alias {alias_str} ;"
        lines.append(
            f"fp:{local} a owl:Class ; rdfs:subClassOf {parent} ;\n"
            f'    rdfs:label "{label}"@ko ;{alias_line}\n'
            f'    fp:productType "{pt}" .'
        )
    lines.append("")

    for local, label in COMMON_REFERENCE_CLASSES:
        lines.append(f'fp:{local} a owl:Class ; rdfs:label "{label}"@ko .')
    lines.append("")

    rel_aliases = {item["canonical"]: item["aliases"] for item in term_map["relations"]}
    for local, inverse, domain, range_, label in COMMON_OBJECT_PROPERTIES:
        aliases = rel_aliases.get(local, [])
        parts = [f"fp:{local} a owl:ObjectProperty ;"]
        if inverse:
            parts.append(f"    owl:inverseOf {inverse} ;")
        parts.append(f"    rdfs:domain {domain} ; rdfs:range {range_} ;")
        if aliases:
            alias_str = ", ".join(f'"{turtle_escape(a)}"' for a in aliases)
            parts.append(f'    rdfs:label "{label}"@ko ;')
            parts.append(f"    fp:alias {alias_str} .")
        else:
            parts.append(f'    rdfs:label "{label}"@ko .')
        lines.append("\n".join(parts))
    lines.append("")

    lines.append("fp:RankingSemantic a owl:Class .")
    ranking_name_seq = 0
    for item in term_map["ranking_semantics"]:
        ranking_name_seq += 1
        local = f"rankingSemantic{ranking_name_seq}"
        alias_str = ", ".join(f'"{turtle_escape(a)}"' for a in item["aliases"])
        lines.append(
            f"fp:{local} a fp:RankingSemantic ;\n"
            f'    fp:column "{item["field"]}" ; fp:order "{item["order"]}" ;\n'
            f"    fp:alias {alias_str} ."
        )
    lines.append("")

    for field in common_fields:
        lines.append(field_property_block(field, "fp:Product", field_aliases.get(field, [])))
        lines.append("")

    return "\n".join(lines)


def build_domain_ttl(
    product_type: str,
    fields: list[str],
    field_aliases: dict[str, list[str]],
) -> str:
    local, parent, label = DOMAIN_CLASS[product_type]
    lines = [header(), ""]
    lines.append(f"fp:{local} a owl:Class ; rdfs:subClassOf {parent} ; rdfs:label \"{label}\"@ko .")
    lines.append("")
    for field in fields:
        lines.append(field_property_block(field, f"fp:{local}", field_aliases.get(field, [])))
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    term_map = json.loads(TERM_MAP_PATH.read_text(encoding="utf-8"))
    field_aliases = {item["canonical"]: item["aliases"] for item in term_map["fields"]}

    with psycopg.connect(database_url()) as conn, conn.cursor() as cur:
        classification = classify_field_domains(cur)

    common_fields: list[str] = []
    domain_fields: dict[str, list[str]] = {pt: [] for pt in PRODUCT_TYPES}
    for field in FIELD_SPECS:
        if field == "product_type":
            # 클래스 계층(fp:Bond/fp:DomesticETF/...)이 이미 이걸 표현하고,
            # fp:productType는 그 클래스들에 붙는 주석 프로퍼티 이름과 겹치므로 제외.
            continue
        domains = classification[field]
        targets = target_domains_for(domains)
        if not targets:
            common_fields.append(field)
        else:
            for pt in targets:
                domain_fields[pt].append(field)

    ONTOLOGY_DIR.mkdir(parents=True, exist_ok=True)
    (ONTOLOGY_DIR / "common.ttl").write_text(
        build_common_ttl(common_fields, field_aliases, term_map), encoding="utf-8"
    )
    for pt in PRODUCT_TYPES:
        (ONTOLOGY_DIR / DOMAIN_FILES[pt]).write_text(
            build_domain_ttl(pt, domain_fields[pt], field_aliases), encoding="utf-8"
        )

    print("common.ttl:", len(common_fields), "fields")
    for pt in PRODUCT_TYPES:
        print(f"{DOMAIN_FILES[pt]}:", len(domain_fields[pt]), "fields")


if __name__ == "__main__":
    main()
