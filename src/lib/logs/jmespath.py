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

import re

import jmespath
from jmespath import functions


class MappingCustomFunctions(functions.Functions):
    # pylint: disable=R0201

    @functions.signature({'types': ['string']},
                         {'types': ['string']},
                         {'types': ['string']})
    def _func_replace_regex(self, subject, regex, replacement):
        # replace java capture group sign ($) to python one (\)
        processed_replacement = re.sub(r'\$(\d+)+', '\\\\\\1', replacement)
        compiled_regex = re.compile(regex)
        result = compiled_regex.sub(processed_replacement, subject)
        return result

    @functions.signature({'types': []},
                         {'types': ['expref']},
                         {'types': ['expref']},
                         {'types': []})
    def _func_if(self, condition, if_true_expression, if_false_expression, node_scope):
        if condition:
            return if_true_expression.visit(if_true_expression.expression, node_scope)
        else:
            return if_false_expression.visit(if_false_expression.expression, node_scope)


JMESPATH_OPTIONS = jmespath.Options(custom_functions=MappingCustomFunctions())