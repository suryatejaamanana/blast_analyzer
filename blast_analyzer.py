import os
import ast
import networkx as nx
import json


PROJECT_PATH = "project"

source_graph = nx.DiGraph()

defined_functions = set()

def parse_file(filepath):
    module_name = filepath.replace(PROJECT_PATH + "/", "").replace(".py", "")

    # Add module as node
    source_graph.add_node(
        module_name,
        type="module"
    )

    with open(filepath, "r") as file:
        tree = ast.parse(file.read())

    for node in ast.walk(tree):

        # Add function nodes
        if isinstance(node, ast.FunctionDef):
            params = [arg.arg for arg in node.args.args]

            defined_functions.add(node.name)

            source_graph.add_node(
                node.name,
                type="function",
                module=module_name,
                params=params
            )

            # Module → Function containment
            source_graph.add_edge(module_name, node.name, relation="contains")


            # Detect calls inside function
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Name):
                        called_function = child.func.id
                        
                        if called_function in source_graph.nodes:
                            if source_graph.nodes[called_function].get("type") == "class":
                                source_graph.add_edge(
                                    node.name,
                                    called_function,
                                    relation="data_flow"
                                )
                            else:
                                source_graph.add_edge(
                                    node.name,
                                    called_function,
                                    relation="calls"
                                )
                        else:
                            source_graph.add_edge(
                                node.name,
                                called_function,
                                relation="external"
                            )


                        # If class → data flow
                        if called_function in source_graph.nodes:
                            if source_graph.nodes[called_function].get("type") == "class":
                                source_graph.add_edge(
                                    node.name,
                                    called_function,
                                    relation="data_flow"
                                )
                            else:
                                source_graph.add_edge(
                                    node.name,
                                    called_function,
                                    relation="calls"
                                )
                        else:
                            source_graph.add_edge(
                                node.name,
                                called_function,
                                relation="external"
                            )

        # Add class nodes
        elif isinstance(node, ast.ClassDef):
            source_graph.add_node(node.name, type="class", module=module_name)

            # Module → Class containment
            source_graph.add_edge(module_name, node.name, relation="contains")

def scan_project():
    for root, dirs, files in os.walk(PROJECT_PATH):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                parse_file(filepath)

def analyze_blast_radius(target):
    if target not in source_graph:
        #print("Target not found in graph.")
        return set()

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
    if target not in source_graph:
        return set()
        
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
        node_data = source_graph.nodes[node]
        if source_graph.nodes[node].get("type") == "module":
            continue

        node_data = source_graph.nodes[node]
        module = node_data.get("module", "unknown")
        layer = classify_layer(module)

        if node == target:
            reason = "Target of change"
            impact_type = "Root Change"

        elif node in forward:
                
             edge_data = source_graph.get_edge_data(target, node)
             relation = edge_data.get("relation") if edge_data else None
                
             if relation == "data_flow":
                impact_type = "Data Handling Impact"
                reason = f"Data structure dependency from '{target}'"
                
             elif relation == "calls":
                 impact_type = "Business Logic Impact"
                 reason = f"Function call dependency from '{target}'"
                
             else:
                 impact_type = "Downstream Impact"
                 reason = f"Indirect dependency from '{target}'"

        elif node in reverse:
                impact_type = "API / Caller Impact"
                reason = f"Calls or depends on '{target}'"

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

def detect_contract_break_by_intent(change_intent):
    change_type = change_intent["type"]
    description = change_intent["description"].lower()

    if change_type == "API_CHANGE":
        if "add required" in description:
            return True
        if "remove" in description:
            return True
        if "rename" in description:
            return True

    if change_type == "REFACTOR":
        if "rename" in description:
            return True

    return False

def detect_unknown_zones():
    unknown = []

    for node in source_graph.nodes():
        if node not in source_graph.nodes():
            continue

        # If function called but not defined in project
        if source_graph.out_degree(node) == 0 and node not in defined_functions:
            unknown.append(node)

    return unknown

def detect_external_calls():
        external = []
    
        for u, v, data in source_graph.edges(data=True):
            if data.get("relation") == "external":
                external.append(v)
    
        return list(set(external))

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
    if target not in source_graph:
        print("\n❌ ERROR: Target function not found in project.")
        print("Please enter a valid function or class name.")
        exit()
    
    change_type = change_intent["type"]

    forward = analyze_blast_radius(target)
    reverse = analyze_reverse_dependencies(target)

    if not forward and not reverse:
        print("\nNo impacted components found.")
        exit()

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

    external_calls = detect_external_calls()

    if external_calls:
        print("\n⚠ UNKNOWN IMPACT ZONES DETECTED:")
        for item in external_calls:
            print(" - External or dynamic dependency:", item)

    trace_paths = find_trace_paths(target)

    print("\nTraceability Paths:\n")

    for node, path in trace_paths.items():
        print(" → ".join(path))

    contract_break = detect_contract_break_by_intent(change_intent)

    if contract_break:
        print("\n⚠ CONTRACT BREAKING CHANGE DETECTED")
        print("Reason: API contract or public interface modified")

    print("\n=== Impact Summary ===")

    api_impacted = any(item["layer"] == "API Layer" for item in explanation_report)
    data_impacted = any(item["impact_type"] == "Data Handling Impact" for item in explanation_report)

    print("API Impacted:", api_impacted)
    print("Business Logic Impacted:", any(item["impact_type"] == "Business Logic Impact" for item in explanation_report))
    print("Data Layer Impacted:", data_impacted)
    print("External Dependencies Impacted:", bool(external_calls))
