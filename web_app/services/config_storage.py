# -*- coding: utf-8 -*-
"""
SQLite-based storage for system configuration.
Provides a key-value store for all config files.
"""

import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class ConfigStorage:
    """SQLite key-value storage for system configuration."""

    # Config categories
    CATEGORY_PROMPTS = "prompts"
    CATEGORY_ACTIONS = "actions"
    CATEGORY_EMAIL = "email"
    CATEGORY_DEVICE = "device"
    CATEGORY_TIMING = "timing"

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = Path.home() / ".autoglm" / "chat.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.config_dir = Path.home() / ".autoglm"
        self._init_db()
        self._migrate_from_json()

    @contextmanager
    def _get_conn(self):
        """Get a database connection with context management."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """Initialize database schema."""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            # System config table (key-value store)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_config (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    category TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Create index for category
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_config_category ON system_config(category)")

            logger.info("System config database table initialized")

    def _migrate_from_json(self):
        """Migrate existing JSON config files to database."""
        migrated_marker = self.config_dir / ".config_migrated"
        
        if migrated_marker.exists():
            return

        migrated_count = 0

        # Migrate custom_prompts.json
        prompts_file = self.config_dir / "custom_prompts.json"
        if prompts_file.exists():
            try:
                data = json.loads(prompts_file.read_text(encoding="utf-8"))
                for key, value in data.items():
                    self.set(f"prompt_{key}", value, self.CATEGORY_PROMPTS)
                    migrated_count += 1
                logger.info(f"Migrated {len(data)} custom prompts from JSON")
            except Exception as e:
                logger.error(f"Failed to migrate prompts: {e}")

        # Migrate device_pins.json
        pins_file = self.config_dir / "device_pins.json"
        if pins_file.exists():
            try:
                data = json.loads(pins_file.read_text(encoding="utf-8"))
                # Store as single JSON blob
                self.set("device_pins", data, self.CATEGORY_DEVICE)
                migrated_count += 1
                logger.info(f"Migrated device pins from JSON")
            except Exception as e:
                logger.error(f"Failed to migrate device pins: {e}")

        # Migrate email_config.json
        email_file = self.config_dir / "email_config.json"
        if email_file.exists():
            try:
                data = json.loads(email_file.read_text(encoding="utf-8"))
                self.set("email_config", data, self.CATEGORY_EMAIL)
                migrated_count += 1
                logger.info(f"Migrated email config from JSON")
            except Exception as e:
                logger.error(f"Failed to migrate email config: {e}")

        # Migrate action_rules.json
        actions_file = self.config_dir / "action_rules.json"
        if actions_file.exists():
            try:
                data = json.loads(actions_file.read_text(encoding="utf-8"))
                self.set("action_rules", data, self.CATEGORY_ACTIONS)
                migrated_count += 1
                logger.info(f"Migrated action rules from JSON")
            except Exception as e:
                logger.error(f"Failed to migrate action rules: {e}")

        # Migrate custom_timing.json if exists
        timing_file = self.config_dir / "custom_timing.json"
        if timing_file.exists():
            try:
                data = json.loads(timing_file.read_text(encoding="utf-8"))
                self.set("custom_timing", data, self.CATEGORY_TIMING)
                migrated_count += 1
                logger.info(f"Migrated custom timing from JSON")
            except Exception as e:
                logger.error(f"Failed to migrate timing: {e}")

        # Migrate custom_apps.json if exists
        apps_file = self.config_dir / "custom_apps.json"
        if apps_file.exists():
            try:
                data = json.loads(apps_file.read_text(encoding="utf-8"))
                self.set("custom_apps", data, self.CATEGORY_ACTIONS)
                migrated_count += 1
                logger.info(f"Migrated custom apps from JSON")
            except Exception as e:
                logger.error(f"Failed to migrate apps: {e}")

        # Migrate project config files from ./config/ directory
        project_config_dir = Path(__file__).parent.parent.parent / "config"
        
        # Migrate screenshot_settings.json
        screenshot_file = project_config_dir / "screenshot_settings.json"
        if screenshot_file.exists() and not self.get("screenshot_settings"):
            try:
                data = json.loads(screenshot_file.read_text(encoding="utf-8"))
                self.set("screenshot_settings", data, "settings")
                migrated_count += 1
                logger.info(f"Migrated screenshot settings from JSON")
            except Exception as e:
                logger.error(f"Failed to migrate screenshot settings: {e}")

        # Migrate telegram_settings.json
        telegram_file = project_config_dir / "telegram_settings.json"
        if telegram_file.exists() and not self.get("telegram_config"):
            try:
                data = json.loads(telegram_file.read_text(encoding="utf-8"))
                self.set("telegram_config", data, "telegram")
                migrated_count += 1
                logger.info(f"Migrated telegram config from JSON")
            except Exception as e:
                logger.error(f"Failed to migrate telegram config: {e}")

        if migrated_count > 0:
            migrated_marker.write_text(datetime.now().isoformat())
            logger.info(f"Config migration completed: {migrated_count} items")

    # ========== Core Operations ==========

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value by key."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM system_config WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row['value'])
                except (json.JSONDecodeError, TypeError):
                    return row['value']
            return default

    def set(self, key: str, value: Any, category: str):
        """Set a config value."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            value_json = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else json.dumps(value)
            cursor.execute("""
                INSERT OR REPLACE INTO system_config (key, value, category, updated_at)
                VALUES (?, ?, ?, ?)
            """, (key, value_json, category, datetime.now().isoformat()))

    def delete(self, key: str) -> bool:
        """Delete a config value."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM system_config WHERE key = ?", (key,))
            return cursor.rowcount > 0

    def get_by_category(self, category: str) -> dict:
        """Get all config values in a category."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM system_config WHERE category = ?", (category,))
            
            result = {}
            for row in cursor.fetchall():
                try:
                    result[row['key']] = json.loads(row['value'])
                except (json.JSONDecodeError, TypeError):
                    result[row['key']] = row['value']
            return result

    def get_all(self) -> dict:
        """Get all config values grouped by category."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value, category FROM system_config")
            
            result = {}
            for row in cursor.fetchall():
                category = row['category']
                if category not in result:
                    result[category] = {}
                try:
                    result[category][row['key']] = json.loads(row['value'])
                except (json.JSONDecodeError, TypeError):
                    result[category][row['key']] = row['value']
            return result

    # ========== Convenience Methods ==========

    def get_device_pins(self) -> dict:
        """Get all device PINs."""
        return self.get("device_pins", {})

    def set_device_pin(self, device_id: str, pin: str):
        """Set a device PIN."""
        pins = self.get_device_pins()
        pins[device_id] = pin
        self.set("device_pins", pins, self.CATEGORY_DEVICE)

    def delete_device_pin(self, device_id: str):
        """Delete a device PIN."""
        pins = self.get_device_pins()
        if device_id in pins:
            del pins[device_id]
            self.set("device_pins", pins, self.CATEGORY_DEVICE)

    def get_email_config(self) -> dict:
        """Get email configuration."""
        return self.get("email_config", {})

    def set_email_config(self, config: dict):
        """Set email configuration."""
        self.set("email_config", config, self.CATEGORY_EMAIL)

    def get_action_rules(self) -> list:
        """Get action rules."""
        return self.get("action_rules", [])

    def set_action_rules(self, rules: list):
        """Set action rules."""
        self.set("action_rules", rules, self.CATEGORY_ACTIONS)

    def get_custom_apps(self) -> dict:
        """Get custom app mappings."""
        return self.get("custom_apps", {})

    def set_custom_apps(self, apps: dict):
        """Set custom app mappings."""
        self.set("custom_apps", apps, self.CATEGORY_ACTIONS)

    def get_custom_prompts(self) -> dict:
        """Get all custom prompts."""
        prompts = {}
        category_data = self.get_by_category(self.CATEGORY_PROMPTS)
        for key, value in category_data.items():
            if key.startswith("prompt_"):
                prompts[key[7:]] = value  # Remove 'prompt_' prefix
        return prompts

    def set_custom_prompt(self, key: str, content: str):
        """Set a custom prompt."""
        self.set(f"prompt_{key}", content, self.CATEGORY_PROMPTS)

    def delete_custom_prompt(self, key: str):
        """Delete a custom prompt."""
        self.delete(f"prompt_{key}")

    def get_custom_timing(self) -> dict:
        """Get custom timing settings."""
        return self.get("custom_timing", {})

    def set_custom_timing(self, timing: dict):
        """Set custom timing settings."""
        self.set("custom_timing", timing, self.CATEGORY_TIMING)


# Global instance
config_storage = ConfigStorage()
