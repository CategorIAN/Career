# Career Management & Job Search Automation

A Django application for managing my job search, tracking applications,
maintaining professional contacts, and publishing my portfolio. It uses
PostgreSQL and runs on Render.

Public visitors can open Resume, Experience, Projects, Education, and
Contact directly. The admin sidebar groups pages into four folders.

## Portfolio

Resume, Experience, Residencies, Projects, Education, and Contact.
These pages cover my professional background and work. Through Contact,
visitors can email me for help building or updating a website.

## Management

Features, Platforms, Companies, Skills, Search Terms, and Project
Management. This folder brings together project planning and the
reference data I maintain across the app.

## Networking

Professionals, Recruiters, Connections, Directions, and References.
These pages organize my professional contacts and networking activity.

## Finding Work

Job Search, Job Postings, Job Applications, Emails, and Freelancer Search.
I use these pages to prioritize searches, evaluate job fit with the OpenAI
API, track applications, and organize Gmail correspondence. The app also
generates tailored cover letters with PDF downloads.

### Freelancer Search

Search the Freelancer API by keyword and review project descriptions,
budgets, bid counts, and associated skills. The app caches and paginates
results and lets me save selected projects and their skills to PostgreSQL.

## Technology Stack

- Python, Django, and PostgreSQL
- HTML, CSS, and JavaScript
- Freelancer API, Gmail API, and OpenAI API
- Render