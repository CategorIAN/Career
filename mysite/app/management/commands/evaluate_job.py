from django.core.management.base import BaseCommand, CommandError

from app.models import JobPosting
from app.services.job_evaluation import JobEvaluationError, evaluate_job_posting


class Command(BaseCommand):
    help = "Evaluate a JobPosting against the candidate background using OpenAI."

    def add_arguments(self, parser):
        parser.add_argument("job_posting_id", type=int)

    def handle(self, *args, **options):
        job_posting_id = options["job_posting_id"]
        try:
            job_posting = JobPosting.objects.get(pk=job_posting_id)
        except JobPosting.DoesNotExist as error:
            raise CommandError(f"Job posting with ID {job_posting_id} does not exist.") from error

        self.stdout.write(f"Job Posting: {job_posting.title} — {job_posting.company_name}")
        try:
            evaluation = evaluate_job_posting(job_posting)
        except JobEvaluationError as error:
            raise CommandError(str(error)) from error

        self.stdout.write(f"Apply: {'Yes' if evaluation.apply else 'No'}")
        self.stdout.write(evaluation.explanation)
