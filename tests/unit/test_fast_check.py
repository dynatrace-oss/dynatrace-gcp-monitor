from assertpy import assert_that

from lib.fast_check import obfuscate_dynatrace_access_key


def test_token_masking_old_format():
    assert_that(obfuscate_dynatrace_access_key("FAKEFAKE7FA-keFAkefAke")).is_equal_to("FAK****************Ake")


def test_token_masking_new_format():
    assert_that(obfuscate_dynatrace_access_key(
        "dt0c01.FAKE11.FAKEEU7QQ5KW7BZVN2XQFAKEFAKEJFHLZKTOUTFZKAAZTRSFR4HTJXZKXIZPPUVZ2D7YPRXY2IUFAKE7JY")).is_equal_to(
        "dt0c01.FAK***********************************************************************************7JY")


def test_token_masking_invalid_format():
    assert_that(obfuscate_dynatrace_access_key("short")).is_equal_to("Invalid Token")
