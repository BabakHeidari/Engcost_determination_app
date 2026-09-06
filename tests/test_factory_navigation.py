from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_factory_pages_use_bookmarkable_get_navigation():
    routes = (ROOT / "modules/factory_parameters/routes.py").read_text(encoding="utf-8")
    factories = (ROOT / "templates/factory_parameters/factories.html").read_text(encoding="utf-8")
    details = (ROOT / "templates/factory_parameters/factory_details.html").read_text(encoding="utf-8")
    subfield = (ROOT / "templates/factory_parameters/factory_subfield.html").read_text(encoding="utf-8")

    assert '@factory_parameters_bp.route("/factory_parameters/<factory_name>", methods=["GET", "POST"])' in routes
    assert 'request.form["factory name"]' not in routes
    assert 'request.form["Subfield"]' not in routes
    assert 'code=303' in routes
    assert '<a href="${factoryUrl}"' in factories
    assert '<a href="${subfieldUrl}"' in details
    assert "url_for('factory_parameters.factory_parameters')" in details
    assert "url_for('factory_parameters.factory_details', factory_name=factory_name)" in subfield
    assert "history.back()" not in details
    assert "history.back()" not in subfield
