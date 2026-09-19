import unittest

from app.workflows.contract import (
    ContractAction,
    ContractStage,
    WorkflowContext,
    action_is_allowed,
    describe_workflow,
    resolve_stage,
    workflow_catalog,
)


class ContractWorkflowTests(unittest.TestCase):
    def test_resolves_main_lifecycle(self):
        cases = (
            (WorkflowContext(), ContractStage.DRAFT),
            (WorkflowContext(has_version=True), ContractStage.READY_TO_INVITE),
            (WorkflowContext(has_version=True, invite_sent=True), ContractStage.AWAITING_COUNTERPARTY),
            (
                WorkflowContext(has_version=True, invite_sent=True, party_2_approved=True),
                ContractStage.AWAITING_CREATOR,
            ),
            (WorkflowContext(finalized=True), ContractStage.ACTIVE),
            (WorkflowContext(finalized=True, dispute_opened=True), ContractStage.DISPUTE),
            (WorkflowContext(finalized=True, completed=True), ContractStage.COMPLETED),
            (WorkflowContext(deleted=True), ContractStage.DELETED),
        )
        for context, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(resolve_stage(context), expected)

    def test_role_controls_signing_actions(self):
        counterparty_stage = WorkflowContext(has_version=True, invite_sent=True)
        self.assertTrue(action_is_allowed(counterparty_stage, "party_2", ContractAction.SIGN_COUNTERPARTY))
        self.assertFalse(action_is_allowed(counterparty_stage, "party_1", ContractAction.SIGN_COUNTERPARTY))

        creator_stage = WorkflowContext(has_version=True, invite_sent=True, party_2_approved=True)
        self.assertTrue(action_is_allowed(creator_stage, "party_1", ContractAction.SIGN_CREATOR))
        self.assertFalse(action_is_allowed(creator_stage, "party_2", ContractAction.SIGN_CREATOR))

    def test_finalized_contract_cannot_be_deleted_or_edited(self):
        context = WorkflowContext(finalized=True)
        self.assertFalse(action_is_allowed(context, "party_1", ContractAction.DELETE_CONTRACT))
        self.assertFalse(action_is_allowed(context, "party_1", ContractAction.CREATE_VERSION))

    def test_description_is_frontend_ready(self):
        result = describe_workflow(WorkflowContext(has_version=True), "party_1")
        self.assertEqual(result["stage"], "ready_to_invite")
        self.assertIn("send_invite", result["available_actions"])
        self.assertEqual(result["action_labels"]["send_invite"], "Направить на согласование")

    def test_catalog_contains_every_stage_and_action(self):
        catalog = workflow_catalog()
        self.assertEqual(set(catalog["stages"]), {stage.value for stage in ContractStage})
        self.assertEqual(set(catalog["actions"]), {action.value for action in ContractAction})


if __name__ == "__main__":
    unittest.main()
