import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from blast_analyzer import BlastRadiusAnalyzer


class BlastAnalyzerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.analyzer = BlastRadiusAnalyzer(project_path="project")
        cls.analyzer.build_graph()

    def test_graph_contains_expected_call_edges(self) -> None:
        graph = self.analyzer.graph

        post_user = "function:api.user_api.post_user"
        create_user = "function:services.user_service.create_user"
        validate_user = "function:utils.validation.validate_user"
        user_class = "class:models.user_model.User"

        self.assertTrue(graph.has_edge(post_user, create_user))
        self.assertEqual(graph[post_user][create_user]["relation"], "CALLS")
        self.assertTrue(graph.has_edge(create_user, validate_user))
        self.assertEqual(graph[create_user][validate_user]["relation"], "CALLS")
        self.assertTrue(graph.has_edge(create_user, user_class))
        self.assertEqual(graph[create_user][user_class]["relation"], "DEPENDS_ON")

    def test_validate_and_normalize_intent(self) -> None:
        raw = {
            "change_type": "api_modification",
            "target": "post_user",
            "modification": "add_optional_field",
        }
        intent, target = self.analyzer.validate_and_normalize_intent(raw)

        self.assertEqual(intent.change_type, "api_modification")
        self.assertEqual(target, "function:api.user_api.post_user")

    def test_report_has_direct_and_indirect_sections(self) -> None:
        raw = {
            "change_type": "function_logic_change",
            "target": "create_user",
            "modification": "adjust validation flow",
        }
        intent, target = self.analyzer.validate_and_normalize_intent(raw)
        report = self.analyzer.generate_report(intent, target)

        self.assertIn("direct_impacts", report)
        self.assertIn("indirect_impacts", report)
        self.assertIn("risk_areas", report)
        self.assertIn("severity", report)
        self.assertGreaterEqual(len(report["direct_impacts"]), 1)

    def test_inheritance_edges_use_inherits_relation(self) -> None:
        with TemporaryDirectory() as tmpdir:
            pkg = Path(tmpdir)
            (pkg / "sample.py").write_text(
                "class Parent:\n"
                "    pass\n\n"
                "class Child(Parent):\n"
                "    pass\n",
                encoding="utf-8",
            )

            analyzer = BlastRadiusAnalyzer(project_path=tmpdir)
            analyzer.build_graph()
            graph = analyzer.graph

            child = "class:sample.Child"
            parent = "class:sample.Parent"
            self.assertTrue(graph.has_edge(child, parent))
            self.assertEqual(graph[child][parent]["relation"], "INHERITS")


if __name__ == "__main__":
    unittest.main()
