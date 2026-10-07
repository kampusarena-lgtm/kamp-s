"""Mining safety policy; this module never starts a miner."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Policy:
    idle_seconds: int = 60
    session_max_age_seconds: int = 10
    stop_temperature_c: float = 70
    resume_temperature_c: float = 60
    cooldown_seconds: int = 900


@dataclass(frozen=True)
class Observation:
    occupied: bool | None
    session_age_seconds: float | None
    idle_seconds: float | None
    temperatures_c: tuple[float, ...]
    emergency_stop: bool = False
    interactive_session_ok: bool = False


class Controller:
    def __init__(self, policy: Policy):
        self.policy = policy
        self.hot_until = 0.0
        self.thermal_latched = False

    def decide(self, obs: Observation, monotonic_now: float) -> tuple[bool, str]:
        p = self.policy
        temps_valid = bool(obs.temperatures_c) and all(
            math.isfinite(t) and 0 <= t <= 120 for t in obs.temperatures_c
        )
        if temps_valid and max(obs.temperatures_c) >= p.stop_temperature_c:
            self.hot_until = monotonic_now + p.cooldown_seconds
            self.thermal_latched = True
        if obs.emergency_stop:
            return False, "Acil durdurma"
        if not obs.interactive_session_ok:
            return False, "Aktif yerel kullanici oturumu dogrulanamadi"
        if obs.occupied is not False:
            return False, "Musteri oturumu aktif veya bilinmiyor"
        age = obs.session_age_seconds
        if age is None or not math.isfinite(age) or not 0 <= age <= p.session_max_age_seconds:
            return False, "Kafe oturum bilgisi eski veya gecersiz"
        idle = obs.idle_seconds
        if idle is None or not math.isfinite(idle) or idle < p.idle_seconds:
            return False, "Klavye/fare bosluk suresi yetersiz veya bilinmiyor"
        if not temps_valid:
            return False, "GPU sicakligi okunamadi"
        if self.thermal_latched:
            if monotonic_now < self.hot_until or max(obs.temperatures_c) > p.resume_temperature_c:
                return False, "Sicaklik durdurmasi / soguma bekleniyor"
            self.thermal_latched = False
        return True, "Oturum bos, giris yok, sicaklik uygun"
