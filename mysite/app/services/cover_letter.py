from django.conf import settings
from openai import APIError, OpenAI

from app.models import Application
from app.services.candidate_background import build_candidate_background


class CoverLetterError(Exception):
    """Base error for cover-letter generation failures."""


class CoverLetterAPIError(CoverLetterError):
    """The OpenAI API could not generate a cover letter."""


class CoverLetterRefusalError(CoverLetterError):
    """OpenAI refused to generate the supplied cover letter."""


class CoverLetterParseError(CoverLetterError):
    """OpenAI did not return a complete, usable cover letter."""


def _job_posting_text(application):
    job_posting = application.job_posting
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


def generate_cover_letter(application: Application) -> str:
    """Generate a tailored cover letter from database-backed candidate context."""
    if not settings.OPENAI_API_KEY:
        raise CoverLetterAPIError("Set the OPENAI_API_KEY environment variable.")

    candidate_background = build_candidate_background()
    instructions = """
Write a concise, natural, professional cover letter specifically tailored to the
supplied job posting. Use only facts found in the candidate background and job
posting. Never invent skills, experience, accomplishments, responsibilities, or
qualifications. Select the candidate's strongest relevant professional
experience, projects, technical skills, and education for this position instead
of attempting to mention everything. Avoid generic or exaggerated enthusiasm.
Return only the cover-letter body, without commentary about the writing process.
Do not include a closing, "Sincerely," line, signature, or candidate name; the
application adds those elements when preparing the downloadable document.
""".strip()

    try:
        response = OpenAI(api_key=settings.OPENAI_API_KEY).responses.create(
            model=settings.OPENAI_JOB_EVALUATION_MODEL,
            input=[
                {"role": "system", "content": instructions},
                {
                    "role": "user",
                    "content": f"{candidate_background}\n\n{_job_posting_text(application)}",
                },
            ],
        )
    except APIError as error:
        raise CoverLetterAPIError("OpenAI failed to generate the cover letter.") from error

    if refusal := _response_refusal(response):
        raise CoverLetterRefusalError(f"OpenAI refused the cover letter: {refusal}")
    if getattr(response, "status", None) == "incomplete":
        raise CoverLetterParseError("OpenAI returned an incomplete cover letter.")

    cover_letter = (getattr(response, "output_text", "") or "").strip()
    if not cover_letter:
        raise CoverLetterParseError("OpenAI did not return a cover letter.")
    return cover_letter
