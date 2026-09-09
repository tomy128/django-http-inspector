import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")

import django
from django.conf import settings
from django.test.utils import get_runner

django.setup()

TestRunner = get_runner(settings)
failures = TestRunner(verbosity=2).run_tests(["tests"])
sys.exit(bool(failures))
