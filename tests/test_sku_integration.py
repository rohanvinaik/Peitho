"""INTEGRATION test for peitho.sku's still-public I/O helper.

The image-hash readers (image_md5 / load_article_images / article_image_hashes) now live in the cassette's
private data-input adapter; their parsing is exercised by the behavior oracle. The pure dedupe decision
(cluster_by_hash) and the SKU decode (parse_sku / age_years) are Detective-pinned in their synth suites +
test_sku_intent. load_sample_skus (the SKU-code sample sweep) is not backend-schema-bound and stays here.
"""

import json

import peitho.sku as sku


def test_load_sample_skus_walks_nested_sku_codes(tmp_path):
    d = tmp_path / "detail"
    d.mkdir()
    (d / "s.json").write_text(json.dumps({"lines": [{"sku_code": "26p100"}, {"x": {"sku_code": "25p9"}}]}))
    (d / "bad.json").write_text("{not json")  # unreadable -> skipped, sweep continues
    assert sku.load_sample_skus((str(d / "*.json"),), "sku_code") == {"26p100", "25p9"}
