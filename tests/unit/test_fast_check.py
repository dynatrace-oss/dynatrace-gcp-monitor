from assertpy import assert_that

from lib.fast_check import format_dynatrace_access_key


def test_token_masking_old_format():
    assert_that(format_dynatrace_access_key("UB7CLJy7RQS-qZD1wfCfX")).is_equal_to("UB7***************CfX")


def test_token_masking_new_format():
    assert_that(format_dynatrace_access_key(
        "dt0c01.FAKEEU7QQ5KW7BZVN2XQ7KD7.FAKEJFHLZKTOUTFZKAAZTRSM7HFKPHFRCJKJN5CWTHMFD7UNE77TPZ7PE77WA7JY")).is_equal_to(
        "dt0c01.FAK***********************************************************************************7JY")


def test_token_masking_invalid_format():
    assert_that(format_dynatrace_access_key("short")).is_equal_to("Invalid Token")
