import json
from pathlib import Path

from virtual_tcu import paths
from virtual_tcu.telemetry.car_key import storage_key

# Persisted estimator-data contract. This is intentionally independent from
# the application version.
PROFILE_SCHEMA_VERSION = 1


class ProfileStore:
    """Versioned, atomic per-car profile storage with flat-file migration."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else paths.profiles_file()
        self.data: dict[str, dict] = {}
        self._active_key: str | None = None
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.save()
            return
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[Profiles] load failed, starting fresh: {exc}")
            self._archive("corrupt")
            self.save()
            return

        if isinstance(stored, dict) and stored.get("version") == PROFILE_SCHEMA_VERSION:
            profiles = stored.get("profiles")
            if isinstance(profiles, dict):
                self.data = {
                    str(key): value for key, value in profiles.items() if isinstance(value, dict)
                }
                active = stored.get("active_profile")
                self._active_key = (
                    str(active) if isinstance(active, str) and active in self.data else None
                )
                return

        # Versions through 13.9.4 stored the profiles directly at the root.
        # Migrate them in place instead of forcing every car to relearn.
        if isinstance(stored, dict) and all(isinstance(value, dict) for value in stored.values()):
            self.data = {str(key): value for key, value in stored.items()}
            self._active_key = None
            self.save()
            return

        print("[Profiles] incompatible schema, archiving and starting fresh")
        self._archive("incompatible")
        self.data = {}
        self._active_key = None
        self.save()

    def _archive(self, reason: str) -> None:
        if not self.path.exists():
            return
        backup = self.path.with_name(f"{self.path.name}.{reason}.bak")
        suffix = 1
        while backup.exists():
            backup = self.path.with_name(f"{self.path.name}.{reason}.{suffix}.bak")
            suffix += 1
        try:
            self.path.replace(backup)
        except Exception as exc:
            print(f"[Profiles] archive failed: {exc}")

    def save(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": PROFILE_SCHEMA_VERSION,
                "active_profile": self._active_key,
                "profiles": self.data,
            }
            temp_path = self.path.with_name(f"{self.path.name}.tmp")
            temp_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            temp_path.replace(self.path)
            return True
        except Exception as exc:
            print(f"[Profiles] save failed: {exc}")
            return False

    @staticmethod
    def _legacy_key(car_key: tuple[int, ...]) -> str | None:
        if len(car_key) >= 3:
            return f"{car_key[0]}_{car_key[1]}_{car_key[2]}"
        return None

    def get(self, car_key: tuple[int, ...]) -> dict | None:
        key = storage_key(car_key)
        if key in self.data:
            return self.data[key]
        legacy = self._legacy_key(car_key)
        if legacy and legacy in self.data:
            return self.data[legacy]
        return None

    def mark_active(self, car_key: tuple[int, ...]) -> None:
        key = storage_key(car_key)
        if key not in self.data or self._active_key == key:
            return
        previous = self._active_key
        self._active_key = key
        if not self.save():
            self._active_key = previous

    def set(self, car_key: tuple[int, ...], profile: dict) -> bool:
        key = storage_key(car_key)
        previous = self.data.get(key)
        previous_active = self._active_key
        self.data[key] = profile
        self._active_key = key
        if self.save():
            return True
        if previous is None:
            self.data.pop(key, None)
        else:
            self.data[key] = previous
        self._active_key = previous_active
        return False

    def delete(self, car_key: tuple[int, ...]) -> bool:
        key = storage_key(car_key)
        previous = self.data.pop(key, None)
        if previous is None:
            return False
        previous_active = self._active_key
        if self._active_key == key:
            self._active_key = None
        if self.save():
            return True
        self.data[key] = previous
        self._active_key = previous_active
        return False
