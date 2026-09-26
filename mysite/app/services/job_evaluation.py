from django.conf import settings
from openai import APIError, OpenAI
from pydantic import BaseModel, ValidationError

from app.models import JobPosting
from app.services.candidate_background import build_candidate_background


class JobEvaluation(BaseModel):
    apply: bool
    explanation: str


class JobEvaluationError(Exception):
    """Base error for JobPosting evaluation failures."""


class JobEvaluationAPIError(JobEvaluationError):
    """The OpenAI API could not complete the evaluation."""


class JobEvaluationRefusalError(JobEvaluationError):
    """OpenAI refused to evaluate the supplied content."""


class JobEvaluationParseError(JobEvaluationError):
    """OpenAI did not return a parsed JobEvaluation."""


def _job_posting_text(job_posting):
    lines = [
        "JOB POSTING",
        f"Title: {job_posting.title}",
        f"Company: {job_posting.company_name}",
    ]
    if job_posting.url:
        lines.append(f"URL: {job_posting.url}")
    if job_posting.description:
        lines.extend(["Description:", job_posting.description])
    return "\n".join(lines)


def _response_refusal(response):
    for output in getattr(response, "output", []):
        for content in getattr(output, "content", []):
            refusal = getattr(content, "refusal", None)
            if refusal:
                return refusal
    return None


def evaluate_job_posting(job_posting: JobPosting) -> JobEvaluation:
    """Evaluate a JobPosting against the current database-backed candidate background."""
    if not settings.OPENAI_API_KEY:
        raise JobEvaluationAPIError("Set the OPENAI_API_KEY environment variable.")

    candidate_background = build_candidate_background()
    instructions = """
Compare the supplied job posting with the candidate background and decide whether
the candidate should apply. Use only facts in the candidate background; do not
assume missing skills or experience. Distinguish required qualifications from
preferred qualifications, and do not require every preferred qualification.
Consider whether missing qualifications are essential and whether the role is
substantially more senior than the candidate's demonstrated experience.
Recommend applying when the candidate appears reasonably qualified and the role
is realistically attainable. In the explanation, identify the most important
matches and gaps.
""".strip()

    try:
        response = OpenAI(api_key=settings.OPENAI_API_KEY).responses.parse(
            model=settings.OPENAI_JOB_EVALUATION_MODEL,
            input=[
                {"role": "system", "content": instructions},
                {
                    "role": "user",
                    "content": f"{candidate_background}\n\n{_job_posting_text(job_posting)}",
                },
            ],
            text_format=JobEvaluation,
        )
    except APIError as error:
        raise JobEvaluationAPIError("OpenAI failed to evaluate the job posting.") from error
    except ValidationError as error:
        raise JobEvaluationParseError("OpenAI returned an invalid job evaluation.") from error

    if refusal := _response_refusal(response):
        raise JobEvaluationRefusalError(f"OpenAI refused the evaluation: {refusal}")
    if getattr(response, "status", None) == "incomplete":
        raise JobEvaluationParseError("OpenAI returned an incomplete evaluation.")
    if response.output_parsed is None:
        raise JobEvaluationParseError("OpenAI did not return a valid job evaluation.")

    return response.output_parsed
