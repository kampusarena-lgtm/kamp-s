"""Cafe session timing. No OS commands or miner processes live in this module."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class CyclePolicy:
    startup_wait_seconds: float = 60
    empty_wait_seconds: float = 60
    reboot_after_customer: bool = False


@dataclass(frozen=True)
class CycleDecision:
    allow_mining: bool
    request_reboot: bool
    phase: str
    remaining_seconds: float = 0


class CafeCycle:
    def __init__(self, policy, now):
        self.policy = policy
        self.started_at = now
        self.empty_since = None
        self.customer_seen = False
        self.reboot_requested = False

    def observe(self, occupied, interactive, idle_seconds, now):
        # 'occupied' must already have passed host/freshness/connection checks.
        if occupied is True:
            self.customer_seen = True
            self.empty_since = None
            self.reboot_requested = False
            return CycleDecision(False, False, 'customer_active')
        if (occupied is not False or not interactive or idle_seconds is None
                or not math.isfinite(idle_seconds) or idle_seconds < 0):
            self.empty_since = None
            self.reboot_requested = False
            return CycleDecision(False, False, 'session_unknown')
        if self.empty_since is None:
            self.empty_since = now
        if idle_seconds < self.policy.empty_wait_seconds:
            # New keyboard/mouse input cancels the departure/empty countdown.
            self.empty_since = max(self.empty_since, now - idle_seconds)
        deadline = max(self.started_at + self.policy.startup_wait_seconds,
                       self.empty_since + self.policy.empty_wait_seconds)
        if now < deadline:
            phase = 'departure_wait' if self.customer_seen else 'startup_wait'
            return CycleDecision(False, False, phase, deadline - now)
        if self.customer_seen and self.policy.reboot_after_customer:
            return CycleDecision(False, not self.reboot_requested, 'reboot_required')
        self.customer_seen = False
        return CycleDecision(True, False, 'empty_ready')

    def mark_reboot_requested(self):
        # Called only after the OS accepted the request; empty polls cannot repeat it.
        self.reboot_requested = True
