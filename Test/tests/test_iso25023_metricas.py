from scan import python_metrics, schema_metrics, endpoint_metrics, auth_metrics, product_size


def test_loc_real_no_cero():
    size = product_size()
    assert size["loc"] > 5000
    assert size["files"] > 20
    assert size["has_backend"] and size["has_frontend"] and size["has_docker"]


def test_complejidad_media_bajo_umbral():
    py = python_metrics()
    assert py["functions"] > 50
    assert py["avg_cc"] < 12
    assert py["sql_param_ratio"] >= 0.95


def test_esquema_calidad_datos_25012():
    sch = schema_metrics()
    assert sch["table_count"] >= 10
    assert sch["has_historial"]
    assert sch["has_sla"]
    assert sch["has_embedding"]
    assert sch["has_pgvector"]
    assert sch["foreign_keys"] >= 8
    assert sch["indexes"] >= 8


def test_superficie_api():
    ep = endpoint_metrics()
    assert ep["count"] >= 25
    assert ep["health"]
    assert ep["by_method"]["get"] >= 8
    assert ep["by_method"]["post"] >= 8


def test_controles_seguridad_medibles():
    auth = auth_metrics()
    assert auth["jwt"]
    assert auth["bcrypt"]
    assert auth["oauth2"]
    assert auth["rate_limit"]
    assert auth["roles"]
    assert auth["gitignore_env"]
    assert auth["magic_bytes"]
