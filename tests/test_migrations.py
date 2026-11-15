# from pathlib import Path
#
#
# VERSIONS = Path(__file__).parents[1] / "services/backend/alembic/versions"
#
#
# def test_installations_software_index_is_created_by_one_migration():
#     initial = (VERSIONS / "0001_mvp_assets.py").read_text()
#     follow_up = (VERSIONS / "0004_index_installation_software.py").read_text()
#
#     assert 'op.create_index("ix_installations_software_id"' in initial
#     assert 'op.create_index("ix_installations_software_id"' not in follow_up
