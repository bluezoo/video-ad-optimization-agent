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

"""Ad Campaign Agent - Fashion retail campaign management with Veo 3.1 video generation."""

from __future__ import annotations

import random
import sys
import types


def _ensure_numpy_fallback() -> None:
    """Provide a lightweight stdlib numpy shim only when numpy is not installed."""
    try:
        import numpy  # noqa: F401

        return
    except ModuleNotFoundError:
        pass

    class _Array(list):
        def __mul__(self, other: float) -> _Array:
            return _Array(float(x) * float(other) for x in self)

        def __rmul__(self, other: float) -> _Array:
            return self.__mul__(other)

        def __truediv__(self, other: float) -> _Array:
            denom = float(other) if float(other) != 0.0 else 1.0
            return _Array(float(x) / denom for x in self)

        def sum(self) -> float:
            return float(sum(float(x) for x in self))

        def tolist(self) -> list:
            return list(self)

    class _Generator:
        def __init__(self, seed: int) -> None:
            self._rng = random.Random(seed)

        def uniform(self, low: float = 0.0, high: float = 1.0) -> float:
            return self._rng.uniform(low, high)

        def choice(self, a: int | list, size: int | None = None, replace: bool = True):
            population = list(range(int(a))) if isinstance(a, int) else list(a)
            if size is None:
                return self._rng.choice(population)
            k = min(int(size), len(population))
            if not replace:
                return _Array(self._rng.sample(population, k))
            return _Array(self._rng.choices(population, k=int(size)))

        def dirichlet(self, alpha: list[float]) -> _Array:
            samples = [self._rng.gammavariate(max(float(a), 0.001), 1.0) for a in alpha]
            total = sum(samples) or 1.0
            return _Array(s / total for s in samples)

    np_mod = types.ModuleType("numpy")
    rng_mod = types.ModuleType("numpy.random")
    rng_mod.Generator = _Generator  # type: ignore[attr-defined]
    rng_mod.default_rng = lambda seed=None: _Generator(int(seed or 0))  # type: ignore[attr-defined]
    np_mod.random = rng_mod  # type: ignore[attr-defined]
    np_mod.ndarray = _Array  # type: ignore[attr-defined]
    np_mod.zeros = lambda n: _Array(0.0 for _ in range(int(n)))  # type: ignore[attr-defined]
    np_mod.array = lambda seq: _Array(float(x) for x in seq)  # type: ignore[attr-defined]
    sys.modules["numpy"] = np_mod
    sys.modules["numpy.random"] = rng_mod


def _ensure_google_adk_fallback() -> None:
    """Provide lightweight shims for google.adk, google.genai, and PIL when not installed."""
    try:
        import PIL.Image  # noqa: F401
    except ModuleNotFoundError:
        pil_mod = types.ModuleType("PIL")
        pil_img_mod = types.ModuleType("PIL.Image")
        pil_mod.Image = pil_img_mod  # type: ignore[attr-defined]
        sys.modules.setdefault("PIL", pil_mod)
        sys.modules.setdefault("PIL.Image", pil_img_mod)

    try:
        import google.adk.agents  # noqa: F401
        import google.genai  # noqa: F401

        # In google-adk >= 2.0, Agent is the canonical class; ensure LlmAgent alias exists
        if hasattr(google.adk.agents, "Agent") and not hasattr(google.adk.agents, "LlmAgent"):
            google.adk.agents.LlmAgent = google.adk.agents.Agent  # type: ignore[attr-defined]
        elif hasattr(google.adk.agents, "LlmAgent") and not hasattr(google.adk.agents, "Agent"):
            google.adk.agents.Agent = google.adk.agents.LlmAgent  # type: ignore[attr-defined]
        return
    except ModuleNotFoundError:
        pass

    class _Agent:
        """ADK >= 2.0 Agent shim for environments where google-adk is not installed."""

        def __init__(
            self,
            *,
            model: str = "",
            name: str = "",
            description: str = "",
            instruction: str = "",
            tools: list | None = None,
            sub_agents: list | None = None,
            **kwargs,
        ) -> None:
            self.model = model
            self.name = name
            self.description = description
            self.instruction = instruction
            self.tools = list(tools or [])
            self.sub_agents = list(sub_agents or [])
            for k, v in kwargs.items():
                setattr(self, k, v)

    _LlmAgent = _Agent

    class _ToolContext:
        pass

    google_mod = sys.modules.get("google") or types.ModuleType("google")
    adk_mod = types.ModuleType("google.adk")
    agents_mod = types.ModuleType("google.adk.agents")
    tools_mod = types.ModuleType("google.adk.tools")
    genai_mod = types.ModuleType("google.genai")
    genai_types_mod = types.ModuleType("google.genai.types")
    genai_interactions_mod = types.ModuleType("google.genai.interactions")

    agents_mod.Agent = _Agent  # type: ignore[attr-defined]
    agents_mod.LlmAgent = _LlmAgent  # type: ignore[attr-defined]
    tools_mod.ToolContext = _ToolContext  # type: ignore[attr-defined]
    adk_mod.agents = agents_mod  # type: ignore[attr-defined]
    adk_mod.tools = tools_mod  # type: ignore[attr-defined]
    genai_mod.types = genai_types_mod  # type: ignore[attr-defined]
    genai_mod.interactions = genai_interactions_mod  # type: ignore[attr-defined]
    google_mod.adk = adk_mod  # type: ignore[attr-defined]
    google_mod.genai = genai_mod  # type: ignore[attr-defined]

    sys.modules.setdefault("google", google_mod)
    sys.modules.setdefault("google.adk", adk_mod)
    sys.modules.setdefault("google.adk.agents", agents_mod)
    sys.modules.setdefault("google.adk.tools", tools_mod)
    sys.modules.setdefault("google.genai", genai_mod)
    sys.modules.setdefault("google.genai.types", genai_types_mod)
    sys.modules.setdefault("google.genai.interactions", genai_interactions_mod)


_ensure_numpy_fallback()
_ensure_google_adk_fallback()

from . import agent as agent  # noqa: E402

