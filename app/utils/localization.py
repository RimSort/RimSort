import json
import os

# Cache for storing loaded translations
_translation_cache = {}

# Path to the locales directory
_locales_dir = os.path.join(os.path.dirname(__file__), 'locales')

def load_locale(language_code):
    """Loads the translations for the specified language code into the cache."""
    if language_code in _translation_cache:
        return _translation_cache[language_code]
    
    locale_path = os.path.join(_locales_dir, f"{language_code}.json")
    try:
        with open(locale_path, 'r', encoding='utf-8') as file:
            translations = json.load(file)
        _translation_cache[language_code] = translations
        return translations
    except FileNotFoundError:
        print(f"Localization file for {language_code} not found.")
        return {}

def translate(key, language_code):
    """Returns the localized string for the given key and language code.
       Falls back to English if the key is not found."""
    # Load the preferred language translations
    translations = load_locale(language_code)
    # Attempt to find the translation in the preferred language
    translation = translations.get(key)
    
    if translation:
        return translation
    else:
        # Fall back to English if the translation is not found
        print(f"Key '{key}' not found in {language_code}. Falling back to English.")
        english_translations = load_locale('en')
        return english_translations.get(key, key)

def invalidate_cache(language_code=None):
    """Invalidates the translation cache, either for a specific language or all."""
    if language_code:
        _translation_cache.pop(language_code, None)
    else:
        _translation_cache.clear()
