def test_package_imports_with_version() -> None:
    import mymind_importer

    assert mymind_importer.__version__
