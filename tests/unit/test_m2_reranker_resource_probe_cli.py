from __future__ import annotations

import pytest

from scripts.run_m2_reranker_resource_probe import _parse_args


def test_real_probe_cli_requires_explicit_opt_in_and_has_no_download_flag() -> None:
    with pytest.raises(SystemExit):
        _parse_args([])
    with pytest.raises(SystemExit):
        _parse_args(["--run-real", "--allow-download"])

    args = _parse_args(["--run-real"])

    assert args.run_real is True
