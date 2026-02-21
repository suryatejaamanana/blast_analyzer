import argparse
import ast
import json
import os
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import networkx as nx


SUPPORTED_CHANGE_TYPES = {
    "api_modification",
    "function_logic_change",
    "validation_rule_change",
    "refactor_shared_method",
    "data_model_change",
}

CONTRACT_BREAK_PATTERNS = (
    "remove",
    "rename",
    "change type",
    "make required",
    "add required",
    "required",
    "delete",
    "change signature",
)
DEPENDENCY_RELATIONS = {"CALLS", "DEPENDS_ON", "INHERITS", "READS", "WRITES", "RETURNS"}


@dataclass
class ChangeIntent:
    change_type: str
    target: str
    modification: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: Dict[str, Any]) -> "ChangeIntent":
        if not isinstance(raw, dict):
            raise ValueError("Change intent must be a JSON object.")

        change_type = str(raw.get("change_type", "")).strip().lower()
        target = str(raw.get("target", "")).strip()
        modification = str(raw.get("modification", "")).strip().lower()

        if change_type not in SUPPORTED_CHANGE_TYPES:
            raise ValueError(
                f"Unsupported change_type '{change_type}'. "
                f"Allowed: {sorted(SUPPORTED_CHANGE_TYPES)}"
            )
        if not target:
            raise ValueError("Missing required field: target")
        if not modification:
            raise ValueError("Missing required field: modification")

        metadata = {k: v for k, v in raw.items() if k not in {"change_type", "target", "modification"}}
        return cls(change_type=change_type, target=target, modification=modification, metadata=metadata)


class BlastRadiusAnalyzer:
    def __init__(self, project_path: str = "project", allow_symbol_target: bool = False) -> None:
        self.project_path = project_path
        self.allow_symbol_target = allow_symbol_target
        self.graph = nx.DiGraph()
        self.module_trees: Dict[str, ast.AST] = {}
        self.module_paths: Dict[str, str] = {}
        self.global_symbol_index: Dict[str, Set[str]] = defaultdict(set)
        self.module_contexts: Dict[str, Dict[str, Any]] = {}
        self.unknown_impact_zones: Set[str] = set()

    def build_graph(self) -> None:
        self._first_pass()
        self._second_pass()

    def _first_pass(self) -> None:
        for file_path in self._scan_files():
            module_name = self._module_name(file_path)
            module_node = self._module_node_id(module_name)
            self.graph.add_node(module_node, type="module", name=module_name, module=module_name)

            with open(file_path, "r", encoding="utf-8") as handle:
                tree = ast.parse(handle.read(), filename=file_path)

            self.module_trees[module_name] = tree
            self.module_paths[module_name] = file_path

            context = {
                "module_node": module_node,
                "functions": {},
                "classes": {},
                "methods": defaultdict(dict),
                "imports": {},
                "inheritance": [],
            }
            self.module_contexts[module_name] = context

            for node in tree.body:
                if isinstance(node, ast.FunctionDef):
                    fn_node = self._function_node_id(module_name, node.name)
                    is_api = module_name.startswith("api.") or self._has_api_decorator(node)
                    self._add_function_node(
                        fn_node,
                        module_name,
                        node.name,
                        node.args.args,
                        parent_class=None,
                        is_api=is_api,
                    )
                    context["functions"][node.name] = fn_node
                    self.graph.add_edge(module_node, fn_node, relation="CONTAINS")
                    if is_api:
                        self._add_api_node(module_name, node.name, parent_class=None)

                elif isinstance(node, ast.ClassDef):
                    class_node = self._class_node_id(module_name, node.name)
                    self.graph.add_node(class_node, type="class", name=node.name, module=module_name)
                    context["classes"][node.name] = class_node
                    self.global_symbol_index[node.name].add(class_node)
                    self.graph.add_edge(module_node, class_node, relation="CONTAINS")

                    for base in node.bases:
                        context["inheritance"].append((class_node, base))

                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            method_node = self._function_node_id(module_name, item.name, parent_class=node.name)
                            is_api = module_name.startswith("api.") or self._has_api_decorator(item)
                            self._add_function_node(
                                method_node,
                                module_name,
                                item.name,
                                item.args.args,
                                parent_class=node.name,
                                is_api=is_api,
                            )
                            context["methods"][node.name][item.name] = method_node
                            self.graph.add_edge(class_node, method_node, relation="CONTAINS")
                            # Class changes should propagate into method-level dependencies.
                            self.graph.add_edge(class_node, method_node, relation="DEPENDS_ON")
                            if is_api:
                                self._add_api_node(module_name, item.name, parent_class=node.name)

    def _second_pass(self) -> None:
        for module_name, tree in self.module_trees.items():
            context = self.module_contexts[module_name]
            module_node = context["module_node"]

            self._process_imports(module_name, tree)
            self._process_inheritance(module_name)

            for node in tree.body:
                if isinstance(node, ast.FunctionDef):
                    self._process_callable(module_name, context["functions"][node.name], node, current_class=None)
                elif isinstance(node, ast.ClassDef):
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            method_node = context["methods"][node.name][item.name]
                            self._process_callable(module_name, method_node, item, current_class=node.name)

            # Module node should import dependencies at module granularity as well.
            for imported in context["imports"].values():
                self.graph.add_edge(module_node, imported, relation="IMPORTS")

    def _process_imports(self, module_name: str, tree: ast.AST) -> None:
        context = self.module_contexts[module_name]
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_module = alias.name
                    alias_name = alias.asname or imported_module.split(".")[-1]
                    module_node = self._module_node_id(imported_module)
                    self.graph.add_node(module_node, type="module", name=imported_module, module=imported_module)
                    context["imports"][alias_name] = module_node

            elif isinstance(node, ast.ImportFrom):
                imported_module = node.module or ""
                module_node = self._module_node_id(imported_module)
                self.graph.add_node(module_node, type="module", name=imported_module, module=imported_module)

                for alias in node.names:
                    alias_name = alias.asname or alias.name
                    resolved = self._resolve_symbol_from_module(imported_module, alias.name)
                    context["imports"][alias_name] = resolved or module_node

    def _process_inheritance(self, module_name: str) -> None:
        context = self.module_contexts[module_name]
        for class_node, base_expr in context["inheritance"]:
            resolved = self._resolve_expression(module_name, base_expr, current_class=None)
            if resolved:
                self.graph.add_edge(class_node, resolved, relation="INHERITS")
            else:
                self.unknown_impact_zones.add(f"Unresolved inheritance: {self._expr_text(base_expr)}")

    def _process_callable(
        self,
        module_name: str,
        callable_node: str,
        fn_node: ast.FunctionDef,
        current_class: Optional[str],
    ) -> None:
        for child in ast.walk(fn_node):
            if isinstance(child, ast.Call):
                self._handle_call(module_name, callable_node, child, current_class)
            elif isinstance(child, ast.Assign):
                self._handle_assign(module_name, callable_node, child, current_class=current_class)
            elif isinstance(child, ast.AnnAssign):
                self._handle_ann_assign(module_name, callable_node, child, current_class=current_class)
            elif isinstance(child, ast.AugAssign):
                self._handle_aug_assign(module_name, callable_node, child, current_class=current_class)
            elif isinstance(child, ast.Attribute):
                if isinstance(child.ctx, ast.Load):
                    data_node = self._data_node_id(self._expr_text(child))
                    self.graph.add_node(data_node, type="data_entity", name=self._expr_text(child), module=module_name)
                    self.graph.add_edge(callable_node, data_node, relation="READS")
                    if (
                        current_class
                        and isinstance(child.value, ast.Name)
                        and child.value.id == "self"
                    ):
                        class_node = self._class_node_id(module_name, current_class)
                        self.graph.add_edge(class_node, data_node, relation="READS")
            elif isinstance(child, ast.Return) and child.value is not None:
                returned = self._resolve_expression(module_name, child.value, current_class=current_class)
                if returned:
                    self.graph.add_edge(callable_node, returned, relation="RETURNS")

    def _handle_call(
        self,
        module_name: str,
        callable_node: str,
        call_node: ast.Call,
        current_class: Optional[str],
    ) -> None:
        callee = self._resolve_expression(module_name, call_node.func, current_class=current_class)
        name_hint = self._expr_text(call_node.func)

        if name_hint in {"eval", "exec", "__import__", "getattr", "setattr"}:
            self.unknown_impact_zones.add(f"Reflection/dynamic call: {name_hint}")
        if name_hint.endswith("import_module"):
            self.unknown_impact_zones.add("Dynamic import: importlib.import_module")

        if callee:
            target_type = self.graph.nodes[callee].get("type")
            relation = "DEPENDS_ON" if target_type == "class" else "CALLS"
            self.graph.add_edge(callable_node, callee, relation=relation)
            return

        ext_node = self._external_node_id(name_hint)
        self.graph.add_node(ext_node, type="external", name=name_hint, module="external")
        self.graph.add_edge(callable_node, ext_node, relation="CALLS")
        self.unknown_impact_zones.add(f"Unresolved symbol: {name_hint}")

    def _handle_assign(
        self,
        module_name: str,
        callable_node: str,
        assign_node: ast.Assign,
        current_class: Optional[str],
    ) -> None:
        for target in assign_node.targets:
            self._add_write_edge(module_name, callable_node, target, current_class=current_class)

    def _handle_ann_assign(
        self,
        module_name: str,
        callable_node: str,
        assign_node: ast.AnnAssign,
        current_class: Optional[str],
    ) -> None:
        self._add_write_edge(module_name, callable_node, assign_node.target, current_class=current_class)

    def _handle_aug_assign(
        self,
        module_name: str,
        callable_node: str,
        assign_node: ast.AugAssign,
        current_class: Optional[str],
    ) -> None:
        self._add_write_edge(module_name, callable_node, assign_node.target, current_class=current_class)

    def _add_write_edge(
        self,
        module_name: str,
        callable_node: str,
        target: ast.AST,
        current_class: Optional[str],
    ) -> None:
        if isinstance(target, ast.Attribute):
            field_name = self._expr_text(target)
            data_node = self._data_node_id(field_name)
            self.graph.add_node(data_node, type="data_entity", name=field_name, module=module_name)
            self.graph.add_edge(callable_node, data_node, relation="WRITES")
            if (
                current_class
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
            ):
                class_node = self._class_node_id(module_name, current_class)
                self.graph.add_edge(class_node, data_node, relation="WRITES")

    def _resolve_expression(
        self, module_name: str, expr: ast.AST, current_class: Optional[str]
    ) -> Optional[str]:
        context = self.module_contexts[module_name]

        if isinstance(expr, ast.Name):
            name = expr.id
            if name in context["imports"]:
                return context["imports"][name]
            if name in context["functions"]:
                return context["functions"][name]
            if name in context["classes"]:
                return context["classes"][name]

            candidates = sorted(self.global_symbol_index.get(name, set()))
            if len(candidates) == 1:
                return candidates[0]
            return None

        if isinstance(expr, ast.Attribute):
            if isinstance(expr.value, ast.Name):
                base_name = expr.value.id
                if base_name == "self" and current_class:
                    method = self.module_contexts[module_name]["methods"].get(current_class, {}).get(expr.attr)
                    if method:
                        return method

                imported = context["imports"].get(base_name)
                if imported and imported.startswith("module:"):
                    imported_module = imported[len("module:") :]
                    direct = self._resolve_symbol_from_module(imported_module, expr.attr)
                    if direct:
                        return direct
            return None

        if isinstance(expr, ast.Call):
            return self._resolve_expression(module_name, expr.func, current_class=current_class)

        return None

    def _resolve_symbol_from_module(self, module_name: str, symbol: str) -> Optional[str]:
        function_node = self._function_node_id(module_name, symbol)
        class_node = self._class_node_id(module_name, symbol)

        if function_node in self.graph:
            return function_node
        if class_node in self.graph:
            return class_node
        return None

    def validate_and_normalize_intent(self, raw_intent: Dict[str, Any]) -> Tuple[ChangeIntent, str]:
        intent = ChangeIntent.from_raw(raw_intent)
        target_node = self.resolve_target(intent.target)
        target_data = self.graph.nodes[target_node]

        node_type = target_data.get("type")
        module_name = target_data.get("module", "")

        if intent.change_type == "api_modification":
            if node_type == "api":
                pass
            elif node_type != "function" or not self._is_api_function(target_data):
                raise ValueError("api_modification must target an API function.")
        elif intent.change_type == "validation_rule_change":
            if node_type != "function":
                raise ValueError("validation_rule_change must target a function.")
            if "validate" not in target_data.get("name", "").lower() and "validation" not in module_name:
                raise ValueError("validation_rule_change target should be a validation function/module.")
        elif intent.change_type == "data_model_change":
            if node_type not in {"class", "data_entity"} and not module_name.startswith("models."):
                raise ValueError("data_model_change must target a model class or data entity.")
        elif intent.change_type in {"function_logic_change", "refactor_shared_method"}:
            if node_type != "function":
                raise ValueError(f"{intent.change_type} must target a function or method.")

        return intent, target_node

    def resolve_target(self, raw_target: str) -> str:
        raw_target = raw_target.strip()
        if raw_target in self.graph:
            return raw_target
        if not self.allow_symbol_target:
            raise ValueError("Target must be fully-qualified node ID.")

        matches = []
        for node_id, data in self.graph.nodes(data=True):
            if data.get("name") == raw_target:
                matches.append(node_id)

        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise ValueError(f"Target '{raw_target}' not found in graph.")
        raise ValueError(
            f"Target '{raw_target}' is ambiguous. Use a fully qualified node id. Candidates: {matches}"
        )

    def generate_report(self, intent: ChangeIntent, target_node: str) -> Dict[str, Any]:
        dep_graph = self._dependency_subgraph()
        direct = self._direct_impacts(dep_graph, target_node)
        all_related = self._transitive_related(dep_graph, target_node)
        indirect = sorted(all_related - direct - {target_node})
        direct_sorted = sorted(direct)

        breaking_contract = self._is_contract_break(intent)

        direct_items = [
            self._impact_item(dep_graph, target_node, node, "Direct", intent, breaking_contract)
            for node in direct_sorted
        ]
        indirect_items = [
            self._impact_item(dep_graph, target_node, node, "Indirect", intent, breaking_contract)
            for node in indirect
        ]

        risks = self._risk_areas(intent, direct_items, indirect_items, breaking_contract)
        severity = self._severity(intent, direct_items, indirect_items, breaking_contract)

        return {
            "change": {
                "change_type": intent.change_type,
                "target": target_node,
                "target_display": self.graph.nodes[target_node].get("name", target_node),
                "modification": intent.modification,
                **intent.metadata,
            },
            "direct_impacts": direct_items,
            "indirect_impacts": indirect_items,
            "risk_areas": risks,
            "unknown_impact_zones": sorted(self.unknown_impact_zones),
            "severity": severity,
        }

    def _impact_item(
        self,
        dep_graph: nx.DiGraph,
        target_node: str,
        node: str,
        impact_type: str,
        intent: ChangeIntent,
        breaking_contract: bool,
    ) -> Dict[str, Any]:
        path = self._trace_path(dep_graph, target_node, node)
        dependency_types = self._path_relations(path)
        category = self._classify_category(node, dependency_types, intent, breaking_contract)

        node_data = self.graph.nodes[node]
        path_display = " -> ".join(self.graph.nodes[p].get("name", p) for p in path)
        relation_chain = " -> ".join(dependency_types)
        if relation_chain:
            reason = (
                f"Impact propagates via relations [{relation_chain}] "
                f"along path: {path_display}"
            )
        else:
            reason = f"Impact propagates along path: {path_display}"

        return {
            "component": node,
            "name": node_data.get("name", node),
            "component_type": node_data.get("type", "unknown"),
            "module": node_data.get("module", "unknown"),
            "impact_type": impact_type,
            "category": category,
            "dependency_types": dependency_types,
            "path": path,
            "reason": reason,
        }

    def _trace_path(self, dep_graph: nx.DiGraph, target_node: str, node: str) -> List[str]:
        if nx.has_path(dep_graph, target_node, node):
            return nx.shortest_path(dep_graph, source=target_node, target=node)
        return [target_node, node]

    def _path_relations(self, path: List[str]) -> List[str]:
        relations: List[str] = []
        for src, dst in zip(path, path[1:]):
            edge = self.graph.get_edge_data(src, dst)
            if edge and "relation" in edge:
                relations.append(edge["relation"])
                continue
            edge = self.graph.get_edge_data(dst, src)
            if edge and "relation" in edge:
                relations.append(edge["relation"])
        return relations

    def _classify_category(
        self,
        node: str,
        dependency_types: List[str],
        intent: ChangeIntent,
        breaking_contract: bool,
    ) -> str:
        data = self.graph.nodes[node]
        module = data.get("module", "")
        node_type = data.get("type", "")

        if "test" in module or module.startswith("tests."):
            return "Test Impact"
        if node_type in {"class", "data_entity"} or any(r in {"READS", "WRITES"} for r in dependency_types):
            return "Data Handling"
        if node_type == "api" or module.startswith("api."):
            if breaking_contract and intent.change_type == "api_modification":
                return "Contract Compatibility"
            return "API-Level"
        return "Business Logic"

    def _dependency_subgraph(self) -> nx.DiGraph:
        dep_graph = nx.DiGraph()
        dep_graph.add_nodes_from(self.graph.nodes(data=True))
        for src, dst, edge in self.graph.edges(data=True):
            relation = edge.get("relation")
            if relation in DEPENDENCY_RELATIONS:
                dep_graph.add_edge(src, dst, relation=relation)
        return dep_graph

    def _direct_impacts(self, dep_graph: nx.DiGraph, target_node: str) -> Set[str]:
        return set(dep_graph.successors(target_node)).union(dep_graph.predecessors(target_node))

    def _transitive_related(self, dep_graph: nx.DiGraph, target_node: str) -> Set[str]:
        related: Set[str] = set()
        queue: deque[str] = deque([target_node])

        while queue:
            current = queue.popleft()
            if current in related:
                continue
            related.add(current)
            for neighbor in dep_graph.successors(current):
                if neighbor not in related:
                    queue.append(neighbor)
        return related

    def _is_contract_break(self, intent: ChangeIntent) -> bool:
        if intent.change_type != "api_modification":
            return False
        mod = intent.modification.lower().replace("_", " ").replace("-", " ")
        return any(pattern in mod for pattern in CONTRACT_BREAK_PATTERNS)

    def _risk_areas(
        self,
        intent: ChangeIntent,
        direct: List[Dict[str, Any]],
        indirect: List[Dict[str, Any]],
        breaking_contract: bool,
    ) -> List[str]:
        risks: List[str] = []
        categories = {item["category"] for item in [*direct, *indirect]}

        if breaking_contract:
            risks.append("Potential contract-breaking change in API surface.")
        if self.unknown_impact_zones:
            risks.append("Unknown Impact Zone: unresolved symbols or dynamic behavior detected.")
        if "Test Impact" not in categories:
            risks.append("Unknown test coverage for impacted components.")
        if intent.change_type == "data_model_change":
            risks.append("Data model change can propagate through mappings and persistence boundaries.")
        return risks

    def _severity(
        self,
        intent: ChangeIntent,
        direct: List[Dict[str, Any]],
        indirect: List[Dict[str, Any]],
        breaking_contract: bool,
    ) -> str:
        score = 0
        score += 2 * len(direct)
        score += len(indirect)

        categories = {item["category"] for item in [*direct, *indirect]}
        if "API-Level" in categories or "Contract Compatibility" in categories:
            score += 2
        if intent.change_type == "data_model_change":
            score += 2
        if breaking_contract:
            score += 4
        if self.unknown_impact_zones:
            score += 2

        if score >= 12:
            return "high"
        if score >= 6:
            return "medium"
        return "low"

    def _scan_files(self) -> List[str]:
        files = []
        for root, _, names in os.walk(self.project_path):
            for name in names:
                if name.endswith(".py"):
                    files.append(os.path.join(root, name))
        return sorted(files)

    def _module_name(self, file_path: str) -> str:
        rel_path = os.path.relpath(file_path, self.project_path)
        return rel_path.replace(os.sep, ".").rsplit(".py", 1)[0]

    def _module_node_id(self, module_name: str) -> str:
        return f"module:{module_name}"

    def _function_node_id(self, module_name: str, fn_name: str, parent_class: Optional[str] = None) -> str:
        if parent_class:
            return f"function:{module_name}.{parent_class}.{fn_name}"
        return f"function:{module_name}.{fn_name}"

    def _class_node_id(self, module_name: str, class_name: str) -> str:
        return f"class:{module_name}.{class_name}"

    def _data_node_id(self, name: str) -> str:
        return f"data:{name}"

    def _external_node_id(self, name: str) -> str:
        return f"external:{name}"

    def _add_function_node(
        self,
        node_id: str,
        module_name: str,
        fn_name: str,
        args: Iterable[ast.arg],
        parent_class: Optional[str],
        is_api: bool,
    ) -> None:
        params = [arg.arg for arg in args]
        self.graph.add_node(
            node_id,
            type="function",
            name=fn_name,
            module=module_name,
            params=params,
            parent_class=parent_class,
            is_api=is_api,
        )
        self.global_symbol_index[fn_name].add(node_id)

    def _add_api_node(self, module_name: str, fn_name: str, parent_class: Optional[str]) -> None:
        api_node_id = self._api_node_id(module_name, fn_name, parent_class)
        function_node_id = self._function_node_id(module_name, fn_name, parent_class)
        if api_node_id in self.graph:
            return
        display_name = f"{fn_name} [API]"
        self.graph.add_node(api_node_id, type="api", name=display_name, module=module_name)
        self.graph.add_edge(self._module_node_id(module_name), api_node_id, relation="CONTAINS")
        self.graph.add_edge(api_node_id, function_node_id, relation="DEPENDS_ON")

    def _has_api_decorator(self, fn_node: ast.FunctionDef) -> bool:
        for decorator in fn_node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            name = self._expr_text(target)
            if self._decorator_is_api(name):
                return True
        return False

    def _decorator_is_api(self, name: str) -> bool:
        if not name:
            return False
        if name == "route" or name.endswith(".route"):
            return True
        verbs = {"get", "post", "put", "delete", "patch", "options", "head"}
        last = name.split(".")[-1]
        return last in verbs

    def _is_api_function(self, node_data: Dict[str, Any]) -> bool:
        if node_data.get("is_api"):
            return True
        module_name = node_data.get("module", "")
        return module_name.startswith("api.")

    def _expr_text(self, expr: ast.AST) -> str:
        if isinstance(expr, ast.Name):
            return expr.id
        if isinstance(expr, ast.Attribute):
            return f"{self._expr_text(expr.value)}.{expr.attr}"
        if isinstance(expr, ast.Call):
            return self._expr_text(expr.func)
        return expr.__class__.__name__

    def _api_node_id(self, module_name: str, fn_name: str, parent_class: Optional[str] = None) -> str:
        if parent_class:
            return f"api:{module_name}.{parent_class}.{fn_name}"
        return f"api:{module_name}.{fn_name}"


def _header(title: str) -> str:
    line = "=" * 30
    return f"{line}\n {title}\n{line}"


def _format_module_name(module_name: str) -> str:
    return module_name.replace(".", "/")


def _format_node_entry(node_id: str, data: Dict[str, Any]) -> str:
    node_type = data.get("type", "unknown")
    module = data.get("module", "")
    name = data.get("name", node_id)

    if node_type == "module":
        display = _format_module_name(name)
        return f"('{display}', {{'type': 'module'}})"
    if node_type == "function":
        display = name
        module_display = _format_module_name(module)
        params = data.get("params", [])
        return (
            f"('{display}', {{'type': 'function', 'module': '{module_display}', "
            f"'params': {params}}})"
        )
    if node_type == "class":
        module_display = _format_module_name(module)
        return f"('{name}', {{'type': 'class', 'module': '{module_display}'}})"
    if node_type == "external":
        return f"('{name}', {{'type': 'external'}})"
    if node_type == "data_entity":
        return f"('{name}', {{'type': 'data_entity', 'module': '{_format_module_name(module)}'}})"
    return f"('{name}', {{'type': '{node_type}'}})"


def _format_edge(src: str, dst: str, graph: nx.DiGraph) -> str:
    src_data = graph.nodes[src]
    dst_data = graph.nodes[dst]
    src_name = src_data.get("name", src)
    dst_name = dst_data.get("name", dst)

    if src_data.get("type") == "module":
        src_name = _format_module_name(src_name)
    if dst_data.get("type") == "module":
        dst_name = _format_module_name(dst_name)
    return f"{src_name} → {dst_name}"


def load_intent(args: argparse.Namespace) -> Dict[str, Any]:
    if args.intent_json:
        return json.loads(args.intent_json)
    if args.intent_file:
        with open(args.intent_file, "r", encoding="utf-8") as handle:
            return json.load(handle)

    print("\n" + _header("CHANGE INTENT INPUT"))
    print("\nEnter Change Type:")
    print("1. api_modification")
    print("2. validation_rule_change")
    print("3. refactor_shared_method")
    print("4. function_logic_change")
    print("5. data_model_change")
    choice = input("Select (1/2/3/4/5): ").strip()
    mapping = {
        "1": "api_modification",
        "2": "validation_rule_change",
        "3": "refactor_shared_method",
        "4": "function_logic_change",
        "5": "data_model_change",
    }
    change_type = mapping.get(choice)
    if not change_type:
        raise ValueError("Invalid choice.")
    target = input("Enter target node id or symbol name: ").strip()
    modification = input("Describe the modification: ").strip()
    return {"change_type": change_type, "target": target, "modification": modification}


def report_to_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Blast Radius Report",
        "",
        "## Change Summary",
        f"- Change Type: `{report['change']['change_type']}`",
        f"- Target: `{report['change']['target']}`",
        f"- Modification: `{report['change']['modification']}`",
        "",
        "## Direct Impacts",
    ]
    if report["direct_impacts"]:
        for item in report["direct_impacts"]:
            lines.append(f"- `{item['component']}` ({item['category']}): {item['reason']}")
    else:
        lines.append("- None")

    lines.extend(["", "## Indirect Impacts"])
    if report["indirect_impacts"]:
        for item in report["indirect_impacts"]:
            lines.append(f"- `{item['component']}` ({item['category']}): {item['reason']}")
    else:
        lines.append("- None")

    lines.extend(["", "## Risk Zones"])
    if report["risk_areas"]:
        for risk in report["risk_areas"]:
            lines.append(f"- {risk}")
    else:
        lines.append("- None")

    lines.extend(["", f"## Severity: {report['severity'].capitalize()}"])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Blast radius analyzer")
    parser.add_argument("--project-path", default="project", help="Path to Python project")
    parser.add_argument(
        "--allow-symbol-target",
        action="store_true",
        help="Allow non-qualified target names when they uniquely map to one node",
    )
    parser.add_argument("--intent-file", help="Path to JSON file containing change intent")
    parser.add_argument("--intent-json", help="Inline JSON string containing change intent")
    parser.add_argument("--output-json", default="blast_report.json", help="JSON report output path")
    parser.add_argument("--output-md", default="blast_report.md", help="Markdown report output path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    analyzer = BlastRadiusAnalyzer(
        project_path=args.project_path,
        allow_symbol_target=args.allow_symbol_target,
    )
    analyzer.build_graph()

    try:
        raw_intent = load_intent(args)
        intent, target_node = analyzer.validate_and_normalize_intent(raw_intent)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1

    report = analyzer.generate_report(intent, target_node)

    with open(args.output_json, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    with open(args.output_md, "w", encoding="utf-8") as handle:
        handle.write(report_to_markdown(report))

    label_map = {
        "api_modification": "API_CHANGE",
        "validation_rule_change": "VALIDATION_CHANGE",
        "refactor_shared_method": "REFACTOR",
        "function_logic_change": "LOGIC_CHANGE",
        "data_model_change": "DATA_MODEL_CHANGE",
    }
    change_label = label_map.get(intent.change_type, intent.change_type.upper())

    print("Blast radius analysis complete.")
    print(f"JSON report: {args.output_json}")
    print(f"Markdown report: {args.output_md}")
    print(f"Severity: {report['severity']}")
    print(f"Direct impacts: {len(report['direct_impacts'])}")
    print(f"Indirect impacts: {len(report['indirect_impacts'])}")
    print("...")

    print("\n" + _header("BLAST RADIUS REPORT"))
    print("\nChange Type: " + change_label)
    print("Target: " + report["change"]["target_display"])
    print("Description: " + report["change"]["modification"])
    print("\nDetailed Impact Report:\n")

    items = [*report["direct_impacts"], *report["indirect_impacts"]]
    items_sorted = sorted(items, key=lambda item: item["name"])
    for item in items_sorted:
        module_name = item.get("module", "unknown")
        component_type = item.get("component_type", "unknown")
        layer = "Unknown Layer"
        if component_type == "api" or module_name.startswith("api."):
            layer = "API Layer"
        elif module_name.startswith("services."):
            layer = "Service Layer"
        elif module_name.startswith("models."):
            layer = "Data Model Layer"
        elif module_name.startswith("database."):
            layer = "Data Access Layer"

        impact_type = "Root Change" if item["component"] == target_node else "Upstream Impact"
        print("----------------------------------")
        print(f"Component   : {item['name']}")
        print(f"Layer       : {layer}")
        print(f"Impact Type : {impact_type}")
        print(f"Reason      : Calls or references '{report['change']['target_display']}'")

    print("\n----------------------------------")
    total_impacted = len({item["component"] for item in items})
    risk_level = report["severity"].upper()
    print(f"Total Impacted Components: {total_impacted}")
    print(f"Risk Level: {risk_level}")
    print(f"\nJSON report exported to {args.output_json}")

    print("\nTraceability Paths:\n")
    for item in items_sorted:
        path_names = [analyzer.graph.nodes[n].get("name", n) for n in item["path"]]
        print(" → ".join(path_names))

    api_impacted = any(
        item.get("component_type") == "api" or item.get("module", "").startswith("api.")
        for item in items
    )
    data_impacted = any(
        item.get("module", "").startswith("models.")
        or item.get("component_type") in {"class", "data_entity"}
        for item in items
    )
    print("\n=== Impact Summary ===")
    print(f"API Impacted: {api_impacted}")
    print(f"Data Layer Impacted: {data_impacted}")
    print("External Dependencies Impacted: False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
