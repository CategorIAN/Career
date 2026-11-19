from django.db import migrations


OPTIMIZATION_LAB_SITE_MAP = """flowchart TD
    Visitor[Visitor] --> Home[Optimization Lab Home]
    Home --> SLS[Segmented Least Squares]
    Home --> SetCover[Greedy Set Cover]
    Home --> MaxFlow[Maximum Flow]
    Home --> TSP[Traveling Salesman]
    Visitor --> Admin[Django Admin]

    subgraph Navigation[Public navigation]
        Home --> SLS
        Home --> SetCover
        Home --> MaxFlow
        Home --> TSP
    end

    subgraph SegmentedLeastSquares[Segmented Least Squares visualization]
        SLS --> SLSInput[Add and edit ordered points]
        SLSInput --> SLSPenalty[Set segment penalty]
        SLSPenalty --> SLSSolve([Solve])
        SLSSolve --> SLSAPI[POST API segmented least squares solve]
        SLSAPI --> SLSValidate{Valid points and penalty?}
        SLSValidate -->|No| SLSError[Validation error]
        SLSValidate -->|Yes| SLSAlgorithm[Dynamic programming segmentation]
        SLSAlgorithm --> SLSResults[Segments, objective, errors, and timing]
    end

    subgraph GreedySetCover[Greedy Set Cover visualization]
        SetCover --> SetInput[Create subsets and elements]
        SetInput --> SetSolve([Solve])
        SetSolve --> SetAPI[POST API greedy set cover solve]
        SetAPI --> SetValidate{Valid collection?}
        SetValidate -->|No| SetError[Validation error]
        SetValidate -->|Yes| SetAlgorithm[Greedy set cover algorithm]
        SetAlgorithm --> SetResults[Selected subsets and element count]
    end

    subgraph MaximumFlow[Maximum Flow visualization]
        MaxFlow --> FlowInput[Create graph, capacities, source, and sink]
        FlowInput --> FlowStrategy[Choose BFS or DFS strategy]
        FlowStrategy --> FlowTrace([Trace Maximum Flow])
        FlowTrace --> FlowAPI[POST API maximum flow trace]
        FlowAPI --> FlowValidate{Valid graph and capacities?}
        FlowValidate -->|No| FlowError[Validation error]
        FlowValidate -->|Yes| FlowAlgorithm[Maximum flow trace algorithm]
        FlowAlgorithm --> FlowResults[Augmenting paths and flow results]
    end

    subgraph TravelingSalesman[Traveling Salesman visualization]
        TSP --> TSPInput[Create Euclidean city points]
        TSPInput --> TSPCheckpoint[Choose optional training checkpoint]
        TSPCheckpoint --> TSPSolve([Solve])
        TSPSolve --> TSPAPI[POST API traveling salesman solve]
        TSPAPI --> TSPValidate{Valid city count and coordinates?}
        TSPValidate -->|No| TSPError[Validation error]
        TSPValidate -->|Yes| TSPAlgorithm[Deep Q Learning and Held Karp comparison]
        TSPAlgorithm --> TSPResults[Tours, distances, and comparison results]
    end
"""


def populate_optimization_lab_site_map(apps, schema_editor):
    Project = apps.get_model("app", "Project")
    Project.objects.filter(
        title="Optimization Lab",
        github_url="https://github.com/CategorIAN/optimization-lab",
        mermaid_site_map="",
    ).update(mermaid_site_map=OPTIMIZATION_LAB_SITE_MAP)


class Migration(migrations.Migration):
    dependencies = [("app", "0071_expand_event_planner_site_map")]

    operations = [
        migrations.RunPython(populate_optimization_lab_site_map, migrations.RunPython.noop),
    ]
