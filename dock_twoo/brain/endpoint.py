"""Audio-duration based turn boundaries shared by wake and conversation capture."""

from dataclasses import dataclass


@dataclass
class TurnEndpoint:
    silence_required: float = 1.5
    idle_timeout: float = 10.0
    max_duration: float = 120.0
    elapsed: float = 0.0
    speech: float = 0.0
    silence: float = 0.0

    def feed(self, seconds: float, voiced: bool) -> None:
        self.elapsed += seconds
        if voiced:
            self.speech += seconds
            self.silence = 0.0
        elif self.speech:
            self.silence += seconds

    @property
    def complete(self) -> bool:
        return self.speech > 0 and self.silence + 1e-6 >= self.silence_required

    @property
    def idle_expired(self) -> bool:
        return self.speech == 0 and self.elapsed + 1e-6 >= self.idle_timeout

    @property
    def overlong(self) -> bool:
        return self.elapsed > self.max_duration
