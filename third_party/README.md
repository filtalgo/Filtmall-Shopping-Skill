# Offline phone recognition

- Component: phonenumberslite 9.0.43 (Python port of Google libphonenumber).
- Upstream: https://github.com/daviddrysdale/python-phonenumbers
- Distribution: https://pypi.org/project/phonenumberslite/9.0.43/
- Wheel: phonenumberslite-9.0.43-py2.py3-none-any.whl (unmodified pure Python wheel).
- SHA-256: 986de6a460e9f67215b00d5ec68e7b909eb7f7830581e54269d413756033913e
- License: Apache-2.0; full license in PHONENUMBERS-LICENSE and inside the wheel.

Included for offline import through Python zipimport. No pip installation, network lookup, or operating-system package is needed. Copy this directory together with scripts. Missing/corrupt components stop startup; phone checks must not silently downgrade. Upgrades must pin the version and hash and run the shared phone-privacy fixtures against the JavaScript producer and Python consumer.
