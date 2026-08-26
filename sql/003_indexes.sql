CREATE INDEX IF NOT EXISTS ix_bond_product_id ON core.domestic_bonds (pd_no);
CREATE INDEX IF NOT EXISTS ix_bond_maturity ON core.domestic_bonds (mat_dt);
CREATE INDEX IF NOT EXISTS ix_bond_yield ON core.domestic_bonds (buy_yield DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS ix_bond_risk ON core.domestic_bonds (pd_risk_gcd, crd_grd);
CREATE INDEX IF NOT EXISTS ix_bond_buyable ON core.domestic_bonds (buyable_quantity DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS ix_bond_name_trgm ON core.domestic_bonds USING GIN (pd_nm gin_trgm_ops);

CREATE INDEX IF NOT EXISTS ix_detf_product_id ON core.domestic_etfs (pd_itm_no);
CREATE INDEX IF NOT EXISTS ix_detf_type_region ON core.domestic_etfs (wu_inv_ast_type, wu_inv_rgn);
CREATE INDEX IF NOT EXISTS ix_detf_fee ON core.domestic_etfs (cu_charge_rt ASC NULLS LAST);
CREATE INDEX IF NOT EXISTS ix_detf_return_1y ON core.domestic_etfs (du_er_1y DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS ix_detf_aum ON core.domestic_etfs (pd_net_tamt DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS ix_detf_risk ON core.domestic_etfs (pd_risk_cd, pd_risk_nm);
CREATE INDEX IF NOT EXISTS ix_detf_name_trgm ON core.domestic_etfs USING GIN (pd_nm gin_trgm_ops);

CREATE INDEX IF NOT EXISTS ix_oetf_product_id ON core.overseas_etfs (pd_itm_no);
CREATE INDEX IF NOT EXISTS ix_oetf_isin ON core.overseas_etfs (pd_isin_cd);
CREATE INDEX IF NOT EXISTS ix_oetf_type_region ON core.overseas_etfs (wu_inv_ast_type, wu_inv_rgn);
CREATE INDEX IF NOT EXISTS ix_oetf_fee ON core.overseas_etfs (cu_charge_rt ASC NULLS LAST);
CREATE INDEX IF NOT EXISTS ix_oetf_aum ON core.overseas_etfs (du_last_aum DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS ix_oetf_name_trgm ON core.overseas_etfs USING GIN (pd_nm gin_trgm_ops);

CREATE INDEX IF NOT EXISTS ix_fund_product_id ON core.public_funds (itm_no);
CREATE INDEX IF NOT EXISTS ix_fund_type_region ON core.public_funds (or_attr_desc, fd_ivst_rgn_desc);
CREATE INDEX IF NOT EXISTS ix_fund_risk ON core.public_funds (zrin_fd_ivst_risk_gcd, zrin_fd_ivst_risk_grd_nm);
CREATE INDEX IF NOT EXISTS ix_fund_return_1y ON core.public_funds (fd_yr1_ern_r DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS ix_fund_aum ON core.public_funds (fd_nast_suma DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS ix_fund_name_trgm ON core.public_funds USING GIN (itm_nm gin_trgm_ops);
