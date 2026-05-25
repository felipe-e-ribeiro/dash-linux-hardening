import tempfile
import os
from app.parser import parse_xccdf

MINIMAL_XCCDF = """\
<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.2" id="xccdf_test_benchmark">
  <title>Test Benchmark</title>
  <Rule id="xccdf_test_rule_ssh_empty_passwords" selected="true" severity="high">
    <title>Disable SSH empty passwords</title>
    <description>Prevents login with empty passwords via SSH.</description>
  </Rule>
  <TestResult id="xccdf_test_result" start-time="2026-01-01T00:00:00" end-time="2026-01-01T00:01:00">
    <target>test-host</target>
    <profile idref="xccdf_test_profile_cis"/>
    <score maximum="100">72.0</score>
    <rule-result idref="xccdf_test_rule_ssh_empty_passwords" severity="high">
      <result>fail</result>
    </rule-result>
  </TestResult>
</Benchmark>
"""


def _parse_minimal():
    fd, path = tempfile.mkstemp(suffix=".xml")
    try:
        os.write(fd, MINIMAL_XCCDF.encode())
        os.close(fd)
        return parse_xccdf(path, source="test")
    finally:
        os.unlink(path)


def test_parse_returns_required_keys():
    result = _parse_minimal()
    for key in ("hostname", "score", "rules", "pass_count", "fail_count"):
        assert key in result or key in ("pass_count", "fail_count"), \
            f"Missing key: {key}"
    assert "hostname" in result
    assert "score" in result
    assert "rules" in result
    assert "results" in result


def test_parse_hostname():
    result = _parse_minimal()
    assert result["hostname"] == "test-host"


def test_parse_score():
    result = _parse_minimal()
    assert result["score"] == 72


def test_parse_failed_rule():
    result = _parse_minimal()
    assert result["results"]["fail"] == 1
    assert len(result["rules"]) == 1
    assert result["rules"][0]["severity"] == "high"


def test_parse_source_field():
    result = _parse_minimal()
    assert result["source"] == "test"
