#   Copyright 2021 Dynatrace LLC
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

from assertpy import assert_that

from lib.fast_check import obfuscate_dynatrace_access_key


def test_token_masking_old_format():
    assert_that(obfuscate_dynatrace_access_key("FAKEFAKE7FA-keFAkefAke")).is_equal_to("FAK****************Ake")


def test_token_masking_new_format():
    token_public_part = "dt0c01.FAKE11."
    token_private_part = "FAKEEU7QQ5KW7BZVN2XQFAKEFAKEJFHLZKTOUTFZKAAZTRSFR4HTJXZKXIZPPUVZ2D7YPRXY2IUFAKE7JY"
    assert_that(obfuscate_dynatrace_access_key(
        token_public_part + token_private_part)).is_equal_to(
        "dt0c01.FAKE11")


def test_token_masking_invalid_format():
    assert_that(obfuscate_dynatrace_access_key("short")).is_equal_to("Invalid Token")
