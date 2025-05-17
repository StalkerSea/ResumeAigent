import json
from pathlib import Path

class LocalizationManager:
    _instance = None
    _initialized = False

    LANGUAGE_CODES = {
        "English": "en",
        "Español": "es",
        "Français": "fr",
        "Deutsch": "de",
        "Italiano": "it"
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.locales_dir = Path(__file__).parent.parent
            self.settings_file = self.locales_dir / "settings.json"
            self.locales_dir = self.locales_dir / "localizations"
            self.settings = self._load_settings()
            self.strings = self._load_locale(self.settings.get("language", "en"))
            self._initialized = True

    def _load_settings(self):
        try:
            with open(self.settings_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"language": "en"}

    def _load_locale(self, language: str):
        locale_file = self.locales_dir / f"{language}.json"
        try:
            with open(locale_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def get_string(self, key: str) -> str:
        """
        Get a localized string using dot notation or path-like syntax for nested keys.
        
        Args:
            key (str): Key path (e.g., "settings.language" or "settings/language")
            
        Returns:
            str: The localized string or the key itself if not found
        """
        # Convert path-like syntax to dot notation
        key_path = key.replace('/', '.')
        keys = key_path.split('.')
        
        # Navigate through nested dictionaries
        current = self.strings
        for k in keys:
            if isinstance(current, dict):
                current = current.get(k)
                if current is None:
                    return key
            else:
                return key
        
        return current if current is not None else key

    def change_language(self, language: str):
        """
        Change the current language setting.
        
        Args:
            language (str): The display name of the language (e.g., "English")
        """
        # Convert display language to code
        language_code = self.LANGUAGE_CODES.get(language, language)
        
        # If input was already a code, validate it exists
        if language not in self.LANGUAGE_CODES.values() and language_code not in self.LANGUAGE_CODES.values():
            raise ValueError(f"Unsupported language: {language}")
        
        self.settings["language"] = language_code
        self.strings = self._load_locale(language_code)
        
        with open(self.settings_file, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=4)
            
        return self.get_string("settings/language/changed")