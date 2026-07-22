# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""ws09: agent instructions/descriptions must not carry hardcoded fashion framing."""


def test_no_fashion_retail_company_framing():
    import inspect

    import app.agent as agent_module
    source = inspect.getsource(agent_module)
    assert "fashion retail company" not in source

def test_app_description_not_fashion_specific():
    from app.config import APP_DESCRIPTION
    assert "fashion" not in APP_DESCRIPTION.lower()

def test_media_instruction_teaches_presentation_mode():
    from app.agent import MEDIA_AGENT_INSTRUCTION
    assert "presentation_mode" in MEDIA_AGENT_INSTRUCTION

def test_no_stale_product_counts():
    import inspect

    import app.agent as agent_module
    source = inspect.getsource(agent_module)
    assert "22 pre-loaded products" not in source
    assert "28 pre-loaded products" not in source
