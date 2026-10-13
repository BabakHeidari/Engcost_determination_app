"""Inspect the JSON data actually delivered in a rendered HTML page."""

import json
import re


def script_json(html, element_id):
    match = re.search(r'<script\b[^>]*\bid="' + re.escape(element_id) + r'"[^>]*>(.*?)</script>', html, re.S)
    assert match is not None, f"Missing JSON script {element_id}"
    return json.loads(match.group(1))


def javascript_json(html, variable):
    match = re.search(r'\bconst\s+' + re.escape(variable) + r'\s*=\s*', html)
    assert match is not None, f"Missing JSON assignment {variable}"
    return json.JSONDecoder().raw_decode(html[match.end():])[0]
