# Freelancer Project Search & Data Pipeline

A Django application for searching, processing, and storing freelance project data from the Freelancer API.

The application retrieves project listings based on user-defined search terms, transforms the nested API responses into application-friendly data, and allows selected projects and their associated skills to be stored in a relational database. API responses are cached to reduce redundant requests and limit unnecessary calls to the Freelancer API.

## Features

* Search Freelancer projects using user-defined search terms
* Retrieve project data from the Freelancer API
* Cache search results to reduce redundant API requests
* Paginate project search results
* View full project descriptions in a modal
* Show or hide the skills associated with each project
* Display project type, budget, bid count, and status
* Identify projects that have already been saved
* Selectively save projects and their associated skills to the database

## Technology Stack

* Python
* Django
* PostgreSQL
* HTML
* CSS
* JavaScript
* Freelancer API

## Architecture

The application is organized into four primary layers:

### Presentation Layer

* Django templates
* HTML forms
* JavaScript

### Application Layer

* Django views
* Helper functions
* Pagination

### Integration Layer

* Freelancer API
* Django cache

### Persistence Layer

* Django ORM
* `FreelancerProject`
* `FreelancerSkill`

## Workflow

1. The user enters a search query.
2. Django receives and normalizes the query.
3. The application checks for previously cached results.
4. If necessary, the application queries the Freelancer API.
5. The API returns project data.
6. The application transforms the returned JSON into application-friendly data.
7. Django paginates and displays the search results.
8. The application checks which displayed projects are already stored in the database.
9. The user can select a project to save.
10. The project and its associated Freelancer skills are stored in the database.

## API Caching

Search queries are normalized before being used to generate cache keys. When a search is performed, the application checks Django's cache before contacting the Freelancer API.

If cached results exist, they are returned immediately. Otherwise, the application makes a Freelancer API request and stores the returned projects in the cache for subsequent searches.

This reduces redundant API calls and helps manage Freelancer API request limits.

## Database Persistence

Projects are not automatically stored simply because they appear in search results. The user can review the results and choose which projects to save.

When a project is selected, the application retrieves its complete data from the cached search results rather than making another Freelancer API request.

Projects are saved using Django's `update_or_create`, with the Freelancer project ID used to identify existing records. This prevents duplicate project records when the same project is saved more than once.

The project's Freelancer skills are also created or updated and associated with the project through a many-to-many relationship.

## Data Model

The primary Freelancer-related models are:

### `FreelancerProject`

Stores project information retrieved from the Freelancer API, including project details, budget information, bid information, status, and other project metadata.

### `FreelancerSkill`

Stores the skills associated with Freelancer projects.

A `FreelancerProject` can have multiple `FreelancerSkill` records, and a skill can be associated with multiple projects.

## Project Status

### Implemented

* Manual Freelancer project search
* API integration
* Search-result caching
* Pagination
* Project description modal
* Project skill display
* Database persistence for selected projects
* Freelancer skill persistence
* Many-to-many project/skill relationships

### Planned

* Scheduled ETL searches with Airflow
* Historical project analytics
* Skill trend dashboards
* Automated testing

## Purpose

The long-term goal of the project is to build a searchable database of freelance opportunities that reduces repeated API requests, supports project analysis, and helps identify the skills and project types most relevant to career development.
