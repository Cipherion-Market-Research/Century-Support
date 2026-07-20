from kpi_sync.config import Config


def test_abacus_disabled_by_default():
    # Amendment C-R1: owner does not want Abacus Indexer data exposed
    # publicly -- must be off unless explicitly enabled.
    assert Config.ABACUS_ENABLED is False
