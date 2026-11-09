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


JOB_EVALUATION_INSTRUCTIONS = """
Evaluate whether this job is worth applying to by comparing the supplied job
posting with the supplied candidate background. The candidate background is the
authoritative source for education, work history, projects, skills, and
credentials. Return a recommendation based on realistic application value, not
whether the candidate already matches every listed preference.

Candidate assumptions:
- The candidate is willing to relocate anywhere in the United States for a
  suitable role and is open to remote, hybrid, and fully on-site work.
- Do not treat the candidate's current location, lack of local employment, or
  unconfirmed willingness to relocate or work on-site as a negative factor for
  a United States role.
- The candidate is open to different work arrangements and schedules. If a
  posting mentions unusually long hours, extensive travel, or an unusual
  schedule, identify it as a consideration, not as evidence the candidate is
  unwilling or unable to meet it.
- The candidate is interested in software engineering, data engineering, and
  related technical work. Evaluate actual responsibilities, not just title;
  related programming, backend, API, ETL, and data-systems roles can be good
  fits when responsibilities align.

Interpret the posting accurately:
- Separate explicit hiring requirements, stated job responsibilities, inferred
  employer expectations, and candidate evidence. Explicit requirements are
  qualifications or conditions the posting says a candidate must satisfy and
  receive substantial weight.
- Responsibilities describe the work the successful candidate will do. They
  are relevant to whether the candidate can plausibly perform the role, but do
  not automatically require prior professional performance of that exact task.
  Do not convert responsibilities into mandatory prior experience without
  supporting language in the posting.
- Clearly label inferences from a role title, responsibility, or company
  context as competitiveness considerations, not explicit requirements. Do not
  invent years-of-experience thresholds, technologies, credentials, or
  architectural requirements the posting does not establish.
- A senior or founding-engineer title alone does not establish a minimum number
  of years or prior founding/senior experience. Similarly, a responsibility to
  architect or scale a platform does not by itself require prior large-scale
  distributed-systems experience.
- Consider the difficulty and independence the responsibilities suggest. A
  demanding role can still be unsuitable when the responsibilities are
  substantially beyond a plausible transition from the demonstrated background,
  even without explicit minimum qualifications. Distinguish that competitiveness
  concern from a confirmed failure to meet a stated requirement.

Assess qualifications carefully:
- Clearly distinguish confirmed matches, confirmed gaps, and unknown or
  unverified information. A confirmed gap requires evidence that the candidate
  lacks a qualification or has substantially insufficient experience for an
  essential responsibility. An absent qualification in the supplied background
  is unverified, not a confirmed deficiency.
- Use precise wording for unverified qualifications, such as "not demonstrated
  in the supplied background" or "the candidate's experience with this
  technology is not established." Do not describe undocumented experience as
  absent, limited, or deficient.
- Treat professional work, internships, freelance development, independently
  developed and deployed applications, graduate projects, API integrations,
  database design, automation, and data engineering work as relevant evidence
  of transferable experience. Evaluate their scope and relevance fairly without
  equating projects to unsupported large-scale production experience.
- Recognize relevant partial experience. For example, a Django application
  deployed on Render demonstrates application-deployment experience, even if it
  does not establish advanced cloud infrastructure or large-scale distributed
  systems experience. Evaluate the demonstrated scope rather than requiring
  exact terminology matches.
- Give required qualifications more weight than preferred qualifications.
  Missing preferred technologies or nonessential tools are manageable gaps when
  supported transferable experience exists; they are not automatic reasons to
  reject a role.
- Do not automatically reject a role solely because it requests more experience
  or has a senior title. Instead assess whether essential responsibilities,
  architecture, scaling, leadership, or domain requirements are substantially
  beyond the demonstrated background.
- Discuss work authorization, visa sponsorship, security clearances, licensing,
  certifications, or similar eligibility only when the posting explicitly makes
  the requirement material. If such an explicit requirement is not addressed
  by the candidate background, identify it as unknown; do not assume the
  candidate meets or fails it. Do not introduce generic or hypothetical
  eligibility concerns.

Recommend applying when there is reasonable alignment and a plausible path to
performing the role, even with imperfect qualifications. Recommend against
applying only when substantial, consequential mismatches make the application
unlikely to be worthwhile. The explanation must be concise, specific, and
evidence-based: identify the strongest relevant qualifications, the most
consequential gaps, and the principal reasons for the recommendation. When
relevant, distinguish unmet or unverified explicit requirements from challenging
responsibilities and clearly identified inferred expectations. Mention unknowns
only when an explicit, material job requirement could change the recommendation.
Avoid speculative concerns, generic disclaimers, and invented personal
preferences, qualifications, experience, or concerns.
""".strip()


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
    try:
        response = OpenAI(api_key=settings.OPENAI_API_KEY).responses.parse(
            model=settings.OPENAI_JOB_EVALUATION_MODEL,
            input=[
                {"role": "system", "content": JOB_EVALUATION_INSTRUCTIONS},
                {
                    "role": "user",
                    "content": f"{candidate_background}\n\n{_job_posting_text(job_posting)}",
                },
            ],
            text_format=JobEvaluation,
        )
    except APIError as error:
        raise JobEvaluationAPIError(
            f"OpenAI failed to evaluate the job posting: "
            f"{type(error).__name__}: {error}"
        ) from error
    except ValidationError as error:
        raise JobEvaluationParseError("OpenAI returned an invalid job evaluation.") from error

    if refusal := _response_refusal(response):
        raise JobEvaluationRefusalError(f"OpenAI refused the evaluation: {refusal}")
    if getattr(response, "status", None) == "incomplete":
        raise JobEvaluationParseError("OpenAI returned an incomplete evaluation.")
    if response.output_parsed is None:
        raise JobEvaluationParseError("OpenAI did not return a valid job evaluation.")

    return response.output_parsed
