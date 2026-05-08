import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
django.setup()
import pandas as pd
from app.models import Skill