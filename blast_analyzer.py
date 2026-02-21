import os
import ast
import networkx as nx
import json

PROJECT_PATH = "project"

source_graph = nx.DiGraph()


def parse_file(filepath):
    module_name = filepath.replace(PROJECT_PATH + "/", "").replace(".py", "")
    with open(filepath, "r") as file:
        tree = ast.parse(file.read())

    for node in ast.walk(tree):

        # Add function nodes
        if isinstance(node, ast.FunctionDef):
            params = [arg.arg for arg in node.args.args]

            source_graph.add_node(
                node.name,
                type="function",
                module=module_name,
                params=params
            )

            # Detect calls inside function
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Name):
                        called_function = child.func.id
                        source_graph.add_edge(node.name, called_function)

        # Add class nodes
        elif isinstance(node, ast.ClassDef):
            source_graph.add_node(node.name, type="class", module=module_name)

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

def classify_layer(module_path):
    if module_path.startswith("api"):
        return "API Layer"
    elif module_path.startswith("services"):
        return "Service Layer"
    elif module_path.startswith("models"):
        return "Data Model Layer"
    elif module_path.startswith("database"):
        return "Database Layer"
    elif module_path.startswith("utils"):
        return "Utility Layer"
    else:
        return "Unknown Layer"

def generate_explanation(target, forward, reverse):
    report = []

    for node in forward.union(reverse):
        if node not in source_graph:
            continue

        node_data = source_graph.nodes[node]
        module = node_data.get("module", "unknown")
        layer = classify_layer(module)

        if node == target:
            reason = "Target of change"
            impact_type = "Root Change"

        elif node in forward:
            reason = f"Depends on '{target}' directly or indirectly"
            impact_type = "Downstream Impact"

        elif node in reverse:
            reason = f"Calls or references '{target}'"
            impact_type = "Upstream Impact"

        else:
            reason = "Indirect relationship"
            impact_type = "Indirect Impact"

        report.append({
            "component": node,
            "layer": layer,
            "impact_type": impact_type,
            "reason": reason
        })

    return report

def export_json_report(report, filename="blast_report.json"):
    with open(filename, "w") as f:
        json.dump(report, f, indent=4)
    print(f"\nJSON report exported to {filename}")

def find_trace_paths(target):
    paths = {}

    for node in source_graph.nodes():
        try:
            for path in nx.all_simple_paths(source_graph, source=node, target=target):
                if len(path) > 1:
                    paths[node] = path
        except:
            continue

    return paths

def detect_contract_break(target):
    node_data = source_graph.nodes[target]
    params = node_data.get("params", [])

    callers = list(source_graph.predecessors(target))

    if len(params) > 2 and callers:
        return True

    return False

def get_change_intent():
    print("\nEnter Change Type:")
    print("1. API_CHANGE")
    print("2. VALIDATION_CHANGE")
    print("3. REFACTOR")

    choice = input("Select (1/2/3): ")

    change_types = {
        "1": "API_CHANGE",
        "2": "VALIDATION_CHANGE",
        "3": "REFACTOR"
    }

    change_type = change_types.get(choice)

    if not change_type:
        print("Invalid choice.")
        return None

    target = input("Enter target function name: ")
    description = input("Describe the change: ")

    return {
        "type": change_type,
        "target": target,
        "description": description
    }

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
print(" CHANGE INTENT INPUT")
print("==============================")

change_intent = get_change_intent()

if not change_intent:
    exit()

target = change_intent["target"]
change_type = change_intent["type"]

forward = analyze_blast_radius(target)
reverse = analyze_reverse_dependencies(target)

if forward and reverse:

    explanation_report = generate_explanation(target, forward, reverse)

    print("\n==============================")
    print(" BLAST RADIUS REPORT")
    print("==============================")

    print("\nChange Type:", change_type)
    print("Target:", target)
    print("Description:", change_intent["description"])

    print("\nDetailed Impact Report:\n")

    for item in explanation_report:
        print("----------------------------------")
        print("Component   :", item["component"])
        print("Layer       :", item["layer"])
        print("Impact Type :", item["impact_type"])
        print("Reason      :", item["reason"])

    total = len(explanation_report)

    print("\n----------------------------------")
    print("Total Impacted Components:", total)

    if change_type == "API_CHANGE":
        print("Contract Compatibility: CHECK REQUIRED")

    if total >= 6:
        print("Risk Level: HIGH")
    elif total >= 3:
        print("Risk Level: MEDIUM")
    else:
        print("Risk Level: LOW")

    export_json_report({
        "change_intent": change_intent,
        "impact": explanation_report
    })

    trace_paths = find_trace_paths(target)

    print("\nTraceability Paths:\n")

    for node, path in trace_paths.items():
        print(" → ".join(path))

    if detect_contract_break(target):
        print("\n⚠ Potential Contract Breaking Change Detected")

