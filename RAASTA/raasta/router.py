"""Model router: surf the free tiers without ever showing the student a 429.

Rules that keep a real product alive on free APIs:
  1. Every provider has a **quota ledger** in SQLite. We stop *before* the 429.
  2. Priority chain with automatic failover on 429 / 5xx / timeout.
  3. A response cache — a large share of tutoring turns repeat across students.
  4. Difficulty routing: routine turns to the fast cheap model, diagnosis and
     planning to the strongest free model available.
  5. Graceful degradation: no keys at all → the deterministic offline engine,
     which is fully functional (and is what the tests and demo use).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .config import Config, Provider
from .pedagogy import Assistance, ImpasseType, Move
from .simulated import SimulatedModel
from .store import Store


class RouterError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Offline engine — deterministic, zero-cost, always available
# ---------------------------------------------------------------------------

_OFFLINE_TEMPLATES: Dict[str, str] = {
    "prime": "Pehle sochiye: is sawal mein aapko kya nikalna hai? Jo bhi aata ho, likh dein.",
    "probe": "Aapki baari. Apna answer likh dein — ghalat bhi chalega, main dekh leta hoon.",
    "point": "Theek hai, yahan ek step mein masla hai. Kaunsa? Pehle apna step likho, phir main batata hoon.",
    "attach": "Ye usi cheez se juda hai jo aap pichhle dafa kar chuke hain. Yaad karke dekhein.",
    "strengthen": "Ab ek aur, thoda alag. Isi tareeqe se karein.",
    "test": "Ab bina madad ke. Sirf jawab likhein.",
    "motivate": "Chhota sa kadam aaj. Bas shuru karein.",
    "fallback": "Samajh nahi aaya? Koi baat nahi — poora sawal chhod kar pehla step likh dein.",
}


def offline_reply(role: str = "point", context: str = "") -> str:
    """Deterministic stand-in used when no API key is configured.

    It is intentionally *pedagogically correct* rather than smart: it asks a
    question and never gives an answer. The system degrades in capability, never
    in safety.
    """
    return _OFFLINE_TEMPLATES.get(role, _OFFLINE_TEMPLATES["fallback"])


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

@dataclass
class CallRecord:
    provider: str
    model: str
    ok: bool
    latency_ms: int
    cached: bool = False
    error: str = ""

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        state = "cached" if self.cached else ("ok" if self.ok else f"ERR:{self.error}")
        return f"<{self.provider}:{self.model} {self.latency_ms}ms {state}>"


class Router:
    def __init__(self, cfg: Optional[Config] = None, store: Optional[Store] = None):
        self.cfg = cfg or Config.from_env()
        self.store = store or Store(self.cfg.db_path)
        self._cooldown: Dict[str, float] = {}
        self.calls: List[CallRecord] = []

    # -- provider selection -------------------------------------------------
    def available_providers(self, tier: Optional[str] = None) -> List[Provider]:
        out = []
        for p in self.cfg.providers:
            if not p.available():
                continue
            if tier and p.tier != tier:
                continue
            if self._cooldown.get(p.name, 0) > time.time():
                continue
            if self.store.usage_today(p.name) >= p.rpd_limit:
                continue
            out.append(p)
        # strong capacity first for "strong", abundant first for "fast"
        out.sort(key=lambda p: -p.rpd_limit)
        return out

    def status(self) -> List[Dict[str, Any]]:
        rows = []
        for p in self.cfg.providers:
            used = self.store.usage_today(p.name)
            rows.append({
                "provider": p.name,
                "configured": bool(p.key()),
                "tier": p.tier,
                "used_today": used,
                "limit_today": p.rpd_limit,
                "remaining": max(0, p.rpd_limit - used),
                "cooling_down": self._cooldown.get(p.name, 0) > time.time(),
                "model": p.default_model,
            })
        return rows

    # -- cache --------------------------------------------------------------
    def _cache_key(self, model: str, messages: Sequence[Dict[str, str]],
                   temperature: float) -> str:
        blob = json.dumps({"m": model, "msgs": list(messages), "t": round(temperature, 2)},
                          ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    # -- core call ----------------------------------------------------------
    def complete(self, messages: List[Dict[str, str]],
                 tier: Optional[str] = None,
                 model: Optional[str] = None,
                 temperature: float = 0.4,
                 max_tokens: int = 400,
                 use_cache: bool = True,
                 system: Optional[str] = None) -> str:
        """Return assistant text. Falls back all the way down to the offline engine."""
        msgs: List[Dict[str, str]] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)

        if self.cfg.offline:
            self.calls.append(CallRecord("offline", "deterministic", True, 0))
            return offline_reply("fallback")

        candidates = self.available_providers(tier) or self.available_providers()
        if not candidates:
            self.calls.append(CallRecord("offline", "no-provider", True, 0))
            return offline_reply("fallback")

        for p in candidates:
            use_model = model or p.default_model
            key = self._cache_key(use_model, msgs, temperature)

            if self.cfg.cache_enabled and use_cache:
                hit = self.store.cache_get(key)
                if hit is not None:
                    self.calls.append(CallRecord(p.name, use_model, True, 0, cached=True))
                    return hit

            t0 = time.time()
            try:
                text = self._http_chat(p, use_model, msgs, temperature, max_tokens)
                dt = int((time.time() - t0) * 1000)
                self.store.bump_usage(p.name, ok=True)
                self.calls.append(CallRecord(p.name, use_model, True, dt))
                if self.cfg.cache_enabled and use_cache:
                    self.store.cache_put(key, text)
                return text
            except Exception as e:                      # noqa: BLE001 - failover by design
                dt = int((time.time() - t0) * 1000)
                self.store.bump_usage(p.name, ok=False)
                self.calls.append(CallRecord(p.name, use_model, False, dt,
                                             error=str(e)[:80]))
                self._cooldown[p.name] = time.time() + 300     # 5 min backoff
                continue

        self.calls.append(CallRecord("offline", "all-failed", True, 0))
        return offline_reply("fallback")

    def _http_chat(self, p: Provider, model: str, messages: List[Dict[str, str]],
                   temperature: float, max_tokens: int) -> str:
        """OpenAI-compatible chat completions over urllib (no SDK dependency)."""
        url = p.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if p.name == "openrouter":
            payload["extra_headers"] = {}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {p.key()}",
                **({"HTTP-Referer": "https://raasta.local",
                    "X-Title": "RAASTA"} if p.name == "openrouter" else {}),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.request_timeout_s) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RouterError(f"http {e.code}") from e
        except Exception as e:                           # noqa: BLE001
            raise RouterError(str(e)) from e

        try:
            return str(body["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as e:
            raise RouterError("malformed response") from e

    # -- convenience --------------------------------------------------------
    def tutor(self, contract: str, student_text: str,
              context: str = "", tier: Optional[str] = "fast") -> str:
        messages = [{"role": "user", "content": (
            f"{contract}\n\nCONTEXT:\n{context}\n\nSTUDENT SAID:\n{student_text}\n\n"
            f"Reply now, following the rules exactly:"
        )}]
        return self.complete(messages, tier=tier, temperature=0.5, max_tokens=350)

    def reply(self, contract: str, assistance: Assistance, move: Move,
              student_text: str, impasse_type: ImpasseType = ImpasseType.NONE,
              language: str = "roman_urdu", context: str = "",
              expected_answer: Optional[str] = None,
              playbook_block: str = "", tier: Optional[str] = "fast") -> str:
        """The single entry point the tutor uses.

        With a live API key this goes to a real model. Without one it goes to the
        simulated model, which is playbook-aware — so a playbook change still
        changes behaviour and the eval suite stays meaningful offline.
        """
        if self.cfg.offline or not self.available_providers(tier):
            return SimulatedModel(playbook_block, language).reply(
                assistance, move, impasse_type, context, expected_answer, student_text)
        messages = [{"role": "user", "content": (
            f"{contract}\n\nCONTEXT:\n{context}\n\nSTUDENT SAID:\n{student_text}\n\n"
            f"Reply now, following the rules exactly:")}]
        return self.complete(messages, tier=tier, temperature=0.5, max_tokens=350)

    def plan(self, contract: str, data: str, tier: str = "strong") -> str:
        messages = [{"role": "user", "content": f"{contract}\n\nDATA:\n{data}\n\nOutput:"}]
        return self.complete(messages, tier=tier, temperature=0.2, max_tokens=700)

    def stats(self) -> Dict[str, Any]:
        ok = sum(1 for c in self.calls if c.ok)
        return {
            "calls": len(self.calls),
            "ok": ok,
            "cached": sum(1 for c in self.calls if c.cached),
            "failed": len(self.calls) - ok,
            "avg_latency_ms": (sum(c.latency_ms for c in self.calls) / len(self.calls))
            if self.calls else 0,
        }
