import os
import ast
import networkx as nx

PROJECT_PATH = "project"

source_graph = nx.DiGraph()


def parse_file(filepath):
    with open(filepath, "r") as file:
        tree = ast.parse(file.read())

    for node in ast.walk(tree):

        # Add function nodes
        if isinstance(node, ast.FunctionDef):
            source_graph.add_node(node.name, type="function")

            # Detect calls inside function
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Name):
                        called_function = child.func.id
                        source_graph.add_edge(node.name, called_function)

        # Add class nodes
        elif isinstance(node, ast.ClassDef):
            source_graph.add_node(node.name, type="class")


def scan_project():
    for root, dirs, files in os.walk(PROJECT_PATH):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                parse_file(filepath)

def analyze_blast_radius(target):
    if target not in source_graph:
        print("Target not found in graph.")
        return None

    impacted = set()
    queue = [target]

    # Traverse forward dependencies (who it affects)
    while queue:
        current = queue.pop(0)
        if current not in impacted:
            impacted.add(current)
            neighbors = list(source_graph.successors(current))
            queue.extend(neighbors)

    return impacted

def analyze_reverse_dependencies(target):
    impacted = set()
    queue = [target]

    while queue:
        current = queue.pop(0)
        if current not in impacted:
            impacted.add(current)
            parents = list(source_graph.predecessors(current))
            queue.extend(parents)

    return impacted



if __name__ == "__main__":

    scan_project()

    print("\n==============================")
    print(" SOURCE GRAPH (Nodes)")
    print("==============================")

    for node in source_graph.nodes(data=True):
        print(node)

    print("\n==============================")
    print(" DEPENDENCY GRAPH (Edges)")
    print("==============================")

    for edge in source_graph.edges():
        print(edge[0], "→", edge[1])

    print("\n==============================")
    print(" BLAST RADIUS ANALYSIS")
    print("==============================")

    target = input("\nEnter function name to analyze: ")

    forward = analyze_blast_radius(target)
    reverse = analyze_reverse_dependencies(target)

    impacted_nodes = forward.union(reverse)

    if impacted_nodes:
        print("\nImpacted Components:")
        for node in impacted_nodes:
            print(" -", node)

        print("\nImpact Summary:")
        count = len(impacted_nodes)

        if count >= 5:
            print(" Risk Level: HIGH")
        elif count >= 3:
            print(" Risk Level: MEDIUM")
        else:
            print(" Risk Level: LOW")

