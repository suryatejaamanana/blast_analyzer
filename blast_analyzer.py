import os
import ast
import networkx as nx

PROJECT_PATH = "project"

source_graph = nx.DiGraph()

def parse_file(filepath):
    with open(filepath, "r") as file:
        tree = ast.parse(file.read())

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            current_function = node.name
            source_graph.add_node(node.name, type="function")

            # Look for calls inside this function
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Name):
                        called_function = child.func.id
                        source_graph.add_edge(current_function, called_function)


        elif isinstance(node, ast.ClassDef):
            source_graph.add_node(node.name, type="class")

def scan_project():
    for root, dirs, files in os.walk(PROJECT_PATH):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                parse_file(filepath)

if __name__ == "__main__":
    scan_project()
    print("Nodes Found:")
    for node in source_graph.nodes(data=True):
        print("\nDependencies:")
        for edge in source_graph.edges():
            print(edge[0], "→", edge[1])
