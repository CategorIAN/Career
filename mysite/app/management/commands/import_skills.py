from django.core.management.base import BaseCommand
import pandas as pd
from ...models import Skill


class Command(BaseCommand):

    def handle(self, *args, **kwargs):

        df = pd.read_csv("skills.csv")

        for _, row in df.iterrows():

            Skill.objects.update_or_create(
                name=row["Name"],
                defaults={
                    "type": row["Type"],
                    "rating": row["Rating"]
                }
            )

        self.stdout.write(self.style.SUCCESS("Skills imported"))