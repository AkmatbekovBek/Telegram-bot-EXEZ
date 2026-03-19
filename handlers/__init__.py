# handlers/__init__.py

from .race import register_race_handlers

# В функции setup_handlers добавить:
def setup_handlers(dp):
    # ... другие регистрации
    register_race_handlers(dp)