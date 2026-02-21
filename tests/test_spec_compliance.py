import unittest

from blast_analyzer import BlastRadiusAnalyzer, report_to_markdown


class SpecComplianceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.analyzer = BlastRadiusAnalyzer(project_path="project")
        cls.analyzer.build_graph()

    def test_required_graph_node_types_exist(self) -> None:
        node_types = {data.get("type") for _, data in self.analyzer.graph.nodes(data=True)}
        self.assertIn("module", node_types)
        self.assertIn("function", node_types)
        self.assertIn("class", node_types)
        self.assertIn("data_entity", node_types)

    def test_required_dependency_relations_exist(self) -> None:
        relations = {edge.get("relation") for _, _, edge in self.analyzer.graph.edges(data=True)}
        self.assertIn("CALLS", relations)
        self.assertIn("IMPORTS", relations)
        self.assertIn("DEPENDS_ON", relations)
        self.assertIn("READS", relations)
        self.assertIn("WRITES", relations)

    def test_change_intent_accepts_supported_types(self) -> None:
        cases = [
            {"change_type": "api_modification", "target": "post_user", "modification": "add_optional_field"},
            {"change_type": "function_logic_change", "target": "create_user", "modification": "adjust flow"},
            {"change_type": "validation_rule_change", "target": "validate_user", "modification": "change min age"},
            {"change_type": "refactor_shared_method", "target": "create_user", "modification": "extract helper"},
            {"change_type": "data_model_change", "target": "User", "modification": "add field"},
        ]
        for raw in cases:
            intent, target = self.analyzer.validate_and_normalize_intent(raw)
            self.assertTrue(intent.change_type)
            self.assertTrue(target in self.analyzer.graph)

    def test_change_intent_rejects_invalid_type(self) -> None:
        with self.assertRaises(ValueError):
            self.analyzer.validate_and_normalize_intent(
                {"change_type": "invalid_type", "target": "create_user", "modification": "x"}
            )

    def test_direct_and_indirect_impacts_present(self) -> None:
        intent, target = self.analyzer.validate_and_normalize_intent(
            {
                "change_type": "function_logic_change",
                "target": "create_user",
                "modification": "adjust validation flow",
            }
        )
        report = self.analyzer.generate_report(intent, target)

        direct_ids = {item["component"] for item in report["direct_impacts"]}
        self.assertIn("function:api.user_api.post_user", direct_ids)
        self.assertIn("function:database.db.save_user", direct_ids)
        self.assertIn("function:utils.validation.validate_user", direct_ids)
        self.assertIn("class:models.user_model.User", direct_ids)

        self.assertGreaterEqual(len(report["indirect_impacts"]), 1)

    def test_explainability_fields_exist_on_every_impact(self) -> None:
        intent, target = self.analyzer.validate_and_normalize_intent(
            {
                "change_type": "function_logic_change",
                "target": "create_user",
                "modification": "adjust validation flow",
            }
        )
        report = self.analyzer.generate_report(intent, target)

        for item in report["direct_impacts"] + report["indirect_impacts"]:
            self.assertTrue(item["reason"])
            self.assertTrue(item["path"])
            self.assertIsInstance(item["dependency_types"], list)
            self.assertIn(item["impact_type"], {"Direct", "Indirect"})

    def test_report_has_spec_top_level_keys(self) -> None:
        intent, target = self.analyzer.validate_and_normalize_intent(
            {
                "change_type": "function_logic_change",
                "target": "create_user",
                "modification": "adjust validation flow",
            }
        )
        report = self.analyzer.generate_report(intent, target)

        self.assertIn("change", report)
        self.assertIn("direct_impacts", report)
        self.assertIn("indirect_impacts", report)
        self.assertIn("risk_areas", report)
        self.assertIn("severity", report)

    def test_unknown_impact_zone_detection(self) -> None:
        intent, target = self.analyzer.validate_and_normalize_intent(
            {
                "change_type": "function_logic_change",
                "target": "create_user",
                "modification": "adjust validation flow",
            }
        )
        report = self.analyzer.generate_report(intent, target)
        self.assertIn("unknown_impact_zones", report)
        self.assertGreaterEqual(len(report["unknown_impact_zones"]), 1)

    def test_contract_break_risk_for_breaking_api_change(self) -> None:
        intent, target = self.analyzer.validate_and_normalize_intent(
            {
                "change_type": "api_modification",
                "target": "post_user",
                "modification": "rename field",
            }
        )
        report = self.analyzer.generate_report(intent, target)
        self.assertTrue(any("contract-breaking" in risk.lower() for risk in report["risk_areas"]))

    def test_markdown_output_contains_sections(self) -> None:
        intent, target = self.analyzer.validate_and_normalize_intent(
            {
                "change_type": "function_logic_change",
                "target": "create_user",
                "modification": "adjust validation flow",
            }
        )
        report = self.analyzer.generate_report(intent, target)
        md = report_to_markdown(report)
        self.assertIn("# Blast Radius Report", md)
        self.assertIn("## Direct Impacts", md)
        self.assertIn("## Indirect Impacts", md)
        self.assertIn("## Risk Zones", md)
        self.assertIn("## Severity:", md)


if __name__ == "__main__":
    unittest.main()
