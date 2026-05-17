from freelancersdk.session import Session
from freelancersdk.resources.projects import search_projects
import json
from freelancersdk.resources.projects.helpers import create_get_projects_project_details_object



if __name__ == '__main__':
    token = "IIHb1xdL1Cb1nwtLhfpyRx4I0yEYxr"
    session = Session(oauth_token=token)
    project_details = create_get_projects_project_details_object(
        full_description=True,
        jobs=True,
    )
    projects = search_projects(
        session,
        query="python",
        project_details=project_details,
        limit=1,
    )
    print(json.dumps(projects, indent=4))
