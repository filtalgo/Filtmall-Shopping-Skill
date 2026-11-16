"""Offline libphonenumber recognition; never fall back to format-specific regexes."""
import hashlib
from pathlib import Path
import sys
import unicodedata

WHEEL = Path(__file__).resolve().parents[1] / 'third_party/phonenumberslite-9.0.43-py2.py3-none-any.whl'
SHA256 = '986de6a460e9f67215b00d5ec68e7b909eb7f7830581e54269d413756033913e'
if not WHEEL.is_file() or hashlib.sha256(WHEEL.read_bytes()).hexdigest() != SHA256:
    raise RuntimeError('Bundled phone privacy component is missing or corrupt')
sys.path.insert(0, str(WHEEL))
import phonenumbers

if phonenumbers.__version__ != '9.0.43':
    raise RuntimeError('Unexpected phone privacy component version')


def contains_phone(value):
    normalized = ''.join(str(unicodedata.decimal(char)) if char.isdecimal() else char
                         for char in unicodedata.normalize('NFKC', value))
    return next(iter(phonenumbers.PhoneNumberMatcher(
        normalized, 'CN', leniency=phonenumbers.Leniency.POSSIBLE, max_tries=1000,
    )), None) is not None
